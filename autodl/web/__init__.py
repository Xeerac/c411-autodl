"""Interface web de c411-autodl (option --interface). Nécessite requirements-interface.txt."""
from __future__ import annotations

from ..commun import log


def serve(cfg: dict, errors: list[str], store, host: str, port: int, interval: int, read_only: bool) -> None:
    try:
        import uvicorn  # noqa: F401

        from .app import create_app
        from .auth import Auth
    except ImportError as e:
        raise SystemExit(f"L'interface nécessite des dépendances supplémentaires ({e.name} manquant) :\n"
                         "  pip install -r requirements-interface.txt\n"
                         "(déjà incluses dans l'image Docker)")
    from ..engine import Engine

    auth = Auth()
    engine = None
    if errors:
        log.warning("Configuration incomplète : le moteur ne démarre pas (%d problème(s), visibles dans l'interface)",
                    len(errors))
    else:
        engine = Engine(cfg, interval=interval, read_only=read_only)
        engine.start()
    if read_only:
        log.warning("LECTURE SEULE : rien ne sera ajouté, supprimé, rangé ni notifié")
    app = create_app(engine, auth, store, errors,
                     engine_factory=lambda c: Engine(c, interval=interval, read_only=read_only))
    log.info("Interface disponible sur http://%s:%d", "localhost" if host in ("127.0.0.1", "0.0.0.0") else host, port)
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False, server_header=False)
    finally:
        if engine:
            engine.stop()
