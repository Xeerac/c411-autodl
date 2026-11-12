"""Suivi Hit & Run : où en est chaque torrent récent par rapport à la règle de c411.

Règle de c411 : un torrent est quitte après 72 h de seed OU un ratio de 1,0 sur ce torrent, le compteur
démarrant 24 h après le début du téléchargement. (Système actuellement désactivé sur c411, mais il
peut revenir : autant ne jamais être pris en défaut.)

Un torrent « à risque » est un torrent pas encore quitte qui ne seede pas : en pause, arrêté, en erreur,
fichiers manquants, ou encore en téléchargement plus de 24 h après son ajout.
Seuls les torrents gérés par le programme (tag autodl) sont suivis.
"""
from __future__ import annotations

import time

from .commun import log

HR_SEED = 72 * 3600
HR_RATIO = 1.0
GRACE = 24 * 3600
CHECK_EVERY = 3600

STOPPED = {"pausedUP": "en pause", "stoppedUP": "arrêté", "pausedDL": "en pause", "stoppedDL": "arrêté",
           "error": "en erreur", "missingFiles": "fichiers manquants", "unknown": "état inconnu"}


def _tags(t: dict) -> list[str]:
    return [x.strip() for x in t.get("tags", "").split(",")]


def status(t: dict, now: float | None = None) -> dict:
    """État Hit & Run d'un torrent : quitte, seed, telechargement ou risque."""
    now = now or time.time()
    seed = int(t.get("seeding_time") or 0)
    ratio = float(t.get("ratio") or 0)
    added = t.get("added_on") or now
    out = {"hash": t.get("hash", "").lower(), "nom": t.get("name", "?"), "seed_h": round(seed / 3600, 1),
           "ratio": round(ratio, 2), "progression": min(100, round(100 * max(seed / HR_SEED, ratio / HR_RATIO)))}
    if seed >= HR_SEED or ratio >= HR_RATIO:
        return {**out, "etat": "quitte", "detail": "quitte (72 h de seed ou ratio 1,0 atteint)"}
    state = t.get("state", "")
    if state in STOPPED:
        return {**out, "etat": "risque", "detail": f"{STOPPED[state]} alors qu'il n'est pas encore quitte"}
    if t.get("progress", 0) < 1:
        if now - added > GRACE:
            return {**out, "etat": "risque", "detail": "toujours en téléchargement plus de 24 h après l'ajout"}
        return {**out, "etat": "telechargement", "detail": "en téléchargement"}
    left = max(HR_SEED - seed, 0)
    return {**out, "etat": "seed", "reste_h": round(left / 3600, 1),
            "detail": f"en seed, quitte dans {left // 3600} h (ou au ratio 1,0)"}


def summary(torrents: list[dict], own_tag: str, now: float | None = None, limit: int = 8) -> dict:
    """Compteurs et liste des torrents à surveiller, pour le tableau de bord."""
    rows = [status(t, now) for t in torrents if own_tag in _tags(t)]
    counts = {k: sum(1 for r in rows if r["etat"] == k) for k in ("quitte", "seed", "telechargement", "risque")}
    watch = sorted((r for r in rows if r["etat"] != "quitte"),
                   key=lambda r: (r["etat"] != "risque", r.get("reste_h", 999), -r["progression"]))
    return {"compteurs": counts, "total": len(rows), "a_surveiller": watch[:limit]}


def maybe_alert(args, cfg: dict, ctx: dict, now: float | None = None, force: bool = False) -> list[dict]:
    """Une fois par heure : prévient (une seule fois par torrent) quand un torrent passe « à risque »."""
    if not cfg.get("hr_alert", True) or args.dry_run:
        return []
    mono = time.monotonic()
    if not force and args.boucle and mono - ctx.get("last_hitrun", -1e9) < CHECK_EVERY:
        return []
    ctx["last_hitrun"] = mono
    qbit, tracking = ctx["qbit"], ctx["tracking"]
    qbit.login(quiet=True)
    risky = [r for r in (status(t, now) for t in qbit.torrents(tag=cfg["own_tag"])) if r["etat"] == "risque"]
    known = set(tracking.data.get("hitrun_alertes", []))
    new = [r for r in risky if r["hash"] not in known]
    # on oublie les torrents qui ne sont plus à risque : s'ils le redeviennent, on prévient à nouveau
    tracking.data["hitrun_alertes"] = sorted(r["hash"] for r in risky)
    if new or known - {r["hash"] for r in risky}:
        tracking.save()
    for r in new:
        log.warning("Hit & Run : %s est %s (%s h de seed, ratio %.2f)", r["nom"], r["detail"], r["seed_h"], r["ratio"])
    if new and ctx.get("notifier"):
        lines = "\n".join(f"• {r['nom'][:80]} : {r['detail']} ({r['seed_h']} h de seed, ratio {r['ratio']:.2f})"
                          for r in new[:10])
        more = f"\n… et {len(new) - 10} autre(s)" if len(new) > 10 else ""
        ctx["notifier"].send(f"⚠️ **Hit & Run : {len(new)} torrent(s) à risque**\n{lines}{more}\n"
                             "Relance-les dans qBittorrent : il faut 72 h de seed ou un ratio de 1,0.", kind="hitrun")
    return new
