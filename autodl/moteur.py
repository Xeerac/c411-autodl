"""Le moteur : passages, nettoyage, rangement, cross-seed, bilan, freeleech, surveillance des pannes."""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .c411 import C411, freeleech_sources
from .commun import USER_AGENT, _duration, _human, infohash_of, log
from .contenu import content_type, guess_type, qbit_category
from .filtres import _ordered, _reject, _scan


def freeleech_cfg(cfg: dict) -> dict:
    """Réglages élargis pendant un freeleech : plus de catégories, plus gros, plus nombreux."""
    fl = dict(cfg)
    cats = [c.strip() for c in cfg["cats"].split(",") if c.strip()]
    cats += [c for c in cfg["fl_cats"] if c not in cats]
    fl["cats"] = ",".join(cats)
    fl["max_per_run"] = cfg["fl_max_per_run"]
    if cfg["fl_max_size"] is not None:
        fl["max_size"] = cfg["fl_max_size"]
    if cfg["fl_ignore_formats"]:
        fl["formats"] = []  # sinon FORMATS=epub,cbz écarterait tous les films et séries
    tags = [t.strip() for t in cfg["qbit_tags"].split(",") if t.strip()]
    fl["qbit_tags"] = ",".join(tags + ([] if "freeleech" in tags else ["freeleech"]))
    return fl


def _freeleech_transition(args, cfg: dict, ctx: dict, sources: list[str]) -> None:
    """Journalise et notifie le début et la fin d'un freeleech (une seule fois chacun)."""
    active = bool(sources)
    if active == ctx.get("freeleech", False):
        return
    ctx["freeleech"] = active
    if active:
        extra = f", catégories en plus : {','.join(cfg['fl_cats'])}" if cfg["fl_cats"] else ""
        msg = (f"🎉 Freeleech actif sur c411 ({', '.join(sources)}) : mode élargi "
               f"(jusqu'à {cfg['fl_max_per_run']} torrents par passage{extra}, pas de pause liée au ratio)")
    else:
        msg = "🔚 Freeleech terminé : retour aux réglages normaux"
    log.info("%s", msg)
    if ctx.get("notifier") and not args.dry_run:
        ctx["notifier"].send(msg)


def run_once(args, cfg: dict, ctx: dict) -> int:
    """Un passage complet. Retourne le nombre de torrents ajoutés."""
    c411, qbit, state = ctx["c411"], ctx["qbit"], ctx["state"]
    routine = log.debug if args.boucle else log.info  # en boucle, on ne journalise que l'essentiel

    # Ratio : contrôlé avant de chercher, pour ne rien demander à c411 si on est sous le seuil
    up = down = 0
    freeleech = False
    if cfg["min_ratio"] > 0 or cfg["fl_mode"]:
        ratio, up, down, allowed = ctx["profile"].ratio()
        ctx["last_ratio"] = ratio
        sources = freeleech_sources(getattr(ctx["profile"], "last_profile", None)) if cfg["fl_mode"] else []
        freeleech = bool(sources)
        _freeleech_transition(args, cfg, ctx, sources)
        if freeleech:
            cfg = freeleech_cfg(cfg)  # recherche élargie le temps du freeleech
        blocked = None
        if not allowed:
            blocked = "c411 bloque les téléchargements sur ton compte"
        elif cfg["min_ratio"] > 0 and ratio <= cfg["min_ratio"] and not freeleech:
            # En freeleech, télécharger ne fait pas baisser le ratio : pas de pause
            blocked = f"ratio {ratio:.2f} ≤ {cfg['min_ratio']:.2f}"
        if blocked:
            if ctx.get("blocked") != blocked:  # on ne le répète pas à chaque minute
                log.warning("En pause : %s", blocked)
                if ctx.get("notifier") and args.boucle:
                    ctx["notifier"].status(f"⏸️ c411-autodl en pause : {blocked}")
            ctx["blocked"] = blocked
            return 0
        if ctx.get("blocked"):
            log.info("Reprise : ratio %.2f > %.2f", ratio, cfg["min_ratio"])
            if ctx.get("notifier"):
                ctx["notifier"].status(f"▶️ c411-autodl reprend : ratio {ratio:.2f} > {cfg['min_ratio']:.2f}")
        ctx["blocked"] = None
        routine("Ratio actuel : %.2f", ratio)

    qbit.login(quiet=bool(args.boucle))
    in_client = qbit.hashes()
    free = qbit.free_space()
    min_free = cfg["min_free_gb"] * 1024**3
    if free >= 0:
        routine("Espace libre seedbox : %.1f Go", free / 1024**3)

    added = skipped = total_bytes = counted_bytes = 0
    added_items: list[dict] = []
    budget_bytes = free - min_free if free >= 0 else None

    for it in _ordered(_scan(c411, args, cfg), cfg):
        if added >= cfg["max_per_run"]:
            log.info("Maximum par passage atteint (%d)", cfg["max_per_run"])
            return _finish(added, skipped, total_bytes, args, ctx, added_items, up, down + counted_bytes)

        h = it["infohash"]
        if h and (h in in_client or state.has(h)):
            continue
        reason = _reject(it, cfg)
        if reason:
            skipped += 1
            log.debug("ignoré (%s) : %s", reason, it["title"])
            continue
        if budget_bytes is not None and it["size"] > budget_bytes:
            log.warning("Plus assez d'espace (marge %d Go) : arrêt", cfg["min_free_gb"])
            return _finish(added, skipped, total_bytes, args, ctx, added_items, up, down + counted_bytes)
        if not it["link"]:
            log.warning("Pas de lien de téléchargement : %s", it["title"])
            continue
        # Ce que c411 comptera réellement en reçu (rien pendant un freeleech sur le compte)
        counted = 0 if freeleech else int(it["size"] * it["dl_factor"])
        if cfg["min_ratio"] > 0 and counted and down + counted_bytes + counted > 0:
            projected = up / (down + counted_bytes + counted)
            if projected <= cfg["min_ratio"]:
                skipped += 1
                log.info("ignoré (ratio après téléchargement : %.3f) : %s", projected, it["title"])
                continue

        kind = content_type(it["category"], it["title"])
        category = qbit_category(kind, cfg)
        if args.dry_run:
            log.info("[dry-run] + %s (%s, %d complétés, %d seeders, %s leechers) -> %s",
                     it["title"], _human(it["size"]), it["completed"], it["seeders"],
                     it["leechers"] if it["leechers"] >= 0 else "?", category)
            added += 1
            total_bytes += it["size"]
            counted_bytes += counted
            continue

        try:
            data = c411.download(it["link"])
            h = h or infohash_of(data)
            if h in in_client or state.has(h):
                continue
            known = ctx.setdefault("categories_ok", set())
            if category not in known:  # créée une fois par catégorie (409 si elle existe déjà)
                qbit.ensure_category(category, cfg["qbit_savepath"])
                known.add(category)
            qbit.add(f"{h}.torrent", data, category, cfg["qbit_tags"],
                     cfg["qbit_savepath"], cfg["qbit_paused"])
        except Exception as e:  # on continue avec les suivants
            log.error("Échec pour %s : %s", it["title"], e)
            continue

        state.add(h, it["title"], kind, it["size"])
        state.save()
        in_client.add(h)
        if budget_bytes is not None:
            budget_bytes -= it["size"]
        added += 1
        total_bytes += it["size"]
        counted_bytes += counted
        added_items.append(it)
        log.info("+ %s (%s, %d complétés, %d seeders, %s leechers)", it["title"], _human(it["size"]),
                 it["completed"], it["seeders"], it["leechers"] if it["leechers"] >= 0 else "?")

    return _finish(added, skipped, total_bytes, args, ctx, added_items, up, down + counted_bytes)


# Messages renvoyés par un tracker quand le torrent n'existe plus (c411 : « Torrent removed by its uploader »)
REMOVED_RE = re.compile(r"removed|unregistered|not registered|not found|deleted|supprim|inexistant|introuvable",
                        re.IGNORECASE)


def cleanup(args, cfg: dict, ctx: dict) -> int:
    """Retire de qBittorrent les torrents supprimés de c411. Retourne le nombre de torrents traités.

    Un torrent n'est retiré que si DEUX signaux concordent : les trackers c411 de qBittorrent signalent
    sa suppression ET l'API c411 répond 404. Une panne de c411 ne peut donc rien supprimer.
    """
    qbit, c411 = ctx["qbit"], ctx["c411"]
    action = cfg["cleanup_action"]
    qbit.login(quiet=True)
    everything = qbit.torrents()
    scope = [t for t in everything if cfg["own_tag"] in [x.strip() for x in t.get("tags", "").split(",")]]
    log.debug("Nettoyage : vérification de %d torrents (tag « %s »)", len(scope), cfg["own_tag"])

    done = 0
    for t in scope:
        h = t["hash"].lower()
        c411_trackers = [tr for tr in qbit.trackers(h)
                         if "c411" in (urllib.parse.urlsplit(tr.get("url", "")).hostname or "")]
        if not c411_trackers:
            continue
        # Au moins un tracker c411 signale la suppression, et aucun ne fonctionne (statut 2 = OK)
        if any(tr.get("status") == 2 for tr in c411_trackers):
            continue
        removed_msg = next((tr["msg"] for tr in c411_trackers if REMOVED_RE.search(tr.get("msg") or "")), None)
        if not removed_msg:
            continue
        if c411.exists(h) is not False:  # confirmation par l'API : seul un 404 compte
            log.info("Nettoyage : %s signalé « %s » mais toujours présent sur c411, on ne touche à rien",
                     t["name"], removed_msg)
            continue

        # Fichiers partagés avec un autre torrent (cross-seed sur un autre tracker) : on les garde
        shared = any(o["hash"] != t["hash"] and o.get("content_path") == t.get("content_path") for o in everything)
        if action == "pause":
            what = "mis en pause (tag c411-supprime)"
        elif action == "fichiers" and not shared:
            what = "retiré, fichiers supprimés"
        else:
            what = "retiré, fichiers conservés" + (" (utilisés par un autre torrent)" if shared else "")

        if args.dry_run:
            log.info("[dry-run] Supprimé de c411 (« %s ») : %s serait %s", removed_msg, t["name"], what)
            done += 1
            continue
        try:
            if action == "pause":
                qbit.stop(h)
                qbit.add_tags(h, "c411-supprime")
            else:
                qbit.delete(h, delete_files=(action == "fichiers" and not shared))
        except Exception as e:
            log.error("Nettoyage : échec pour %s : %s", t["name"], e)
            continue
        done += 1
        log.info("🗑️ Supprimé de c411 (« %s ») : %s %s", removed_msg, t["name"], what)
        if ctx.get("notifier"):
            ctx["notifier"].send(f"🗑️ **Supprimé de c411** ({removed_msg}) : {t['name']}, {what}.")
    return done


def watchdog(cfg: dict, ctx: dict, errors: int, error: Exception | None = None) -> int:
    """Suit les échecs d'affilée et prévient en cas de panne puis de reprise. Retourne le nouveau compteur."""
    if error is None:
        if errors >= cfg["alert_after"]:
            down = _duration(time.time() - ctx.get("down_since", time.time()))
            log.info("Fonctionne à nouveau après %d passages en échec (%s)", errors, down)
            _alert(cfg, ctx, f"✅ **c411-autodl fonctionne à nouveau**, après {errors} passages en échec ({down}).")
        return 0
    errors += 1
    if errors == 1:
        ctx["down_since"] = time.time()
    # On signale la première erreur, puis une sur dix pour ne pas inonder le journal
    if errors == 1 or errors % 10 == 0:
        log.error("Passage interrompu (%d erreur(s) d'affilée) : %s", errors, error)
    if errors == cfg["alert_after"]:
        _alert(cfg, ctx, f"⚠️ **c411-autodl en panne** : {errors} passages en échec d'affilée.\n"
                         f"Dernière erreur : {str(error)[:300]}\n"
                         f"Il continue de réessayer et te préviendra quand tout repartira.")
    return errors


def _stop(signum, frame):
    raise KeyboardInterrupt


def _alert(cfg: dict, ctx: dict, text: str) -> None:
    """Alerte de panne / de reprise (si ALERTE_PANNE et des notifications sont configurées)."""
    if cfg["alert"] and ctx.get("notifier"):
        ctx["notifier"].send(text)


def _safe(func, *args):
    """Une fonction annexe qui échoue ne doit jamais arrêter le programme."""
    try:
        return func(*args)
    except Exception as e:
        log.error("%s interrompu : %s", func.__name__, e)
        return None


def maybe_cleanup(args, cfg: dict, ctx: dict, force: bool = False) -> None:
    if not cfg["cleanup"] and not force:
        return
    now = time.monotonic()
    if not force and args.boucle and now - ctx.get("last_cleanup", -1e9) < cfg["cleanup_minutes"] * 60:
        return
    ctx["last_cleanup"] = now
    try:
        n = cleanup(args, cfg, ctx)
        (log.info if n or not args.boucle else log.debug)("Nettoyage terminé : %d torrent(s) supprimé(s) de c411", n)
    except Exception as e:
        log.error("Nettoyage interrompu : %s", e)


def recategorize(args, cfg: dict, ctx: dict, keep_location: bool = False) -> dict:
    """Range dans une catégorie par type les torrents déjà présents (commande --recategoriser).

    Le type exact est retrouvé via la recherche Torznab de c411 (l'API ne donne que « Ebook »),
    sinon deviné d'après le titre. Retourne {catégorie cible: nombre}.

    Par défaut qBittorrent déplace les fichiers dans le dossier de la nouvelle catégorie. Les torrents
    dont les fichiers servent aussi à un autre torrent (cross-seed) sont laissés tels quels : les
    déplacer casserait l'autre torrent. Avec keep_location, seule l'étiquette change (aucun fichier
    ne bouge) et ces torrents-là sont rangés aussi.
    """
    qbit, c411, state = ctx["qbit"], ctx["c411"], ctx["state"]
    qbit.login(quiet=True)
    everything = qbit.torrents()
    own = [t for t in everything if cfg["own_tag"] in [x.strip() for x in t.get("tags", "").split(",")]]
    paths: dict[str, int] = {}
    for t in everything:
        paths[t.get("content_path", "")] = paths.get(t.get("content_path", ""), 0) + 1
    log.info("Rangement de %d torrents (%s)…", len(own),
             "étiquette seulement, fichiers en place" if keep_location else "les fichiers suivent leur catégorie")

    summary: dict[str, int] = {}
    known_cats = ctx.setdefault("categories_ok", set())
    for i, t in enumerate(own, 1):
        h = t["hash"].lower()
        entry = state.seen.get(h, {})
        kind = entry.get("type") or _lookup_type(c411, h, entry.get("title") or t["name"])
        if kind and not entry.get("type") and h in state.seen:
            state.seen[h]["type"] = kind  # mémorisé pour le bilan
        kind = kind or guess_type(t["name"])
        target = f"{cfg['cat_prefix']}-{kind}"
        if t.get("category") == target:
            continue
        if paths.get(t.get("content_path", ""), 0) > 1 and not keep_location:
            log.info("  laissé en place (fichiers partagés avec un autre torrent) : %s", t["name"])
            continue
        summary[target] = summary.get(target, 0) + 1
        if args.dry_run:
            log.info("  [dry-run] %s -> %s", t["name"], target)
            continue
        try:
            if target not in known_cats:
                qbit.ensure_category(target, cfg["qbit_savepath"])
                known_cats.add(target)
            if keep_location:
                qbit.set_auto_management(h, False)  # sans gestion auto, changer de catégorie ne déplace rien
            qbit.set_category(h, target)
            log.info("  (%d/%d) %s -> %s", i, len(own), t["name"], target)
        except Exception as e:
            log.error("  échec pour %s : %s", t["name"], e)
    if not args.dry_run:
        state.save()
    verb = "seraient rangés" if args.dry_run else "rangés"
    log.info("Rangement terminé : %s %s", ", ".join(f"{n} dans {c}" for c, n in sorted(summary.items()))
             or "rien à ranger", verb if summary else "")
    return summary


def _lookup_type(c411: C411, infohash: str, title: str) -> str:
    """Type exact d'un torrent : on cherche son titre sur c411 et on lit la catégorie du résultat."""
    for query in (title, re.sub(r"[.\[\]()_-]+", " ", title).strip()):
        try:
            for it in c411.search("", 0, 50, query):
                if it["infohash"] == infohash:
                    return content_type(it["category"], it["title"])
        except Exception as e:
            log.debug("recherche du type impossible pour %s : %s", title, e)
    return ""


def maybe_crossseed(args, cfg: dict, ctx: dict) -> int:
    """Prévient cross-seed dès qu'un torrent ajouté par le programme a fini de télécharger.

    cross-seed cherche alors tout de suite la même release sur les autres trackers, au lieu
    d'attendre son prochain passage : on y arrive parmi les premiers seeders.
    """
    if not cfg["cs_url"]:
        return 0
    tracking = ctx["tracking"]
    sent = set(tracking.data.get("crossseed_envoyes", []))
    qbit = ctx["qbit"]
    qbit.login(quiet=True)
    complete = [t["hash"].lower() for t in qbit.torrents(tag=cfg["own_tag"]) if t.get("progress", 0) >= 1]

    if not tracking.data.get("crossseed_init"):
        # Premier lancement : les torrents déjà terminés sont couverts par la recherche quotidienne de
        # cross-seed, on ne les lui renvoie pas tous d'un coup
        if args.dry_run:
            log.info("[dry-run] cross-seed : %d torrents déjà terminés seraient marqués comme couverts",
                     len(complete))
            return 0
        tracking.data["crossseed_init"] = True
        tracking.data["crossseed_envoyes"] = sorted(set(complete) | sent)
        tracking.save()
        log.info("cross-seed : activé. %d torrents déjà terminés ne seront pas renvoyés", len(complete))
        return 0

    todo = [h for h in complete if h not in sent]
    done = 0
    for h in todo:
        if args.dry_run:
            log.info("[dry-run] cross-seed serait prévenu pour %s", h[:8])
            continue
        try:
            _crossseed_webhook(cfg, h)
        except urllib.error.HTTPError as e:
            log.error("cross-seed : refusé pour %s (HTTP %d%s)", h[:8], e.code,
                      " : vérifie CROSS_SEED_API_KEY" if e.code == 401 else "")
            if e.code == 401:
                break
            continue
        except Exception as e:  # cross-seed arrêté ou injoignable : on réessaiera au prochain passage
            if not ctx.get("cs_down"):
                log.warning("cross-seed injoignable (%s) : on réessaiera plus tard", e)
            ctx["cs_down"] = True
            break
        ctx["cs_down"] = False
        sent.add(h)
        done += 1
    if done:
        tracking.data["crossseed_envoyes"] = sorted(sent)
        tracking.save()
        log.info("cross-seed : %d torrent(s) terminé(s) envoyé(s) pour recherche immédiate", done)
    return done


def _crossseed_webhook(cfg: dict, infohash: str) -> None:
    req = urllib.request.Request(
        f"{cfg['cs_url'].rstrip('/')}/api/webhook",
        data=urllib.parse.urlencode({"infoHash": infohash}).encode(),
        headers={"X-Api-Key": cfg["cs_key"], "Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def report_data(cfg: dict, ctx: dict) -> tuple[dict, dict]:
    """Chiffres du bilan depuis le dernier relevé. Retourne (chiffres, nouveau relevé)."""
    qbit, state, tracking = ctx["qbit"], ctx["state"], ctx["tracking"]
    qbit.login(quiet=True)
    torrents = qbit.torrents(tag=cfg["own_tag"])
    snap = tracking.data.get("bilan") or {}
    prev_up, prev_down = snap.get("uploaded", {}), snap.get("downloaded", {})
    since = snap.get("time")

    up_delta = down_delta = 0
    by_type: dict[str, list] = {}
    top = []
    for t in torrents:
        h = t["hash"].lower()
        du = max(int(t.get("uploaded", 0)) - int(prev_up.get(h, 0)), 0)
        dd = max(int(t.get("downloaded", 0)) - int(prev_down.get(h, 0)), 0)
        up_delta += du
        down_delta += dd
        if du:
            top.append((du, t["name"]))
        kind = state.seen.get(h, {}).get("type") or guess_type(t["name"])
        agg = by_type.setdefault(kind, [0, 0, 0])  # [nombre, taille, envoyé depuis l'ajout]
        agg[0] += 1
        agg[1] += int(t.get("size", 0))
        agg[2] += int(t.get("uploaded", 0))

    added = 0
    for entry in state.seen.values():
        try:
            when = time.mktime(time.strptime(entry.get("added", ""), "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            continue
        if since is None or when >= since:
            added += 1

    data = {"since": since, "added": added, "up": up_delta, "down": down_delta, "ratio": None,
            "ratio_delta": None, "torrents": len(torrents),
            "types": sorted(((k, n, size, up) for k, (n, size, up) in by_type.items()),
                            key=lambda r: r[3] / r[2] if r[2] else 0, reverse=True),
            "top": sorted(top, reverse=True)[:3]}
    new_snap = {"time": time.time(),
                "uploaded": {t["hash"].lower(): int(t.get("uploaded", 0)) for t in torrents},
                "downloaded": {t["hash"].lower(): int(t.get("downloaded", 0)) for t in torrents}}
    if cfg["profile_key"]:
        try:
            ratio, _, _, _ = ctx["profile"].ratio()
            new_snap["ratio"] = data["ratio"] = ratio
            if "ratio" in snap:
                data["ratio_delta"] = ratio - snap["ratio"]
        except Exception as e:
            log.warning("Bilan : ratio indisponible (%s)", e)
    return data, new_snap


def _period(since: float | None) -> str:
    return "depuis le " + time.strftime("%d/%m à %H:%M", time.localtime(since)) if since else "depuis le début"


def report_text(d: dict) -> str:
    """Bilan au format Markdown simple (journal et Telegram)."""
    lines = [f"📊 **Bilan c411-autodl** ({_period(d['since'])})",
             f"• {d['added']} torrent(s) ajouté(s) · {_human(d['down'])} téléchargés · **{_human(d['up'])} envoyés**"]
    if d["ratio"] is not None:
        evolution = f" ({d['ratio_delta']:+.2f})" if d["ratio_delta"] is not None else ""
        lines.append(f"• Ratio c411 : {d['ratio']:.2f}{evolution}")
    if d["types"]:
        lines.append("**Rendement par type** (envoyé ÷ taille, depuis l'ajout) :")
        for kind, n, size, up in d["types"]:
            lines.append(f"• {kind} : ×{(up / size if size else 0):.2f} ({n} torrent(s), {_human(up)} envoyés)")
    if d["top"]:
        lines.append("**Ce qui a le plus envoyé** :")
        for du, name in d["top"]:
            lines.append(f"• {name[:80]} — {_human(du)}")
    return "\n".join(lines)


TYPE_LABELS = {"bd": "BD / mangas", "ebook": "eBooks", "presse": "Presse", "livre-audio": "Livres audio",
               "livre": "Livres", "musique": "Musique", "film": "Films", "serie": "Séries", "logiciel": "Logiciels",
               "jeu": "Jeux", "adulte": "Adulte"}
GREEN, ORANGE, BLURPLE = 0x2ECC71, 0xE67E22, 0x5865F2


def report_embed(d: dict) -> dict:
    """Bilan sous forme d'embed Discord : chiffres clés en tuiles, rendement en tableau aligné."""
    delta = d["ratio_delta"]
    color = BLURPLE if not delta else GREEN if delta > 0 else ORANGE
    fields = [{"name": "📤 Envoyé", "value": f"**{_human(d['up'])}**", "inline": True},
              {"name": "📥 Téléchargé", "value": _human(d["down"]), "inline": True},
              {"name": "➕ Ajoutés", "value": f"{d['added']} torrent(s)", "inline": True}]
    if d["ratio"] is not None:
        arrow = "" if delta is None else f"  {'▲' if delta > 0 else '▼' if delta < 0 else '='} {delta:+.2f}"
        fields.append({"name": "⚖️ Ratio c411", "value": f"**{d['ratio']:.2f}**{arrow}", "inline": True})
    if d["down"]:
        fields.append({"name": "🔁 Envoyé ÷ téléchargé", "value": f"×{d['up'] / d['down']:.2f}", "inline": True})
    fields.append({"name": "🌱 En seed", "value": f"{d['torrents']} torrent(s)", "inline": True})
    if d["types"]:
        rows = [f"{'Type':<13}{'Rdt':>8}{'Nb':>6}{'Envoyé':>11}"]
        for kind, n, size, up in d["types"][:8]:
            yield_ = "×" + format(up / size if size else 0, ".2f")
            rows.append(f"{TYPE_LABELS.get(kind, kind)[:13]:<13}{yield_:>8}{n:>6}{_human(up):>11}")
        fields.append({"name": "📈 Rendement par type (envoyé ÷ taille, depuis l'ajout)",
                       "value": ("```\n" + "\n".join(rows))[:1020] + "\n```", "inline": False})
    if d["top"]:
        medals = ("🥇", "🥈", "🥉")
        lines = [f"{medals[i]} **{_human(du)}** · {name[:70]}" for i, (du, name) in enumerate(d["top"])]
        fields.append({"name": "🏆 Ce qui a le plus envoyé", "value": "\n".join(lines)[:1024], "inline": False})
    return {"title": "📊 Bilan quotidien", "description": _period(d["since"]).capitalize(),
            "color": color, "fields": fields}


def build_report(cfg: dict, ctx: dict) -> tuple[str, dict]:
    """Bilan depuis le dernier relevé. Retourne (texte au format Markdown simple, nouveau relevé)."""
    data, snap = report_data(cfg, ctx)
    return report_text(data), snap


def maybe_report(args, cfg: dict, ctx: dict, force: bool = False) -> None:
    """Bilan une fois par jour à BILAN_HEURE (ou tout de suite avec --bilan, sans changer le relevé)."""
    if not cfg["bilan"] and not force:
        return
    if args.dry_run and not force:  # essai à blanc / lecture seule : le relevé quotidien n'est pas touché
        return
    tracking = ctx["tracking"]
    today = time.strftime("%Y-%m-%d")
    if not force and (time.localtime().tm_hour < cfg["bilan_heure"] or tracking.data.get("bilan_date") == today):
        return
    try:
        if not force and not tracking.data.get("bilan"):
            # Tout premier relevé : rien à comparer encore, le premier bilan arrivera demain
            _, snap = build_report(cfg, ctx)
            tracking.data.update(bilan=snap, bilan_date=today)
            tracking.save()
            log.info("Bilan : premier relevé enregistré, premier bilan demain vers %d h", cfg["bilan_heure"])
            return
        data, snap = report_data(cfg, ctx)
        text = report_text(data)
    except Exception as e:
        log.error("Bilan impossible : %s", e)
        return
    for line in text.replace("**", "").splitlines():
        log.info("%s", line)
    if ctx.get("notifier"):
        ctx["notifier"].send(text, embed=report_embed(data))
    if not force:
        tracking.data.update(bilan=snap, bilan_date=today)
        tracking.save()


def _finish(added: int, skipped: int, total_bytes: int, args,
            ctx: dict | None = None, items: list | None = None, up: int = 0, down: int = 0) -> int:
    verb = "seraient ajoutés" if args.dry_run else "ajoutés"
    dl = "à télécharger" if args.dry_run else "téléchargés"
    (log.debug if args.boucle and not added else log.info)(
        "Terminé : %d %s (%s %s), %d ignorés par les filtres",
        added, verb, _human(total_bytes), dl, skipped)
    if items and ctx and ctx.get("notifier"):
        ratio = up / down if up and down else None
        ctx["notifier"].added(items, total_bytes, ratio)
    return added
