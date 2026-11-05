"""Accès à c411 : recherche Torznab, téléchargement des .torrent, profil (ratio, freeleech)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .commun import USER_AGENT, _float, _int, log


TORZNAB_NS = "http://torznab.com/schemas/2015/feed"


class C411:
    def __init__(self, base_url: str, api_key: str, delay: float):
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.delay = delay  # pause entre requêtes (limite : 120/min par clé)

    def _get(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.key}",
            "User-Agent": USER_AGENT,
        })
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                time.sleep(self.delay)
                return data
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    log.warning("c411 : limite atteinte (429), pause 60 s")
                    time.sleep(60)
                    continue
                raise
        raise RuntimeError("unreachable")

    def search(self, cats: str, offset: int, limit: int, query: str = "") -> list[dict]:
        params = {"t": "search", "cat": cats, "offset": offset, "limit": limit, "apikey": self.key}
        if query:
            params["q"] = query
        url = f"{self.base}/api?{urllib.parse.urlencode(params)}"
        root = ET.fromstring(self._get(url))
        err = root if root.tag == "error" else None
        if err is not None:
            raise RuntimeError(f"Torznab : {err.get('description') or err.get('code')}")

        items = []
        for it in root.iter("item"):
            attrs = {a.get("name"): a.get("value") for a in it.findall(f"{{{TORZNAB_NS}}}attr")}
            enclosure = it.find("enclosure")
            link = (enclosure.get("url") if enclosure is not None else None) or it.findtext("link")
            size = attrs.get("size") or it.findtext("size") or (enclosure.get("length") if enclosure is not None else None)
            items.append({
                "title": it.findtext("title") or "?",
                "link": link,
                "size": int(size) if size and str(size).isdigit() else 0,
                "infohash": (attrs.get("infohash") or "").lower(),
                "completed": _int(attrs.get("grabs")),
                "seeders": _int(attrs.get("seeders")),
                "leechers": _leechers(attrs),
                "category": attrs.get("category") or it.findtext("category") or "",
                "page": it.findtext("comments") or it.findtext("link") or "",
                # 0 = freeleech (ne compte pas dans le reçu), 0.5 = silver, 1 = normal
                "dl_factor": _float(attrs.get("downloadvolumefactor"), 1.0),
            })
        return items

    def download(self, link: str) -> bytes:
        return self._get(link)

    def exists(self, infohash: str) -> bool | None:
        """Le torrent existe-t-il encore sur c411 ? True / False (404) / None si on ne peut pas savoir."""
        try:
            self._get(f"{self.base}/api/torrents/{infohash}")
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            log.warning("c411 : impossible de vérifier %s (HTTP %d)", infohash[:8], e.code)
            return None
        except Exception as e:
            log.warning("c411 : impossible de vérifier %s (%s)", infohash[:8], e)
            return None

    def ratio(self) -> tuple[float, int, int, bool]:
        """Retourne (ratio, envoyé, reçu, téléchargement autorisé) depuis /api/user/profile."""
        try:
            prof = json.loads(self._get(f"{self.base}/api/user/profile"))
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise RuntimeError("la clé C411_PROFILE_API_KEY n'a pas le scope « Profil (lecture) »") from e
            if e.code == 401:
                raise RuntimeError("clé C411_PROFILE_API_KEY absente ou invalide") from e
            raise
        self.last_profile = prof  # gardé pour le mode freeleech
        up = int(prof["transfer"]["uploaded"]["total"])
        down = int(prof["transfer"]["downloaded"]["total"])
        allowed = bool(prof.get("download", {}).get("allowed", True))
        return (up / down if down else float("inf")), up, down, allowed


def freeleech_sources(profile: dict | None) -> list[str]:
    """Sources du freeleech actif sur le compte (campaign = événement du site, window, personal), sinon []."""
    fl = (profile or {}).get("freeleech") or {}
    if not fl.get("active"):
        return []
    return list(fl.get("sources") or ["actif"])


def _leechers(attrs: dict) -> int:
    """Leechers d'un résultat Torznab : attribut « leechers », sinon « peers » − « seeders »."""
    if attrs.get("leechers") is not None:
        return _int(attrs.get("leechers"))
    peers, seeders = _int(attrs.get("peers")), _int(attrs.get("seeders"))
    if peers < 0 or seeders < 0:
        return -1  # inconnu
    return max(peers - seeders, 0)
