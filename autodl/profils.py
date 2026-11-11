"""Réglages par catégorie (PROFILS_CATEGORIES) et budget de téléchargement quotidien (BUDGET_JOUR).

Un profil remplace, pour une catégorie, certains réglages généraux. Une ligne par catégorie (ou « ; » entre
deux profils dans le .env) :

    3010: formats=flac taille_max=2Go par_passage=3
    2030: taille_max=15Go seeders_max=10 par_passage=1 budget_jour=30Go
    2000: completes_min=5

La catégorie exacte du torrent (2030) l'emporte sur sa famille (2000). Ce qui n'est pas précisé reste
réglé par la configuration générale.

Budget quotidien : ce que c411 comptera en « reçu » (rien pendant un freeleech, la moitié pour un torrent
à 50 %) est additionné jour par jour. Au-delà de BUDGET_JOUR (ou du budget_jour d'un profil), plus aucun
torrent ne compte jusqu'au lendemain. Les freeleech ne consomment pas de budget.
"""
from __future__ import annotations

import re
import time

from .commun import _human, parse_size

# nom dans le profil -> (clé de la configuration, type)
KEYS: dict[str, tuple[str, str]] = {
    "formats": ("formats", "words"),
    "mots_requis": ("required", "words"),
    "mots_exclus": ("exclude", "words"),
    "taille_min": ("min_size", "size"),
    "taille_max": ("max_size", "size"),
    "completes_min": ("min_completed", "int"),
    "seeders_min": ("min_seeders", "int"),
    "seeders_max": ("max_seeders", "int"),
    "leechers_min": ("min_leechers", "int"),
    "par_passage": ("max_per_run", "int"),
    "budget_jour": ("budget_day", "size"),
}
CAT_RE = re.compile(r"^\d{4}$")


def parse(raw: str) -> dict[str, dict]:
    """Texte des profils -> {catégorie: {clé de configuration: valeur}}. Lève ValueError (message en français)."""
    profiles: dict[str, dict] = {}
    for chunk in re.split(r"[;\n]", raw or ""):
        line = chunk.strip()
        if not line or line.startswith("#"):
            continue
        cat, sep, rest = line.partition(":")
        cat = cat.strip()
        if not sep or not CAT_RE.match(cat):
            raise ValueError(f"PROFILS_CATEGORIES : « {line[:40]} » doit commencer par une catégorie, "
                             "par exemple « 3010: formats=flac »")
        if cat in profiles:
            raise ValueError(f"PROFILS_CATEGORIES : la catégorie {cat} apparaît deux fois")
        profile: dict = {}
        for pair in rest.split():
            name, eq, value = pair.partition("=")
            name = name.strip().lower()
            if not eq or name not in KEYS:
                raise ValueError(f"PROFILS_CATEGORIES ({cat}) : « {pair} » inconnu. Réglages possibles : "
                                 + ", ".join(KEYS))
            key, kind = KEYS[name]
            value = value.strip()
            try:
                if kind == "words":
                    profile[key] = [w.strip().lower() for w in value.split(",") if w.strip()]
                elif kind == "size":
                    profile[key] = parse_size(value)
                else:
                    profile[key] = int(value)
                    if profile[key] < 0:
                        raise ValueError
            except ValueError:
                raise ValueError(f"PROFILS_CATEGORIES ({cat}) : valeur invalide pour {name} ({value})") from None
        profiles[cat] = profile
    return profiles


def match(category: str, profiles: dict) -> str | None:
    """Profil qui s'applique à cette catégorie : exact (2030), sinon la famille (2000)."""
    category = str(category or "")
    if category in profiles:
        return category
    family = category[:1] + "000" if category[:1].isdigit() else ""
    return family if family in profiles else None


def effective(cfg: dict, category: str) -> tuple[dict, str | None]:
    """Configuration qui s'applique à un torrent de cette catégorie, et le profil retenu."""
    key = match(category, cfg.get("profiles") or {})
    if key is None:
        return cfg, None
    return {**cfg, **cfg["profiles"][key]}, key


# ------------------------------------------------------------------ budget quotidien

class Budget:
    """Reçu compté par jour (persistant dans suivi.json), au total et par profil."""

    def __init__(self, tracking, persist: bool = True, now: float | None = None):
        self.tracking, self.persist = tracking, persist
        self.day = time.strftime("%Y-%m-%d", time.localtime(now))
        data = dict(tracking.data.get("budget") or {})
        if data.get("jour") != self.day:
            data = {"jour": self.day, "total": 0, "cats": {}}
        self.data = {"jour": data["jour"], "total": int(data.get("total", 0)), "cats": dict(data.get("cats", {}))}

    def refuse(self, cfg: dict, eff: dict, profile: str | None, counted: int) -> str | None:
        """Raison du refus si ce torrent dépasserait un budget, sinon None."""
        if counted <= 0:
            return None
        limit = cfg.get("budget_day")
        if limit and self.data["total"] + counted > limit:
            return f"budget du jour atteint ({_human(self.data['total'])} sur {_human(limit)})"
        limit = eff.get("budget_day") if profile else None
        if limit and self.data["cats"].get(profile, 0) + counted > limit:
            return f"budget du jour de la catégorie {profile} atteint"
        return None

    def spend(self, profile: str | None, counted: int) -> None:
        if counted <= 0:
            return
        self.data["total"] += counted
        if profile:
            self.data["cats"][profile] = self.data["cats"].get(profile, 0) + counted
        if self.persist:
            self.tracking.data["budget"] = self.data
            self.tracking.save()
