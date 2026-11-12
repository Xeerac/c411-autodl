"""Récap quotidien du profil c411 (RECAP_PROFIL) : niveau, classe, quêtes, voies, Zen, ratio, équipe.

Envoyé chaque jour à l'heure du bilan (BILAN_HEURE), dans le salon « Profil » du bot Discord (ou par le
webhook, ou sur Telegram). Comparé au récap de la veille : XP gagnée, quêtes terminées, Zen gagné ou dépensé.
Données de /api/user/profile (clé API avec le scope « Profil (lecture) »).
"""
from __future__ import annotations

import time

from .commun import _human, log

GREEN = 0x2ECC71
VOIES = (("seed", "Seed"), ("upload", "Upload"), ("specialization", "Spécialisation"),
         ("competitivity", "Compétitivité"))
GRADES = {"bronze": "🥉 Bronze", "argent": "🥈 Argent", "or": "🥇 Or"}
SOURCES = {"personal": "personnel", "campaign": "événement du site", "window": "fenêtre freeleech"}
BLOCKED = {"insufficient_balance": "solde insuffisant"}


def bar(done: float, total: float, width: int = 10) -> str:
    filled = round(width * done / total) if total else 0
    return "▰" * max(0, min(width, filled)) + "▱" * (width - max(0, min(width, filled)))


def _delta(now, before, fmt="{:+,}") -> str:
    if before is None or now is None or now == before:
        return ""
    return " (" + fmt.format(now - before).replace(",", " ") + ")"


def snapshot(p: dict) -> dict:
    """Ce qu'on garde pour comparer au lendemain."""
    level = p.get("level") or {}
    progress = (p.get("class") or {}).get("progress") or {}
    zen = p.get("zen") or {}
    up = (p.get("transfer") or {}).get("uploaded") or {}
    return {"jour": time.strftime("%Y-%m-%d"), "level": level.get("level"), "xp": level.get("xp"),
            "quests": progress.get("questsCompleted"), "zen": zen.get("balance"),
            "envoye_reel": up.get("actual")}


def _ratio(up: int | None, down: int | None) -> str:
    if not down:
        return "∞" if up else "–"
    return f"{up / down:.2f}"


def recap_embed(p: dict, prev: dict | None = None) -> dict:
    prev = prev or {}
    level = p.get("level") or {}
    cls = p.get("class")
    zen = p.get("zen") or {}
    transfer = p.get("transfer") or {}
    up, down = transfer.get("uploaded") or {}, transfer.get("downloaded") or {}
    fields = []

    if level:
        into, left = level.get("xpIntoLevel") or 0, level.get("xpToNextLevel") or 0
        span = into + left
        pct = f" · {round(100 * into / span)} %" if span else ""
        fields.append({"name": "🎖️ Niveau", "inline": False, "value":
                       f"**{level.get('level', '?')}**{_delta(level.get('level'), prev.get('level'))}"
                       f" · {into} / {span} XP vers le niveau suivant{pct}\n`{bar(into, span, 16)}`\n"
                       f"XP totale : {level.get('xp', 0):,}".replace(",", " ")
                       + _delta(level.get("xp"), prev.get("xp"))})

    if cls:
        progress = cls.get("progress") or {}
        grade = progress.get("grade") or {}
        stars = "⭐" * int(progress.get("stars") or 0)
        lines = [f"Fondation : **{cls.get('foundation', '?')}**",
                 f"Emblème : {GRADES.get(grade.get('tier'), grade.get('tier', '?'))} {grade.get('level', '')} {stars}".rstrip()]
        if cls.get("treeBonusBp"):
            lines.append(f"Bonus de l'arbre : +{cls['treeBonusBp'] / 100:.2f} %".replace(".", ","))
        fields.append({"name": "🧭 Classe", "value": "\n".join(lines), "inline": True})
        done, total = progress.get("questsCompleted"), progress.get("questsTotal")
        if total:
            fields.append({"name": "📜 Quêtes", "inline": True, "value":
                           f"**{done} / {total}**{_delta(done, prev.get('quests'))}\n`{bar(done, total)}`"})
        voies = cls.get("voies") or {}
        rows = []
        for key, label in VOIES:
            v = voies.get(key) or {}
            d, t = v.get("questsCompleted", 0), v.get("questsTotal", 0)
            rows.append(f"{'⭐' if v.get('star') else '▫️'} **{label}** `{bar(d, t, 8)}` {d}/{t}")
        if rows:
            fields.append({"name": "🛤️ Voies", "value": "\n".join(rows), "inline": False})

    if zen:
        fields.append({"name": "💰 Zen", "inline": True, "value":
                       f"**{zen.get('balance', 0):,}**".replace(",", " ") + _delta(zen.get("balance"), prev.get("zen"))
                       + f"\nGagné : {zen.get('totalEarned', 0):,} · dépensé : {zen.get('totalSpent', 0):,}".replace(",", " ")})

    if up or down:
        credit = up.get("credit") or down.get("credit")
        value = f"Officiel : **{_ratio(up.get('total'), down.get('total'))}**"
        if credit:
            value += f"\nMesuré par le tracker : {_ratio(up.get('actual'), down.get('actual'))}"
        fields.append({"name": "⚖️ Ratio", "value": value, "inline": True})
        sent = f"**{_human(up.get('total', 0))}**"
        if up.get("credit"):
            sent += f"\ndont {_human(up['credit'])} de crédit"
        if up.get("actual") is not None and prev.get("envoye_reel") is not None:
            sent += f"\n+{_human(max(up['actual'] - prev['envoye_reel'], 0))} depuis hier"
        fields.append({"name": "📤 Envoyé", "value": sent, "inline": True})
        received = f"**{_human(down.get('total', 0))}**"
        if down.get("credit"):
            received += f"\n{_human(down['credit'])} de crédit déduit"
        fields.append({"name": "📥 Reçu", "value": received, "inline": True})

    team = p.get("team")
    if team:
        fields.append({"name": "👥 Équipe", "inline": True,
                       "value": f"**{team.get('name', '?')}** [{team.get('tag', '')}] · {team.get('role', '')}".strip()})

    status = []
    dl = p.get("download") or {}
    if dl and not dl.get("allowed", True):
        status.append(f"⛔ Téléchargement bloqué ({BLOCKED.get(dl.get('blockedReason'), dl.get('blockedReason') or '?')})")
    fl = p.get("freeleech") or {}
    if fl.get("active"):
        status.append("🎉 Freeleech actif (" + ", ".join(SOURCES.get(s, s) for s in fl.get("sources") or []) + ")")
    if p.get("silverLeech"):
        status.append("🥈 Silver leech actif")
    if p.get("leechBonuses"):
        status.append(f"🎁 {len(p['leechBonuses'])} bonus de téléchargement")
    if status:
        fields.append({"name": "📌 État du compte", "value": "\n".join(status), "inline": False})

    since = p.get("memberSince", "")[:10]
    desc = f"Membre depuis le {since[8:10]}/{since[5:7]}/{since[:4]}" if len(since) == 10 else None
    embed = {"title": f"👤 Profil c411 de {p.get('username', '?')}", "color": GREEN,
             "fields": [{**f, "value": f["value"][:1024]} for f in fields]}
    if desc:
        embed["description"] = desc
    return embed


def recap_text(p: dict) -> str:
    """Version courte en texte (journal, Telegram)."""
    level = p.get("level") or {}
    zen = (p.get("zen") or {}).get("balance")
    progress = (p.get("class") or {}).get("progress") or {}
    parts = [f"👤 **Profil c411 de {p.get('username', '?')}**"]
    if level:
        parts.append(f"• Niveau {level.get('level')} ({level.get('xpIntoLevel', 0)} XP dans le niveau)")
    if progress.get("questsTotal"):
        parts.append(f"• Quêtes : {progress.get('questsCompleted')} / {progress['questsTotal']}")
    if zen is not None:
        parts.append(f"• Zen : {zen}")
    t = p.get("transfer") or {}
    if t:
        parts.append(f"• Ratio : {_ratio((t.get('uploaded') or {}).get('total'), (t.get('downloaded') or {}).get('total'))}")
    return "\n".join(parts)


def fetch(ctx: dict) -> dict:
    ctx["profile"].ratio()  # lit /api/user/profile et garde la réponse
    return getattr(ctx["profile"], "last_profile", None) or {}


def maybe_recap(args, cfg: dict, ctx: dict, force: bool = False) -> dict | None:
    """Une fois par jour, à BILAN_HEURE (ou tout de suite avec force, sans changer la référence de la veille)."""
    if not cfg.get("profil_recap") and not force:
        return None
    if not cfg.get("profile_key") or (args.dry_run and not force):
        return None
    tracking = ctx["tracking"]
    today = time.strftime("%Y-%m-%d")
    if not force and (time.localtime().tm_hour < cfg["bilan_heure"] or tracking.data.get("profil_date") == today):
        return None
    try:
        profile = fetch(ctx)
    except Exception as e:
        log.warning("Récap du profil impossible : %s", e)
        return None
    if not profile:
        return None
    embed = recap_embed(profile, tracking.data.get("profil_veille"))
    if ctx.get("notifier"):
        ctx["notifier"].send(recap_text(profile), embed=embed, kind="profil")
    log.info("Récap du profil c411 %s", "envoyé" if ctx.get("notifier") else "préparé (aucune notification)")
    if not force:
        tracking.data.update(profil_date=today, profil_veille=snapshot(profile))
        tracking.save()
    return embed
