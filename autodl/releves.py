"""Relevés quotidiens : ratio, total envoyé et total reçu sur c411, un relevé par jour.

Le relevé est pris chaque jour à l'heure du bilan (BILAN_HEURE), même si le bilan est désactivé.
Le tout premier est pris tout de suite, pour avoir une base de comparaison dès le premier jour.
Il faut la clé API Profil. En essai à blanc ou en lecture seule, rien n'est enregistré.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .commun import DATA, _human, _save_json, log

MAX_DAYS = 3 * 366  # environ trois ans d'historique, quelques dizaines d'octets par jour


class Releves:
    def __init__(self, path: Path | None = None):
        self.path = path or DATA / "releves.json"
        self._lock = threading.Lock()
        self.items: list[dict] = []
        if self.path.exists():
            try:
                self.items = json.loads(self.path.read_text(encoding="utf-8")).get("releves", [])
            except ValueError:
                log.warning("%s illisible, l'historique des relevés repart de zéro", self.path.name)

    def has_day(self, day: str) -> bool:
        return any(r["jour"] == day for r in self.items)

    def add(self, day: str, ratio: float, up: int, down: int, extra: dict | None = None) -> dict:
        entry = {"jour": day, "ts": time.time(), "ratio": round(ratio, 4), "envoye": int(up), "recu": int(down),
                 **(extra or {})}
        with self._lock:
            self.items = [r for r in self.items if r["jour"] != day] + [entry]
            self.items.sort(key=lambda r: r["jour"])
            self.items = self.items[-MAX_DAYS:]
            _save_json(self.path, {"version": 1, "releves": self.items})
        return entry

    def rows(self, limit: int | None = None) -> list[dict]:
        """Relevés du plus récent au plus ancien, chacun comparé au précédent."""
        out, prev = [], None
        for r in self.items:
            out.append(_compare(r, prev))
            prev = r
        out.reverse()
        return out[:limit] if limit else out


def _compare(r: dict, prev: dict | None) -> dict:
    row = {"jour": r["jour"], "ratio": r["ratio"], "envoye": r["envoye"], "recu": r["recu"],
           "envoye_txt": _human(r["envoye"]), "recu_txt": _human(r["recu"])}
    for key in ("ratio", "envoye", "recu"):
        if prev is None:
            row[f"{key}_delta"] = None
            row[f"{key}_pct"] = None
            continue
        delta = r[key] - prev[key]
        row[f"{key}_delta"] = round(delta, 4) if key == "ratio" else int(delta)
        row[f"{key}_pct"] = round(100 * delta / prev[key], 2) if prev[key] else None
    for key in ("envoye", "recu"):
        d = row[f"{key}_delta"]
        row[f"{key}_delta_txt"] = None if d is None else ("+" if d >= 0 else "−") + _human(abs(d))
    return row


def maybe_releve(args, cfg: dict, ctx: dict, force: bool = False) -> dict | None:
    """Prend le relevé du jour s'il est l'heure (ou si aucun relevé n'existe encore)."""
    if not cfg["profile_key"] or args.dry_run:
        return None
    releves: Releves = ctx.setdefault("releves", Releves())
    today = time.strftime("%Y-%m-%d")
    first = not releves.items
    if not force and not first:
        if releves.has_day(today) or time.localtime().tm_hour < cfg["bilan_heure"]:
            return None
    try:
        ratio, up, down, _ = ctx["profile"].ratio()
    except Exception as e:
        log.warning("Relevé quotidien impossible : %s", e)
        return None
    profile = getattr(ctx["profile"], "last_profile", None) or {}
    zen = (profile.get("zen") or {}).get("balance")
    entry = releves.add(today, ratio, up, down, {"zen": zen} if zen is not None else None)
    rows = releves.rows(limit=1)
    pct = rows[0]["ratio_pct"] if rows else None
    log.info("Relevé du %s : ratio %.2f%s, %s envoyés, %s reçus", today, ratio,
             f" ({pct:+.2f} % sur la veille)" if pct is not None else " (premier relevé)",
             _human(up), _human(down))
    return entry
