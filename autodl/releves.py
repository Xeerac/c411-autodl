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

    def complete_types(self, day: str, snapshot) -> None:
        """Relevé du jour pris avant la v2.4 (sans le détail par type) : on le complète une fois."""
        entry = next((r for r in self.items if r["jour"] == day), None)
        if entry is None or "types" in entry or getattr(self, "_types_tried", None) == day:
            return
        self._types_tried = day  # un seul essai par jour, même si qBittorrent ne répond pas
        types = snapshot()
        if types:
            with self._lock:
                entry["types"] = types
                _save_json(self.path, {"version": 1, "releves": self.items})

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
    # Par type : rendement cumulé (envoyé ÷ taille) et envoyé dans la journée
    if r.get("types"):
        before = (prev or {}).get("types") or {}
        row["types"] = {}
        for kind, t in r["types"].items():
            day = t["envoye"] - before[kind]["envoye"] if kind in before else None
            row["types"][kind] = {"n": t["n"], "rendement": round(t["envoye"] / t["taille"], 2) if t["taille"] else 0,
                                  "envoye_jour": max(day, 0) if day is not None else None,
                                  "envoye_jour_txt": _human(max(day, 0)) if day is not None else None}
    return row


def _types_snapshot(cfg: dict, ctx: dict) -> dict:
    """Par type de contenu : nombre de torrents, taille et total envoyé (torrents gérés par le programme).

    Comparé d'un jour à l'autre, il donne ce que chaque catégorie a envoyé dans la journée.
    """
    qbit, state = ctx.get("qbit"), ctx.get("state")
    if qbit is None or state is None:
        return {}
    try:
        qbit.login(quiet=True)
        torrents = qbit.torrents(tag=cfg["own_tag"])
    except Exception as e:
        log.debug("Relevé : rendement par type indisponible (%s)", e)
        return {}
    from .contenu import guess_type
    out: dict[str, dict] = {}
    for t in torrents:
        kind = state.seen.get(t["hash"].lower(), {}).get("type") or guess_type(t.get("name", ""))
        agg = out.setdefault(kind, {"n": 0, "taille": 0, "envoye": 0})
        agg["n"] += 1
        agg["taille"] += int(t.get("size", 0))
        agg["envoye"] += int(t.get("uploaded", 0))
    return out


def maybe_releve(args, cfg: dict, ctx: dict, force: bool = False) -> dict | None:
    """Prend le relevé du jour s'il est l'heure (ou si aucun relevé n'existe encore)."""
    if not cfg["profile_key"] or args.dry_run:
        return None
    releves: Releves = ctx.setdefault("releves", Releves())
    today = time.strftime("%Y-%m-%d")
    first = not releves.items
    if not force and not first:
        if releves.has_day(today):
            releves.complete_types(today, lambda: _types_snapshot(cfg, ctx))
            return None
        if time.localtime().tm_hour < cfg["bilan_heure"]:
            return None
    try:
        ratio, up, down, _ = ctx["profile"].ratio()
    except Exception as e:
        log.warning("Relevé quotidien impossible : %s", e)
        return None
    profile = getattr(ctx["profile"], "last_profile", None) or {}
    zen = (profile.get("zen") or {}).get("balance")
    extra = {"zen": zen} if zen is not None else {}
    types = _types_snapshot(cfg, ctx)
    if types:
        extra["types"] = types
    entry = releves.add(today, ratio, up, down, extra or None)
    rows = releves.rows(limit=1)
    pct = rows[0]["ratio_pct"] if rows else None
    log.info("Relevé du %s : ratio %.2f%s, %s envoyés, %s reçus", today, ratio,
             f" ({pct:+.2f} % sur la veille)" if pct is not None else " (premier relevé)",
             _human(up), _human(down))
    return entry
