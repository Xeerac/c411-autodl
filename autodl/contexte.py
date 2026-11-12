"""Préparation des connexions (c411, qBittorrent, notifications) à partir de la configuration."""
from __future__ import annotations

from .c411 import C411
from .commun import DATA
from .notifications import Notifier
from .qbit import QBit
from .stockage import State, Tracking


def build_context(cfg: dict, dry_run: bool = False) -> dict:
    """Objets partagés par toutes les opérations du moteur.

    En essai à blanc (ou en lecture seule), aucune notification n'est configurée : une instance de test
    ne doit jamais écrire sur ton Discord ou ton Telegram.
    """
    ctx = {
        "c411": C411(cfg["c411_url"], cfg["api_key"], cfg["delay"]),
        "profile": C411(cfg["c411_url"], cfg["profile_key"], 0),
        "qbit": QBit(cfg["qbit_url"], cfg["qbit_user"], cfg["qbit_pass"]),
        "state": State(DATA / "state.json"),
        "tracking": Tracking(DATA / "suivi.json"),
    }
    notifier = make_notifier(cfg)
    if notifier.enabled and not dry_run:
        ctx["notifier"] = notifier
    return ctx


def make_notifier(cfg: dict) -> Notifier:
    from .notifications import KINDS
    bot = None
    if cfg.get("bot_on"):
        channels = {kind: cfg[f"bot_channel_{kind}"] for kind in KINDS if cfg.get(f"bot_channel_{kind}")}
        bot = {"token": cfg["bot_token"], "channel": cfg["bot_channel"], "channels": channels}
    return Notifier(cfg["discord_webhook"], cfg["telegram_token"], cfg["telegram_chat"], cfg["notif_pauses"], bot)
