"""Types de contenu et catégories qBittorrent."""
from __future__ import annotations

import re


# Catégories Torznab de c411 -> type de contenu (sert à la catégorie qBittorrent et au bilan)
TYPES_EXACTS = {"7020": "ebook", "7030": "bd", "7010": "presse", "7000": "livre", "3030": "livre-audio"}


TYPES_FAMILLES = {"1": "jeu", "2": "film", "3": "musique", "4": "logiciel", "5": "serie", "6": "adulte",
                  "7": "livre", "8": "autre"}


def qbit_category(kind: str, cfg: dict) -> str:
    """Catégorie qBittorrent : une par type (c411-ebook, c411-bd…) ou une seule (QBIT_CATEGORY)."""
    if cfg.get("cat_par_type"):
        return f"{cfg['cat_prefix']}-{kind}"
    return cfg["qbit_category"]


def content_type(category: str, title: str = "") -> str:
    """Type de contenu d'après la catégorie Torznab (ex : 7030 -> bd, 2030 -> film)."""
    category = (category or "").strip()
    if category in TYPES_EXACTS:
        return TYPES_EXACTS[category]
    if category[:1] in TYPES_FAMILLES:
        return TYPES_FAMILLES[category[:1]]
    return guess_type(title) if title else "autre"


def guess_type(title: str) -> str:
    """Devine le type d'après le titre, pour les torrents ajoutés avant la v1.3 (catégorie inconnue)."""
    t = title.lower()
    if re.search(r"(?<![a-z0-9])(cbz|cbr)(?![a-z0-9])", t):
        return "bd"
    if re.search(r"(?<![a-z0-9])(mp3|m4b|m4a|kbps)(?![a-z0-9])", t):
        return "livre-audio"
    return "ebook"
