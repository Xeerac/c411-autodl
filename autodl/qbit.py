"""Pilotage de qBittorrent via l'API de la WebUI."""
from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request

from .commun import USER_AGENT, log, multipart


class QBit:
    def __init__(self, url: str, user: str, password: str):
        self.base = url.rstrip("/")
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        self.user, self.password = user, password
        self.logged = False  # la session est gardée entre deux passages

    def _req(self, path: str, data: bytes | None = None, ctype: str | None = None) -> bytes:
        headers = {"Referer": self.base, "Origin": self.base, "User-Agent": USER_AGENT}
        if ctype:
            headers["Content-Type"] = ctype
        req = urllib.request.Request(f"{self.base}/api/v2/{path}", data=data, headers=headers)
        try:
            with self.opener.open(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            # Session expirée (403) : on se reconnecte une fois et on réessaie
            if e.code == 403 and self.logged and not path.startswith("auth/"):
                log.debug("qBittorrent : session expirée, reconnexion")
                self.logged = False
                self.login(quiet=True)
                with self.opener.open(req, timeout=60) as r:
                    return r.read()
            raise

    def _form(self, path: str, fields: dict[str, str]) -> bytes:
        return self._req(path, urllib.parse.urlencode(fields).encode(), "application/x-www-form-urlencoded")

    def login(self, quiet: bool = False) -> None:
        if self.logged:  # session déjà ouverte : rien à faire (reconnexion auto si elle expire)
            return
        # qBittorrent < 5.2 répond « Ok. » / « Fails. », les versions récentes une réponse vide.
        try:
            resp = self._form("auth/login", {"username": self.user, "password": self.password})
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"qBittorrent : connexion refusée (HTTP {e.code})") from e
        if resp.strip() == b"Fails.":
            raise RuntimeError("qBittorrent : identifiants refusés")
        try:
            version = self._req("app/version").decode()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"qBittorrent : accès refusé après connexion (HTTP {e.code})") from e
        self.logged = True
        (log.debug if quiet else log.info)("qBittorrent %s connecté", version)

    def hashes(self) -> set[str]:
        return {t["hash"].lower() for t in json.loads(self._req("torrents/info"))}

    def free_space(self) -> int:
        state = json.loads(self._req("sync/maindata")).get("server_state", {})
        return int(state.get("free_space_on_disk", -1))

    def ensure_category(self, name: str, save_path: str) -> None:
        try:
            self._form("torrents/createCategory", {"category": name, "savePath": save_path})
        except urllib.error.HTTPError as e:
            if e.code != 409:  # 409 = existe déjà
                raise

    def torrents(self, tag: str = "") -> list[dict]:
        query = "?" + urllib.parse.urlencode({"tag": tag}) if tag else ""
        return json.loads(self._req("torrents/info" + query))

    def trackers(self, h: str) -> list[dict]:
        return json.loads(self._req("torrents/trackers?" + urllib.parse.urlencode({"hash": h})))

    def delete(self, h: str, delete_files: bool) -> None:
        self._form("torrents/delete", {"hashes": h, "deleteFiles": str(delete_files).lower()})

    def stop(self, h: str) -> None:
        try:
            self._form("torrents/stop", {"hashes": h})  # qBittorrent 5.x
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            self._form("torrents/pause", {"hashes": h})  # qBittorrent 4.x

    def set_category(self, h: str, category: str) -> None:
        self._form("torrents/setCategory", {"hashes": h, "category": category})

    def set_auto_management(self, h: str, enable: bool) -> None:
        self._form("torrents/setAutoManagement", {"hashes": h, "enable": str(enable).lower()})

    def add_tags(self, h: str, tags: str) -> None:
        self._form("torrents/addTags", {"hashes": h, "tags": tags})

    def add(self, filename: str, torrent: bytes, category: str, tags: str, save_path: str, paused: bool) -> None:
        fields = {"category": category, "tags": tags,
                  "paused": str(paused).lower(), "stopped": str(paused).lower()}
        if save_path:
            fields["savepath"] = save_path
        body, ctype = multipart(fields, {"torrents": (filename, torrent)})
        resp = self._req("torrents/add", body, ctype)
        if resp.strip() == b"Fails.":
            raise RuntimeError(f"qBittorrent a refusé le torrent : {resp[:200]!r}")
