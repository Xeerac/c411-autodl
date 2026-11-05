"""Ligne de commande et boucle principale."""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import signal
import sys
import time

from .c411 import C411
from .commun import DATA, HERE, __version__, log
from .config import load_cfg_or_exit, load_env
from .moteur import _safe, _stop, maybe_cleanup, maybe_crossseed, maybe_report, recategorize, run_once, watchdog
from .notifications import Notifier
from .qbit import QBit
from .stockage import State, Tracking


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    load_env(HERE / ".env")
    DATA.mkdir(exist_ok=True)
    for name in ("state.json", "c411_autodl.log"):  # ancienne organisation : fichiers à côté du script
        old = HERE / name
        if old.exists() and not (DATA / name).exists():
            old.replace(DATA / name)

    p = argparse.ArgumentParser(description="Auto-téléchargement c411 -> qBittorrent")
    p.add_argument("--dry-run", action="store_true", help="n'ajoute rien, affiche seulement")
    p.add_argument("--pages", type=int, default=None,
                   help="nombre de pages Torznab à parcourir, 6 max (défaut : PAGES ou 1)")
    p.add_argument("--rattrapage", action="store_true",
                   help="parcourt le catalogue au maximum (par catégorie et par mot-clé)")
    # 300 s par défaut : c411 met son flux en cache 5 min, vérifier plus souvent ne sert à rien
    p.add_argument("--boucle", type=int, nargs="?", const=300, default=None,
                   metavar="SECONDES",
                   help="tourne en continu, un passage toutes les N secondes (défaut : 300)")
    p.add_argument("--test-notif", action="store_true", help="envoie une notification de test et quitte")
    p.add_argument("--nettoyage", action="store_true",
                   help="vérifie tout de suite les torrents supprimés de c411, puis quitte (combinable avec --dry-run)")
    p.add_argument("--bilan", action="store_true",
                   help="affiche (et envoie en notification) le bilan tout de suite, puis quitte")
    p.add_argument("--recategoriser", action="store_true",
                   help="range les torrents déjà présents dans une catégorie par type, puis quitte "
                        "(combinable avec --dry-run)")
    p.add_argument("--garder-emplacement", action="store_true",
                   help="avec --recategoriser : change seulement l'étiquette, aucun fichier n'est déplacé")
    p.add_argument("--version", action="version", version=f"c411-autodl {__version__}")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(),
                  logging.handlers.RotatingFileHandler(  # 3 fichiers de 5 Mo maximum
                      DATA / "c411_autodl.log", maxBytes=5 * 1024**2, backupCount=3, encoding="utf-8")],
    )

    cfg = load_cfg_or_exit()
    # Sans option sur la ligne de commande, PAGES et BOUCLE_SECONDES du .env s'appliquent
    if args.pages is None:
        args.pages = cfg["pages"]
    if args.boucle is None:
        args.boucle = cfg["boucle"]

    ctx = {
        "c411": C411(cfg["c411_url"], cfg["api_key"], cfg["delay"]),
        "profile": C411(cfg["c411_url"], cfg["profile_key"], 0),
        "qbit": QBit(cfg["qbit_url"], cfg["qbit_user"], cfg["qbit_pass"]),
        "state": State(DATA / "state.json"),
        "tracking": Tracking(DATA / "suivi.json"),
    }
    notifier = Notifier(cfg["discord_webhook"], cfg["telegram_token"], cfg["telegram_chat"], cfg["notif_pauses"])
    if notifier.enabled and not args.dry_run:  # pas de notification pour un essai à blanc
        ctx["notifier"] = notifier
        if args.test_notif:
            notifier.send("✅ **c411-autodl** : test de notification réussi.")
            log.info("Notification de test envoyée")
            return
    elif args.test_notif:
        sys.exit("Aucune notification configurée (DISCORD_WEBHOOK_URL ou TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID).")

    if args.nettoyage:
        maybe_cleanup(args, cfg, ctx, force=True)
        return
    if args.bilan:
        maybe_report(args, cfg, ctx, force=True)
        return
    if args.recategoriser:
        try:
            recategorize(args, cfg, ctx, keep_location=args.garder_emplacement)
        except Exception as e:
            log.error("Rangement interrompu : %s", e)
            sys.exit(1)
        return

    if not args.boucle:
        try:
            run_once(args, cfg, ctx)
        except Exception as e:
            log.error("Passage interrompu : %s", e)
            sys.exit(1)
        maybe_cleanup(args, cfg, ctx)
        _safe(maybe_crossseed, args, cfg, ctx)
        maybe_report(args, cfg, ctx)
        return

    # Docker et systemd arrêtent le programme avec SIGTERM : on le traite comme un Ctrl+C (arrêt propre)
    signal.signal(signal.SIGTERM, _stop)
    log.info("c411-autodl %s", __version__)
    log.info("Démarrage en continu : un passage toutes les %d s (ratio minimum %.2f%s%s). Ctrl+C pour arrêter.",
             args.boucle, cfg["min_ratio"], ", notifications actives" if ctx.get("notifier") else "",
             f", nettoyage des supprimés toutes les {cfg['cleanup_minutes']} min ({cfg['cleanup_action']})"
             if cfg["cleanup"] else "")
    extras = [name for name, on in (("catégorie par type", cfg["cat_par_type"]),
                                    ("cross-seed immédiat", cfg["cs_url"]),
                                    (f"bilan quotidien à {cfg['bilan_heure']} h", cfg["bilan"]),
                                    ("mode freeleech", cfg["fl_mode"]),
                                    (f"alerte après {cfg['alert_after']} échecs",
                                     cfg["alert"] and ctx.get("notifier"))) if on]
    if extras:
        log.info("Options actives : %s", ", ".join(extras))
    total_added = errors = 0
    last_beat = time.monotonic()
    try:
        while True:
            start = time.monotonic()
            try:
                total_added += run_once(args, cfg, ctx)
                errors = watchdog(cfg, ctx, errors)
            except Exception as e:
                errors = watchdog(cfg, ctx, errors, e)
            # Indépendants du ratio : tournent même quand les ajouts sont en pause
            maybe_cleanup(args, cfg, ctx)
            _safe(maybe_crossseed, args, cfg, ctx)
            maybe_report(args, cfg, ctx)
            if time.monotonic() - last_beat >= 3600:  # signe de vie toutes les heures
                ratio = ctx.get("last_ratio")
                log.info("Toujours actif : %d torrents ajoutés depuis le démarrage%s", total_added,
                         f", ratio {ratio:.2f}" if ratio is not None else "")
                last_beat = time.monotonic()
            # En cas d'erreurs répétées (site ou seedbox injoignable), on espace les essais : 5 min max
            wait = args.boucle * min(2 ** max(errors - 1, 0), 5) if errors else args.boucle
            time.sleep(max(1, wait - (time.monotonic() - start)))
    except KeyboardInterrupt:
        log.info("Arrêt demandé : %d torrents ajoutés depuis le démarrage", total_added)
