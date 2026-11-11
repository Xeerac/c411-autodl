"""Alertes de surveillance, vérifiées une fois par heure : espace disque, tracker c411, certificat SSL.

Chaque alerte n'est envoyée qu'une fois, puis de nouveau seulement si le problème disparaît et revient
(ou une fois par jour pour le certificat qui expire). Rien n'est envoyé en essai à blanc.
"""
from __future__ import annotations

import time

from .commun import _human, log

CHECK_EVERY = 3600
CERT_DAYS = 14
STOPPED = ("pausedUP", "stoppedUP", "pausedDL", "stoppedDL", "queuedUP", "queuedDL", "checkingUP",
           "checkingDL", "checkingResumeData", "moving", "metaDL")


def _send(ctx: dict, text: str) -> None:
    log.warning("%s", text.replace("**", "").replace("\n", " · "))
    if ctx.get("notifier"):
        ctx["notifier"].send(text)


def check_disk(cfg: dict, ctx: dict, memo: dict) -> str | None:
    limit = cfg.get("alert_disk_gb") or 0
    if not limit:
        return None
    free = ctx["qbit"].free_space()
    if free < 0:
        return None
    low = free < limit * 1024**3
    if low and not memo.get("disque"):
        memo["disque"] = True
        return (f"⚠️ **Espace disque bas sur la seedbox** : {_human(free)} libres (seuil d'alerte : {limit} Go).\n"
                f"Les ajouts s'arrêtent d'eux-mêmes sous {cfg['min_free_gb']} Go. Fais de la place ou réduis "
                "INACTIFS_JOURS pour retirer plus tôt les torrents qui n'envoient plus rien.")
    if not low and free > limit * 1024**3 * 1.1:
        memo.pop("disque", None)
    return None


def check_tracker(cfg: dict, ctx: dict, memo: dict) -> str | None:
    """Torrents gérés qui n'ont aucun tracker fonctionnel. Il faut deux vérifications d'affilée
    (une heure d'écart) pour alerter : au démarrage de qBittorrent, les annonces prennent du temps."""
    limit = cfg.get("alert_tracker") or 0
    if not limit:
        return None
    torrents = ctx["qbit"].torrents(tag=cfg["own_tag"])
    broken = [t for t in torrents if not t.get("tracker") and t.get("state") not in STOPPED]
    if len(broken) < limit:
        memo.pop("tracker_vu", None)
        memo.pop("tracker", None)
        return None
    if not memo.get("tracker_vu"):
        memo["tracker_vu"] = True  # premier constat : on attend la prochaine vérification
        return None
    if memo.get("tracker"):
        return None
    memo["tracker"] = True
    names = "\n".join(f"• {t.get('name', '?')[:80]}" for t in broken[:5])
    return (f"⚠️ **Tracker c411 injoignable** pour {len(broken)} torrent(s) depuis plus d'une heure.\n{names}\n"
            "c411 est peut-être en maintenance, ou ta passkey a changé : vérifie l'onglet Trackers dans qBittorrent.")


def check_certificate(cfg: dict, ctx: dict, memo: dict, now: float) -> str | None:
    if not cfg.get("alert_cert", True) or not cfg.get("domain_on"):
        return None
    from .domaine import helper_status
    status = helper_status()
    seen = status.get("vu_le") or 0
    if seen and now - seen > 3 * CHECK_EVERY:
        if memo.get("assistant"):
            return None
        memo["assistant"] = True
        return (f"⚠️ **L'assistant du domaine ne répond plus** depuis {int((now - seen) // 3600)} h : le certificat "
                f"de {cfg['domain']} ne sera pas vérifié. Sur le serveur : systemctl status c411-autodl-domaine.timer")
    memo.pop("assistant", None)
    cert = status.get("certificat") or {}
    if not cert.get("valide") or not cert.get("expire_ts"):
        return None
    days = int((cert["expire_ts"] - now) // 86400)
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    if days >= CERT_DAYS or memo.get("certificat") == today:
        return None
    memo["certificat"] = today
    return (f"⚠️ **Le certificat SSL de {cfg['domain']} expire dans {days} jour(s)** ({cert.get('expire', '?')}).\n"
            "Caddy aurait dû le renouveler : vérifie que le port 80 est joignable (directement ou par Cloudflare), "
            "et regarde journalctl -u caddy.")


def maybe_alerts(args, cfg: dict, ctx: dict, now: float | None = None, force: bool = False) -> list[str]:
    if args.dry_run:
        return []
    mono = time.monotonic()
    if not force and args.boucle and mono - ctx.get("last_alerts", -1e9) < CHECK_EVERY:
        return []
    ctx["last_alerts"] = mono
    now = now or time.time()
    tracking = ctx["tracking"]
    memo = dict(tracking.data.get("alertes") or {})
    before = dict(memo)
    sent = []
    ctx["qbit"].login(quiet=True)
    for check in (lambda: check_disk(cfg, ctx, memo), lambda: check_tracker(cfg, ctx, memo),
                  lambda: check_certificate(cfg, ctx, memo, now)):
        try:
            text = check()
        except Exception as e:
            log.debug("Alerte : vérification impossible (%s)", e)
            continue
        if text:
            _send(ctx, text)
            sent.append(text)
    if memo != before:
        tracking.data["alertes"] = memo
        tracking.save()
    return sent
