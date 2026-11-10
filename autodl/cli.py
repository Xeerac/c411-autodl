"""Ligne de commande."""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import signal
import sys

from .commun import DATA, HERE, __version__, log
from .config import build_cfg, load_cfg_or_exit
from .contexte import build_context
from .engine import Engine
from .inactifs import maybe_inactive
from .moteur import _safe, _stop, maybe_cleanup, maybe_crossseed, maybe_report, recategorize, run_once
from .reglages import ConfigStore


def parse_args(argv=None) -> argparse.Namespace:
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
    p.add_argument("--inactifs", action="store_true",
                   help="retire tout de suite les torrents inactifs, puis quitte (combinable avec --dry-run)")
    p.add_argument("--bilan", action="store_true",
                   help="affiche (et envoie en notification) le bilan tout de suite, puis quitte")
    p.add_argument("--recategoriser", action="store_true",
                   help="range les torrents déjà présents dans une catégorie par type, puis quitte "
                        "(combinable avec --dry-run)")
    p.add_argument("--garder-emplacement", action="store_true",
                   help="avec --recategoriser : change seulement l'étiquette, aucun fichier n'est déplacé")
    g = p.add_argument_group("interface web")
    g.add_argument("--interface", action="store_true",
                   help="lance l'interface web et le moteur en tâche de fond (nécessite requirements-interface.txt)")
    g.add_argument("--port", type=int, default=8411, help="port de l'interface (défaut : 8411)")
    g.add_argument("--hote", default="127.0.0.1",
                   help="adresse d'écoute (défaut : 127.0.0.1, accessible uniquement depuis la machine)")
    g.add_argument("--lecture-seule", action="store_true",
                   help="moteur en essai à blanc permanent : rien n'est ajouté, supprimé, rangé ni notifié")
    g.add_argument("--desactiver-2fa", action="store_true",
                   help="secours : désactive la double authentification de l'interface (téléphone perdu), puis quitte")
    p.add_argument("--version", action="version", version=f"c411-autodl {__version__}")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(),
                  logging.handlers.RotatingFileHandler(  # 4 fichiers de 5 Mo maximum
                      DATA / "c411_autodl.log", maxBytes=5 * 1024**2, backupCount=3, encoding="utf-8")],
    )


def main(argv=None) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    DATA.mkdir(exist_ok=True)
    for name in ("state.json", "c411_autodl.log"):  # ancienne organisation : fichiers à côté du script
        old = HERE / name
        if old.exists() and not (DATA / name).exists():
            old.replace(DATA / name)

    args = parse_args(argv)
    setup_logging(args.verbose)

    # Configuration : donnees/config.json s'il existe (géré par l'interface), sinon .env + environnement
    store = ConfigStore()

    if args.desactiver_2fa:
        from .web.auth import Auth
        auth = Auth()
        if not auth.has_admin():
            sys.exit("Aucun compte d'interface n'existe encore.")
        if auth.reset_totp():
            log.warning("Double authentification de l'interface désactivée depuis la ligne de commande")
            print("Double authentification désactivée : la connexion ne demande plus que le mot de passe.")
        else:
            print("La double authentification n'était pas activée.")
        return

    if args.interface:
        from .web import serve
        cfg, errors = build_cfg(store.values())
        signal.signal(signal.SIGTERM, _stop)
        log.info("c411-autodl %s : interface web", __version__)
        serve(cfg, errors, store, args.hote, args.port, interval=args.boucle or cfg["boucle"] or 300,
              read_only=args.lecture_seule)
        return

    cfg = load_cfg_or_exit(store.values())
    # Sans option sur la ligne de commande, PAGES et BOUCLE_SECONDES s'appliquent
    if args.pages is None:
        args.pages = cfg["pages"]
    if args.boucle is None:
        args.boucle = cfg["boucle"]

    ctx = build_context(cfg, dry_run=args.dry_run)  # pas de notification pour un essai à blanc
    if args.test_notif:
        if "notifier" not in ctx:
            sys.exit("Aucune notification configurée (DISCORD_WEBHOOK_URL ou TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)"
                     if not args.dry_run else "Pas de notification de test en essai à blanc.")
        ctx["notifier"].send("✅ **c411-autodl** : test de notification réussi.")
        log.info("Notification de test envoyée")
        return

    if args.nettoyage:
        maybe_cleanup(args, cfg, ctx, force=True)
        return
    if args.inactifs:
        maybe_inactive(args, cfg, ctx, force=True)
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
        maybe_inactive(args, cfg, ctx)
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
                                    (f"retrait des inactifs après {cfg['inactive_days']} j", cfg["inactive"]),
                                    ("cross-seed immédiat", cfg["cs_url"]),
                                    (f"bilan quotidien à {cfg['bilan_heure']} h", cfg["bilan"]),
                                    ("mode freeleech", cfg["fl_mode"]),
                                    (f"alerte après {cfg['alert_after']} échecs",
                                     cfg["alert"] and ctx.get("notifier"))) if on]
    if extras:
        log.info("Options actives : %s", ", ".join(extras))
    Engine(cfg, interval=args.boucle, read_only=args.dry_run, ctx=ctx, pages=args.pages,
           rattrapage=args.rattrapage).run_forever()
