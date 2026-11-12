"""Appels à l'API REST de Discord avec le jeton du bot (bibliothèque standard uniquement).

Sert à envoyer les messages dans les salons et à lister les serveurs, salons et rôles pour l'interface.
Les commandes du bot, elles, passent par discord_bot.py (connexion permanente).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .commun import __version__

API = "https://discord.com/api/v10"
# Discord exige ce format d'en-tête pour les bots
USER_AGENT = f"DiscordBot (https://github.com/Xeerac/c411-autodl, {__version__})"
# Lire les salons, envoyer des messages, intégrer des liens (embeds), créer les commandes
PERMISSIONS = 1024 + 2048 + 16384
TEXT_CHANNELS = (0, 5)  # salon textuel, salon d'annonces


class DiscordError(RuntimeError):
    pass


def _request(token: str, method: str, path: str, payload: dict | None = None, retry: bool = True):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method, headers={
        "Authorization": f"Bot {token}", "User-Agent": USER_AGENT, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        if e.code == 429 and retry:  # trop de messages d'un coup : Discord indique combien attendre
            try:
                wait = float(json.loads(e.read() or b"{}").get("retry_after", 1))
            except ValueError:
                wait = 1.0
            time.sleep(min(wait, 10))
            return _request(token, method, path, payload, retry=False)
        raise DiscordError(_explain(e.code)) from None
    except urllib.error.URLError as e:
        raise DiscordError(f"Discord injoignable ({e.reason})") from None


def _explain(code: int) -> str:
    return {401: "jeton du bot refusé (vérifie DISCORD_BOT_TOKEN)",
            403: "le bot n'a pas accès à ce salon (permissions « Voir le salon » et « Envoyer des messages »)",
            404: "serveur ou salon introuvable (le bot y est-il invité ?)"}.get(code, f"erreur Discord HTTP {code}")


def me(token: str) -> dict:
    return _request(token, "GET", "/users/@me")


def invite_url(application_id: str) -> str:
    return (f"https://discord.com/oauth2/authorize?client_id={application_id}"
            f"&scope=bot+applications.commands&permissions={PERMISSIONS}")


def guilds(token: str) -> list[dict]:
    return [{"id": g["id"], "nom": g["name"]} for g in _request(token, "GET", "/users/@me/guilds")]


def channels(token: str, guild: str) -> list[dict]:
    items = _request(token, "GET", f"/guilds/{guild}/channels")
    parents = {c["id"]: c["name"] for c in items if c.get("type") == 4}  # catégories
    out = [{"id": c["id"], "nom": c["name"], "categorie": parents.get(c.get("parent_id") or "", ""),
            "position": c.get("position", 0)} for c in items if c.get("type") in TEXT_CHANNELS]
    out.sort(key=lambda c: (c["categorie"], c["position"]))
    return out


def roles(token: str, guild: str) -> list[dict]:
    items = _request(token, "GET", f"/guilds/{guild}/roles")
    return [{"id": r["id"], "nom": r["name"]} for r in sorted(items, key=lambda r: -r.get("position", 0))
            if r["name"] != "@everyone" and not r.get("managed")]


def send(token: str, channel: str, payload: dict) -> None:
    _request(token, "POST", f"/channels/{channel}/messages", payload)
