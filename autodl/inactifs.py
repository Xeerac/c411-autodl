"""Retrait des torrents inactifs : ceux qui n'envoient plus rien depuis longtemps.

Règles de seed de c411 (Hit & Run) : un torrent est quitte après 72 h de seed OU un ratio de 1,0 sur
ce torrent. On ne se fie qu'au temps de seed, avec une marge (96 h par défaut, jamais moins de 72 h) :
le ratio vu par qBittorrent peut différer de celui compté par c411.

Un torrent n'est retiré que si TOUT est vrai :
- il porte le tag des torrents gérés (autodl) : tes torrents manuels et les cross-seeds ne sont jamais touchés ;
- il est complet et a seedé au moins INACTIFS_SEED_MIN_HEURES ;
- il n'a rien transféré depuis INACTIFS_JOURS jours ;
- personne ne l'attend : aucun leecher connecté ni annoncé par le tracker ;
- un tracker c411 répond normalement (un tracker en panne fausserait les deux points précédents).
Les fichiers partagés avec un autre torrent (cross-seed) sont toujours gardés, et le nombre de retraits
par jour est plafonné.
"""
from __future__ import annotations

import time
import urllib.parse

from .commun import log

HR_HOURS = 72  # temps de seed minimum exigé par c411
CHECK_EVERY = 3600  # une vérification par heure suffit largement


def _tags(t: dict) -> list[str]:
    return [x.strip() for x in t.get("tags", "").split(",")]


def _idle_since(t: dict) -> float:
    """Dernier transfert connu (ou la fin du téléchargement si rien n'a jamais été envoyé)."""
    return max(t.get("last_activity") or 0, t.get("completion_on") or 0, t.get("added_on") or 0)


def candidates(cfg: dict, ctx: dict, everything: list[dict], now: float | None = None) -> list[dict]:
    """Torrents qui remplissent toutes les conditions, du plus anciennement inactif au plus récent."""
    now = now or time.time()
    min_seed = max(cfg["inactive_seed_hours"], HR_HOURS) * 3600
    idle_limit = cfg["inactive_days"] * 86400
    out = []
    for t in everything:
        if cfg["own_tag"] not in _tags(t):
            continue
        if t.get("progress", 0) < 1 or (t.get("completion_on") or 0) <= 0:
            continue
        seed = t.get("seeding_time")
        if seed is None or seed < min_seed:  # champ absent (vieux qBittorrent) : on ne touche à rien
            continue
        if now - _idle_since(t) < idle_limit:
            continue
        if (t.get("num_leechs") or 0) > 0 or (t.get("num_incomplete") or 0) > 0:
            continue
        out.append(t)
    out.sort(key=_idle_since)
    return out


def _c411_working(qbit, h: str) -> bool:
    for tr in qbit.trackers(h):
        host = urllib.parse.urlsplit(tr.get("url", "")).hostname or ""
        if "c411" in host and tr.get("status") == 2:
            return True
    return False


def retire_inactive(args, cfg: dict, ctx: dict, now: float | None = None) -> int:
    """Retire les torrents inactifs. Retourne le nombre de torrents traités (ou qui le seraient)."""
    qbit, tracking = ctx["qbit"], ctx["tracking"]
    now = now or time.time()
    action = cfg["inactive_action"]
    qbit.login(quiet=True)
    everything = qbit.torrents()
    found = candidates(cfg, ctx, everything, now)

    today = time.strftime("%Y-%m-%d", time.localtime(now))
    quota = tracking.data.get("inactifs") or {}
    used = quota.get("n", 0) if quota.get("jour") == today else 0
    left = max(cfg["inactive_max_per_day"] - used, 0)
    if not args.dry_run and not left:
        if found:
            log.debug("Inactifs : plafond du jour atteint (%d), %d torrent(s) attendront demain",
                      cfg["inactive_max_per_day"], len(found))
        return 0

    done, names = 0, []
    for t in found:
        if not args.dry_run and done >= left:
            break
        h = t["hash"].lower()
        if not _c411_working(qbit, h):
            log.debug("Inactifs : %s ignoré, aucun tracker c411 ne répond normalement", t["name"])
            continue
        shared = any(o["hash"] != t["hash"] and o.get("content_path") == t.get("content_path") for o in everything)
        if action == "pause":
            what = "mis en pause (tag inactif)"
        elif action == "fichiers" and not shared:
            what = "retiré, fichiers supprimés"
        else:
            what = "retiré, fichiers conservés" + (" (utilisés par un autre torrent)" if shared else "")
        days = int((now - _idle_since(t)) // 86400)
        hours = int(t["seeding_time"] // 3600)
        if args.dry_run:
            log.info("[dry-run] Inactif depuis %d j (%d h de seed) : %s serait %s", days, hours, t["name"], what)
            done += 1
            continue
        try:
            if action == "pause":
                qbit.stop(h)
                qbit.add_tags(h, "inactif")
            else:
                qbit.delete(h, delete_files=(action == "fichiers" and not shared))
        except Exception as e:
            log.error("Inactifs : échec pour %s : %s", t["name"], e)
            continue
        done += 1
        names.append(t["name"])
        log.info("💤 Inactif depuis %d j (%d h de seed) : %s %s", days, hours, t["name"], what)

    if args.dry_run:
        if done > left:
            log.info("[dry-run] Inactifs : %d torrent(s) concernés, %d au maximum seraient retirés aujourd'hui",
                     done, left)
        return done
    if done:
        tracking.data["inactifs"] = {"jour": today, "n": used + done}
        tracking.save()
        if ctx.get("notifier"):
            shown = "\n".join(f"• {n}" for n in names[:10]) + (f"\n… et {len(names) - 10} autre(s)"
                                                                  if len(names) > 10 else "")
            ctx["notifier"].send(f"💤 **{done} torrent(s) inactif(s) retiré(s)** (rien envoyé depuis "
                                 f"{cfg['inactive_days']} j) :\n{shown}", kind="retrait")
    return done


def maybe_inactive(args, cfg: dict, ctx: dict, force: bool = False) -> None:
    if not cfg["inactive"] and not force:
        return
    now = time.monotonic()
    if not force and args.boucle and now - ctx.get("last_inactive", -1e9) < CHECK_EVERY:
        return
    ctx["last_inactive"] = now
    try:
        n = retire_inactive(args, cfg, ctx)
        (log.info if n or not args.boucle else log.debug)(
            "Inactifs : %d torrent(s) %s", n, "concerné(s)" if args.dry_run else "retiré(s)")
    except Exception as e:
        log.error("Retrait des inactifs interrompu : %s", e)
