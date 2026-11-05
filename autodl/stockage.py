"""Données persistantes : historique des ajouts et suivi."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .commun import _save_json, log


class State:
    def __init__(self, path: Path):
        self.path = path
        self.seen: dict[str, dict] = {}
        if path.exists():
            self.seen = json.loads(path.read_text(encoding="utf-8"))

    def has(self, h: str) -> bool:
        return h in self.seen

    def add(self, h: str, title: str, kind: str = "", size: int = 0) -> None:
        entry = {"title": title, "added": time.strftime("%Y-%m-%d %H:%M:%S")}
        if kind:
            entry["type"] = kind
        if size:
            entry["size"] = size
        self.seen[h] = entry

    def save(self) -> None:
        _save_json(self.path, self.seen)


class Tracking:
    """Petites données de suivi persistantes (donnees/suivi.json) : cross-seed, bilan quotidien."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                log.warning("%s illisible, il sera recréé", path.name)

    def save(self) -> None:
        _save_json(self.path, self.data)
