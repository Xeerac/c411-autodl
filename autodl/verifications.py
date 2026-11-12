"""Vérification des services, pour les boutons « Tester » de l'interface.

Chaque test ne fait que lire (aucun ajout, aucune modification), sauf celui des notifications qui envoie
volontairement un message de test. Ils renvoient {"ok": bool, "message": str} : un message en français,
sans jamais inclure de clé ni de mot de passe.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .c411 import C411
from .commun import USER_AGENT, _human
from .contexte import make_notifier
from .qbit import QBit

TIMEOUT = 15


def ok(message: str) -> dict:
    return {"ok": True, "message": message}


def ko(message: str) -> dict:
    return {"ok": False, "message": message}


def _http_problem(e: Exception, what: str) -> dict:
    if isinstance(e, urllib.error.HTTPError):
        hints = {401: "clé ou identifiants refusés", 403: "accès refusé (droits de la clé ?)",
                 404: "adresse introuvable (vérifie l'URL)", 429: "trop de requêtes, réessaie dans une minute"}
        return ko(f"{what} : HTTP {e.code}, {hints.get(e.code, 'erreur du serveur')}.")
    if isinstance(e, urllib.error.URLError):
        return ko(f"{what} injoignable ({e.reason}).")
    return ko(f"{what} : {e}")


def test_c411(cfg: dict) -> dict:
    if not cfg["api_key"]:
        return ko("Renseigne d'abord la clé API Torznab.")
    try:
        c = C411(cfg["c411_url"], cfg["api_key"], 0)
        items = c.search(cfg["cats"], 0, 5)
    except Exception as e:
        return _http_problem(e, "c411")
    return ok(f"Clé Torznab valide : {len(items)} torrent(s) récent(s) lus dans les catégories {cfg['cats']}.")


def test_profil(cfg: dict) -> dict:
    if not cfg["profile_key"]:
        return ko("Renseigne d'abord la clé API Profil.")
    try:
        ratio, up, down, allowed = C411(cfg["c411_url"], cfg["profile_key"], 0).ratio()
    except RuntimeError as e:
        return ko(str(e))
    except Exception as e:
        return _http_problem(e, "Profil c411")
    state = "" if allowed else " Attention : c411 bloque actuellement tes téléchargements."
    return ok(f"Clé Profil valide : ratio {ratio:.2f} ({_human(up)} envoyés, {_human(down)} reçus).{state}")


def test_qbittorrent(cfg: dict) -> dict:
    if not (cfg["qbit_url"] and cfg["qbit_user"] and cfg["qbit_pass"]):
        return ko("Renseigne l'adresse, l'utilisateur et le mot de passe de la WebUI.")
    try:
        q = QBit(cfg["qbit_url"], cfg["qbit_user"], cfg["qbit_pass"])
        q.login(quiet=True)
        version = q._req("app/version").decode()
        count = len(q.torrents())
        free = q.free_space()
    except Exception as e:
        return _http_problem(e, "qBittorrent")
    disk = f", {_human(free)} libres" if free >= 0 else ""
    return ok(f"Connecté à qBittorrent {version} : {count} torrent(s){disk}.")


def test_crossseed(cfg: dict) -> dict:
    if not cfg["cs_url"]:
        return ko("cross-seed n'est pas configuré (adresse vide).")
    base = cfg["cs_url"].rstrip("/")
    try:
        _get(f"{base}/api/ping")
    except Exception as e:
        return _http_problem(e, "cross-seed")
    if not cfg["cs_key"]:
        return ko("cross-seed répond, mais la clé API est vide.")
    # Vérification de la clé sans rien déclencher : un hash qui n'existe pas. Clé refusée = 401,
    # clé acceptée = toute autre réponse (cross-seed ne trouve simplement pas ce torrent).
    req = urllib.request.Request(f"{base}/api/webhook", data=urllib.parse.urlencode({"infoHash": "0" * 40}).encode(),
                                 headers={"X-Api-Key": cfg["cs_key"], "User-Agent": USER_AGENT,
                                          "Content-Type": "application/x-www-form-urlencoded"})
    try:
        urllib.request.urlopen(req, timeout=TIMEOUT).read()
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return ko("cross-seed répond, mais la clé API est refusée.")
    except Exception as e:
        return _http_problem(e, "cross-seed")
    return ok("cross-seed répond et la clé API est acceptée.")


def test_prowlarr(cfg: dict) -> dict:
    if not cfg["prowlarr_url"]:
        return ko("Prowlarr n'est pas configuré (adresse vide).")
    if not cfg["prowlarr_key"]:
        return ko("Renseigne la clé API Prowlarr.")
    base = cfg["prowlarr_url"].rstrip("/")
    try:
        status = json.loads(_get(f"{base}/api/v1/system/status", {"X-Api-Key": cfg["prowlarr_key"]}))
        indexers = json.loads(_get(f"{base}/api/v1/indexer", {"X-Api-Key": cfg["prowlarr_key"]}))
    except Exception as e:
        return _http_problem(e, "Prowlarr")
    names = ", ".join(i.get("name", "?") for i in indexers) or "aucun"
    return ok(f"Prowlarr {status.get('version', '?')} : {len(indexers)} indexeur(s) ({names}).")


def test_notifications(cfg: dict) -> dict:
    notifier = make_notifier(cfg)
    if not notifier.enabled:
        return ko("Aucune notification configurée (webhook Discord ou bot Telegram).")
    from .notifications import KINDS
    notifier.send("✅ **c411-autodl** : test de notification depuis l'interface (webhook principal).")
    # Un message sur chaque webhook propre à un type, pour voir quel salon reçoit quoi (pas de doublon Telegram)
    routed = {}
    for kind, url in notifier.routes.items():
        routed.setdefault(url, []).append(KINDS[kind])
    if routed:
        tg = (notifier.tg_token, notifier.tg_chat)
        notifier.tg_token = notifier.tg_chat = ""
        try:
            for url, labels in routed.items():
                kind = next(k for k, u in notifier.routes.items() if u == url)
                notifier.send(f"✅ **c411-autodl** : test de notification\nCe salon recevra : {', '.join(labels)}.",
                              kind=kind)
        finally:
            notifier.tg_token, notifier.tg_chat = tg
    where = [w for w, on in (("Discord", cfg["discord_webhook"]),
                             ("Telegram", cfg["telegram_token"] and cfg["telegram_chat"])) if on]
    if routed:
        where.append(f"{len(routed)} webhook(s) Discord par type")
    return ok(f"Message de test envoyé sur {' et '.join(where)}. Vérifie qu'il est bien arrivé.")


def _get(url: str, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


# Service -> (fonction, groupe de configuration où le bouton apparaît, libellé du bouton)
SERVICES = {
    "c411": (test_c411, "c411", "Tester la clé Torznab"),
    "profil": (test_profil, "c411", "Tester la clé Profil"),
    "qbittorrent": (test_qbittorrent, "qbittorrent", "Tester la connexion"),
    "crossseed": (test_crossseed, "integrations", "Tester cross-seed"),
    "prowlarr": (test_prowlarr, "integrations", "Tester Prowlarr"),
    "notifications": (test_notifications, "notifications", "Envoyer un message de test"),
}
