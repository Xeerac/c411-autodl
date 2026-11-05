"""Stockage de la configuration gérée par l'interface (donnees/config.json).

Ordre de priorité de la configuration :
  1. donnees/config.json, s'il existe (créé par l'interface, à partir du .env au premier lancement) ;
  2. sinon le fichier .env et les variables d'environnement, comme en v1.

Les valeurs sont gardées sous forme de texte, avec les mêmes noms que dans le .env : la lecture et la
vérification passent toujours par config.build_cfg(), quelle que soit la source.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .commun import DATA, HERE, _save_json, log
from .config import BY_ENV, SETTINGS, read_env_file


class ConfigStore:
    def __init__(self, path: Path | None = None, env_path: Path | None = None):
        self.path = path or DATA / "config.json"
        self.env_path = env_path or HERE / ".env"

    def exists(self) -> bool:
        return self.path.exists()

    def values(self) -> dict[str, str]:
        """Valeurs brutes (texte) indexées par nom de .env."""
        if self.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {k: str(v) for k, v in data.get("valeurs", {}).items()}
        return self.env_values()

    def env_values(self) -> dict[str, str]:
        """Le .env, complété par les variables d'environnement (prioritaires, comme en v1)."""
        values = read_env_file(self.env_path) if self.env_path.exists() else {}
        for s in SETTINGS:
            for name in (s.env, *s.aliases):
                if name in os.environ:
                    values[name] = os.environ[name]
        return values

    def import_env(self) -> int:
        """Crée config.json à partir du .env actuel. Retourne le nombre de réglages importés."""
        values = {k: v for k, v in self.env_values().items() if k in BY_ENV or any(k in s.aliases for s in SETTINGS)}
        self.save(values, origine="import du .env")
        log.info("Configuration importée depuis le .env : %d réglages", len(values))
        return len(values)

    def save(self, values: dict[str, str], origine: str = "interface") -> None:
        data = {"version": 1, "modifie_le": time.strftime("%Y-%m-%d %H:%M:%S"), "origine": origine,
                "valeurs": {k: str(v) for k, v in values.items()}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _save_json(self.path, data)
        try:
            os.chmod(self.path, 0o600)  # contient des clés : lisible par le propriétaire seulement
        except OSError:
            pass
