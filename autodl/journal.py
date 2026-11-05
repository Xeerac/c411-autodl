"""Journal en mémoire pour l'interface : les derniers messages du programme, consultables en direct.

Chaque message reçoit un numéro croissant : l'interface demande « tout ce qui suit le numéro N ».
Les valeurs secrètes de la configuration (clés, mots de passe) sont masquées avant d'être gardées :
même si un message d'erreur en contenait une, elle n'arriverait jamais dans le navigateur.
"""
from __future__ import annotations

import collections
import logging
import re
import threading

# Catégories de messages, pour les filtres de l'interface
CATEGORIES = {
    "ajout": re.compile(r"^(\+ |\[dry-run\] \+ )"),
    "freeleech": re.compile(r"freeleech", re.IGNORECASE),
    "nettoyage": re.compile(r"Supprimé de c411|Nettoyage", re.IGNORECASE),
    "crossseed": re.compile(r"cross-seed", re.IGNORECASE),
}


class LogBuffer(logging.Handler):
    def __init__(self, capacity: int = 2000):
        super().__init__(level=logging.INFO)
        self._records: collections.deque = collections.deque(maxlen=capacity)
        self._lock_buf = threading.Lock()
        self._next = 1
        self._secrets: list[str] = []

    def set_secrets(self, values) -> None:
        """Valeurs à masquer (les plus longues d'abord, pour ne pas laisser de morceau)."""
        self._secrets = sorted({v for v in values if v and len(v) >= 6}, key=len, reverse=True)

    def mask(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return re.sub(r"(apikey=)[^&\s\"']+", r"\1***", text)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.mask(record.getMessage())
        except Exception:
            return
        category = next((name for name, rx in CATEGORIES.items() if rx.search(message)), "")
        with self._lock_buf:
            self._records.append({"id": self._next, "ts": record.created, "niveau": record.levelname,
                                  "categorie": category, "message": message})
            self._next += 1

    def since(self, last_id: int = 0, limit: int = 500) -> list[dict]:
        with self._lock_buf:
            items = [r for r in self._records if r["id"] > last_id]
        return items[-limit:]


BUFFER = LogBuffer()


def install(secrets=()) -> LogBuffer:
    """Branche le journal en mémoire sur le journal du programme (une seule fois)."""
    root = logging.getLogger()
    if BUFFER not in root.handlers:
        root.addHandler(BUFFER)
    BUFFER.set_secrets(secrets)
    return BUFFER


def secret_values(cfg: dict) -> list[str]:
    from .config import SETTINGS
    return [str(cfg.get(s.key) or "") for s in SETTINGS if s.secret]
