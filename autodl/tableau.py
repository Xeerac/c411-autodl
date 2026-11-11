"""Données du tableau de bord : derniers ajouts, rendement par type, état des services.

Lecture seule. Le résultat est mis en cache quelques secondes : rafraîchir la page n'interroge pas la seedbox
à chaque fois. Utilise sa propre connexion qBittorrent, distincte de celle du moteur.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request

from .commun import USER_AGENT, _human, log
from .contenu import guess_type
from .hitrun import summary as hitrun_summary
from .qbit import QBit

CACHE_SECONDS = 30
TIMEOUT = 10


class Dashboard:
    def __init__(self):
        self._lock = threading.Lock()
        self._cache: dict | None = None
        self._cache_at = 0.0
        self._qbit: QBit | None = None
        self._qbit_key = None
        self._torrents: list[dict] = []

    def data(self, cfg: dict, state) -> dict:
        with self._lock:
            if self._cache and time.time() - self._cache_at < CACHE_SECONDS:
                return self._cache
            self._cache = self._build(cfg, state)
            self._cache_at = time.time()
            return self._cache

    def additions(self, cfg: dict, state) -> dict:
        """Tous les ajouts du programme (page « Ajouts »), avec leur état actuel dans qBittorrent."""
        self.data(cfg, state)  # rafraîchit la lecture de qBittorrent si besoin (cache de 30 s)
        with self._lock:
            by_hash = {t["hash"].lower(): t for t in self._torrents}
        return {"genere_le": time.time(), "ajouts": all_additions(state, by_hash)}

    def invalidate(self) -> None:
        with self._lock:
            self._cache = None

    # ------------------------------------------------------------------ construction

    def _build(self, cfg: dict, state) -> dict:
        torrents, qbit_status = self._qbittorrent(cfg)
        self._torrents = torrents
        own = [t for t in torrents if cfg["own_tag"] in [x.strip() for x in t.get("tags", "").split(",")]]
        services = [qbit_status]
        if cfg["cs_url"]:
            services.append(self._crossseed(cfg))
        if cfg["prowlarr_url"]:
            services.append(self._prowlarr(cfg))
        return {
            "genere_le": time.time(),
            "services": services,
            "ajouts": recent_additions(state, {t["hash"].lower(): t for t in torrents}),
            "types": type_stats(own, state),
            "hitrun": hitrun_summary(own, cfg["own_tag"], limit=6),
            "totaux": {"torrents": len(own), "envoye": sum(int(t.get("uploaded", 0)) for t in own),
                       "envoye_txt": _human(sum(int(t.get("uploaded", 0)) for t in own)),
                       "taille_txt": _human(sum(int(t.get("size", 0)) for t in own))},
        }

    def _qbittorrent(self, cfg: dict) -> tuple[list[dict], dict]:
        status = {"id": "qbittorrent", "nom": "qBittorrent", "ok": False, "detail": ""}
        key = (cfg["qbit_url"], cfg["qbit_user"], cfg["qbit_pass"])
        try:
            if self._qbit is None or self._qbit_key != key:
                self._qbit, self._qbit_key = QBit(*key), key
            self._qbit.login(quiet=True)
            torrents = self._qbit.torrents()
            free = self._qbit.free_space()
        except Exception as e:
            self._qbit = None
            status["detail"] = f"injoignable ({str(e)[:120]})"
            return [], status
        seeding = sum(1 for t in torrents if t.get("state", "").endswith("UP") or t.get("state") == "uploading")
        downloading = sum(1 for t in torrents if "DL" in t.get("state", "") or t.get("state") == "downloading")
        status.update(ok=True, detail=f"{len(torrents)} torrents · {seeding} en seed · {downloading} en téléchargement",
                      extra=f"{_human(free)} libres" if free >= 0 else "")
        return torrents, status

    def _crossseed(self, cfg: dict) -> dict:
        status = {"id": "crossseed", "nom": "cross-seed", "ok": False, "detail": ""}
        try:
            _get(cfg["cs_url"].rstrip("/") + "/api/ping")
            status.update(ok=True, detail="répond")
        except Exception as e:
            status["detail"] = f"injoignable ({str(e)[:120]})"
        return status

    def _prowlarr(self, cfg: dict) -> dict:
        status = {"id": "prowlarr", "nom": "Prowlarr", "ok": False, "detail": ""}
        if not cfg["prowlarr_key"]:
            status["detail"] = "clé API manquante"
            return status
        headers = {"X-Api-Key": cfg["prowlarr_key"]}
        base = cfg["prowlarr_url"].rstrip("/")
        try:
            indexers = json.loads(_get(base + "/api/v1/indexer", headers))
            problems = json.loads(_get(base + "/api/v1/indexerstatus", headers))
        except Exception as e:
            status["detail"] = f"injoignable ({str(e)[:120]})"
            return status
        failing = {p.get("indexerId") for p in problems if p.get("disabledTill")}
        names = [i.get("name", "?") + (" (en erreur)" if i.get("id") in failing else "")
                 for i in indexers if i.get("enable", True)]
        status.update(ok=not failing, detail=f"{len(names)} indexeur(s) : {', '.join(names) or 'aucun'}"
                      )
        return status


def recent_additions(state, by_hash: dict, limit: int = 12) -> list[dict]:
    """Derniers torrents ajoutés par le programme, avec ce qu'ils ont envoyé depuis."""
    entries = sorted(state.seen.items(), key=lambda kv: kv[1].get("added", ""), reverse=True)[:limit]
    out = []
    for h, entry in entries:
        t = by_hash.get(h, {})
        size = int(t.get("size") or entry.get("size") or 0)
        uploaded = int(t.get("uploaded", 0))
        out.append({
            "titre": entry.get("title", "?"), "ajoute_le": entry.get("added", ""),
            "type": entry.get("type") or guess_type(entry.get("title", "")),
            "taille": _human(size) if size else "–", "envoye": _human(uploaded) if t else "–",
            "rendement": round(uploaded / size, 2) if t and size else None,
            "etat": _state_label(t.get("state", "")) if t else "absent de qBittorrent",
            "lien": f"https://c411.org/torrents/{h}",
        })
    return out


def all_additions(state, by_hash: dict) -> list[dict]:
    """Chaque torrent ajouté par le programme, du plus récent au plus ancien."""
    from .hitrun import status as hitrun_status
    out = []
    for h, entry in sorted(state.seen.items(), key=lambda kv: kv[1].get("added", ""), reverse=True):
        t = by_hash.get(h)
        size = int((t or {}).get("size") or entry.get("size") or 0)
        uploaded = int(t.get("uploaded", 0)) if t else 0
        row = {"hash": h, "titre": entry.get("title", "?"), "ajoute_le": entry.get("added", ""),
               "type": entry.get("type") or guess_type(entry.get("title", "")),
               "taille": size, "taille_txt": _human(size) if size else "–",
               "envoye": uploaded, "envoye_txt": _human(uploaded) if t else "–",
               "rendement": round(uploaded / size, 2) if t and size else None,
               "present": bool(t), "lien": f"https://c411.org/torrents/{h}"}
        if t:
            hr = hitrun_status(t)
            row.update(etat=_state_label(t.get("state", "")), categorie=t.get("category", ""),
                       ratio=round(float(t.get("ratio") or 0), 2), seed_h=hr["seed_h"], hitrun=hr["etat"],
                       seeders=t.get("num_complete"), leechers=t.get("num_incomplete"))
        else:
            row.update(etat="absent de qBittorrent", categorie="", ratio=None, seed_h=None, hitrun=None,
                       seeders=None, leechers=None)
        out.append(row)
    return out


def type_stats(torrents: list[dict], state) -> list[dict]:
    """Rendement par type de contenu (envoyé ÷ taille), depuis l'ajout, du meilleur au moins bon."""
    agg: dict[str, list] = {}
    for t in torrents:
        h = t["hash"].lower()
        kind = state.seen.get(h, {}).get("type") or guess_type(t.get("name", ""))
        a = agg.setdefault(kind, [0, 0, 0])
        a[0] += 1
        a[1] += int(t.get("size", 0))
        a[2] += int(t.get("uploaded", 0))
    rows = [{"type": k, "torrents": n, "taille": _human(size), "envoye": _human(up),
             "rendement": round(up / size, 2) if size else 0.0} for k, (n, size, up) in agg.items()]
    rows.sort(key=lambda r: r["rendement"], reverse=True)
    best = max((r["rendement"] for r in rows), default=0) or 1
    for r in rows:
        r["barre"] = round(100 * r["rendement"] / best)
    return rows


STATES = {"uploading": "en seed (envoi)", "stalledUP": "en seed", "forcedUP": "en seed (forcé)",
          "queuedUP": "en attente", "pausedUP": "en pause", "stoppedUP": "arrêté", "downloading": "téléchargement",
          "stalledDL": "téléchargement (bloqué)", "forcedDL": "téléchargement", "metaDL": "récupération",
          "checkingUP": "vérification", "checkingDL": "vérification", "missingFiles": "fichiers manquants",
          "error": "erreur", "moving": "déplacement"}


def _state_label(state: str) -> str:
    return STATES.get(state, state or "?")


def _get(url: str, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


__all__ = ["Dashboard", "recent_additions", "type_stats", "log"]
