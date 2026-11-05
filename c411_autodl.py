#!/usr/bin/env python3
"""
c411_autodl - Surveille des catégories c411 (API Torznab) et ajoute automatiquement
dans qBittorrent les torrents qui respectent tes critères, tant que ton ratio le permet.

Aucune dépendance externe : Python 3.9+ uniquement. Configuration dans le fichier .env.

Usage :
    python c411_autodl.py                # un passage
    python c411_autodl.py --dry-run      # montre ce qui serait ajouté, n'ajoute rien
    python c411_autodl.py --boucle       # en continu, un passage toutes les 60 s
    python c411_autodl.py --rattrapage   # parcourt le catalogue au maximum
    python c411_autodl.py --test-notif   # envoie une notification de test

Voir README.md pour le tutoriel complet.
"""
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import logging
import logging.handlers
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

__version__ = "1.3.0"

HERE = Path(__file__).resolve().parent
DATA = HERE / "donnees"  # historique des ajouts et journal
TORZNAB_NS = "http://torznab.com/schemas/2015/feed"
USER_AGENT = f"c411-autodl/{__version__}"

log = logging.getLogger("c411")


# --------------------------------------------------------------------------- config

def load_env(path: Path) -> None:
    """Charge un fichier .env simple (CLE=valeur) sans écraser l'environnement."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        sys.exit(f"Variable manquante dans .env : {name}")
    return value or ""


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def parse_size(raw: str) -> int:
    """« 500Mo », « 2Go », « 1.5 GB », « 800 » (Mo par défaut) -> octets. 0 ou vide = illimité."""
    text = raw.strip().lower().replace(",", ".").replace(" ", "")
    if not text:
        return 0
    units = {"to": 1024**4, "tb": 1024**4, "t": 1024**4, "go": 1024**3, "gb": 1024**3, "g": 1024**3,
             "mo": 1024**2, "mb": 1024**2, "m": 1024**2, "ko": 1024, "kb": 1024, "k": 1024}
    for suffix, mult in units.items():
        if text.endswith(suffix):
            return int(float(text[: -len(suffix)]) * mult)
    return int(float(text) * 1024**2)


def _words(name: str) -> list[str]:
    """Liste séparée par des virgules, en minuscules."""
    return [w.strip().lower() for w in env(name, "").split(",") if w.strip()]


def _regex(name: str):
    raw = env(name, "").strip()
    if not raw:
        return None
    try:
        return re.compile(raw, re.IGNORECASE)
    except re.error as e:
        sys.exit(f"{name} : expression régulière invalide ({e})")


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "oui", "on")


# --------------------------------------------------------------------------- bencode

def _bdecode(data: bytes, i: int = 0):
    """Décodeur bencode minimal. Retourne (valeur, index_fin)."""
    c = data[i:i + 1]
    if c == b"i":
        end = data.index(b"e", i)
        return int(data[i + 1:end]), end + 1
    if c == b"l":
        i += 1
        out = []
        while data[i:i + 1] != b"e":
            v, i = _bdecode(data, i)
            out.append(v)
        return out, i + 1
    if c == b"d":
        i += 1
        out = {}
        while data[i:i + 1] != b"e":
            k, i = _bdecode(data, i)
            start = i
            v, i = _bdecode(data, i)
            out[k] = v
            if k == b"info":
                out[b"__info_span__"] = (start, i)
        return out, i + 1
    if c.isdigit():
        colon = data.index(b":", i)
        n = int(data[i:colon])
        return data[colon + 1:colon + 1 + n], colon + 1 + n
    raise ValueError("bencode invalide")


def infohash_of(torrent: bytes) -> str:
    meta, _ = _bdecode(torrent)
    if not isinstance(meta, dict) or b"__info_span__" not in meta:
        raise ValueError("pas de dictionnaire 'info' dans le .torrent")
    start, end = meta[b"__info_span__"]
    return hashlib.sha1(torrent[start:end]).hexdigest()


# --------------------------------------------------------------------------- HTTP

def multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    for name, (filename, content) in files.items():
        parts.append(
            (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
             f"Content-Type: application/x-bittorrent\r\n\r\n").encode() + content + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


# --------------------------------------------------------------------------- c411

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
        up = int(prof["transfer"]["uploaded"]["total"])
        down = int(prof["transfer"]["downloaded"]["total"])
        allowed = bool(prof.get("download", {}).get("allowed", True))
        return (up / down if down else float("inf")), up, down, allowed


def _float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _leechers(attrs: dict) -> int:
    """Leechers d'un résultat Torznab : attribut « leechers », sinon « peers » − « seeders »."""
    if attrs.get("leechers") is not None:
        return _int(attrs.get("leechers"))
    peers, seeders = _int(attrs.get("peers")), _int(attrs.get("seeders"))
    if peers < 0 or seeders < 0:
        return -1  # inconnu
    return max(peers - seeders, 0)


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1  # inconnu


# --------------------------------------------------------------------------- qBittorrent

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


# --------------------------------------------------------------------------- notifications

class Notifier:
    """Envoie des messages sur Discord (webhook) et/ou Telegram (bot). Tout est optionnel."""

    def __init__(self, discord_webhook: str, tg_token: str, tg_chat: str, pauses: bool):
        self.discord = discord_webhook
        self.tg_token, self.tg_chat = tg_token, tg_chat
        self.pauses = pauses

    @property
    def enabled(self) -> bool:
        return bool(self.discord or (self.tg_token and self.tg_chat))

    def _post(self, url: str, payload: dict) -> None:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
            "Content-Type": "application/json", "User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()

    def send(self, text: str) -> None:
        """Texte au format Markdown simple : **gras** et [titre](lien)."""
        if self.discord:
            try:
                self._post(self.discord, {"content": text[:2000], "flags": 4})  # 4 = pas d'aperçu des liens
            except Exception as e:
                log.warning("Notification Discord échouée : %s", e)
        if self.tg_token and self.tg_chat:
            html = _md_to_html(text)[:4096]
            try:
                self._post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                           {"chat_id": self.tg_chat, "text": html, "parse_mode": "HTML",
                            "disable_web_page_preview": True})
            except Exception as e:
                log.warning("Notification Telegram échouée : %s", e)

    def status(self, text: str) -> None:
        if self.pauses:
            self.send(text)

    def added(self, items: list[dict], total_bytes: int, ratio: float | None) -> None:
        head = f"📥 **{len(items)} torrent(s) ajouté(s) à la seedbox** ({_human(total_bytes)})"
        if ratio is not None:
            head += f" · ratio ≈ {ratio:.2f}"
        lines = [head]
        for it in items[:15]:
            title = it["title"].replace("[", "(").replace("]", ")")
            name = f"[{title}]({it['page']})" if it.get("page") else title
            free = " · freeleech" if it.get("dl_factor") == 0 else ""
            lines.append(f"• {name} — {_human(it['size'])}{free}")
        if len(items) > 15:
            lines.append(f"… et {len(items) - 15} autre(s)")
        self.send("\n".join(lines))


def _md_to_html(text: str) -> str:
    import html
    import re
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', out)
    return out


# --------------------------------------------------------------------------- état local

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


def _save_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)  # remplacement atomique : jamais de fichier à moitié écrit


# --------------------------------------------------------------------------- types de contenu

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


# --------------------------------------------------------------------------- logique

def run_once(args, cfg: dict, ctx: dict) -> int:
    """Un passage complet. Retourne le nombre de torrents ajoutés."""
    c411, qbit, state = ctx["c411"], ctx["qbit"], ctx["state"]
    routine = log.debug if args.boucle else log.info  # en boucle, on ne journalise que l'essentiel

    # Ratio : contrôlé avant de chercher, pour ne rien demander à c411 si on est sous le seuil
    up = down = 0
    if cfg["min_ratio"] > 0:
        ratio, up, down, allowed = ctx["profile"].ratio()
        ctx["last_ratio"] = ratio
        blocked = None
        if not allowed:
            blocked = "c411 bloque les téléchargements sur ton compte"
        elif ratio <= cfg["min_ratio"]:
            blocked = f"ratio {ratio:.2f} ≤ {cfg['min_ratio']:.2f}"
        if blocked:
            if ctx.get("blocked") != blocked:  # on ne le répète pas à chaque minute
                log.warning("En pause : %s", blocked)
                if ctx.get("notifier") and args.boucle:
                    ctx["notifier"].status(f"⏸️ c411-autodl en pause : {blocked}")
            ctx["blocked"] = blocked
            return 0
        if ctx.get("blocked"):
            log.info("Reprise : ratio %.2f > %.2f", ratio, cfg["min_ratio"])
            if ctx.get("notifier"):
                ctx["notifier"].status(f"▶️ c411-autodl reprend : ratio {ratio:.2f} > {cfg['min_ratio']:.2f}")
        ctx["blocked"] = None
        routine("Ratio actuel : %.2f", ratio)

    qbit.login(quiet=bool(args.boucle))
    in_client = qbit.hashes()
    free = qbit.free_space()
    min_free = cfg["min_free_gb"] * 1024**3
    if free >= 0:
        routine("Espace libre seedbox : %.1f Go", free / 1024**3)

    added = skipped = total_bytes = counted_bytes = 0
    added_items: list[dict] = []
    budget_bytes = free - min_free if free >= 0 else None

    for it in _ordered(_scan(c411, args, cfg), cfg):
        if added >= cfg["max_per_run"]:
            log.info("Maximum par passage atteint (%d)", cfg["max_per_run"])
            return _finish(added, skipped, total_bytes, args, ctx, added_items, up, down + counted_bytes)

        h = it["infohash"]
        if h and (h in in_client or state.has(h)):
            continue
        reason = _reject(it, cfg)
        if reason:
            skipped += 1
            log.debug("ignoré (%s) : %s", reason, it["title"])
            continue
        if budget_bytes is not None and it["size"] > budget_bytes:
            log.warning("Plus assez d'espace (marge %d Go) : arrêt", cfg["min_free_gb"])
            return _finish(added, skipped, total_bytes, args, ctx, added_items, up, down + counted_bytes)
        if not it["link"]:
            log.warning("Pas de lien de téléchargement : %s", it["title"])
            continue
        counted = int(it["size"] * it["dl_factor"])  # ce que c411 comptera réellement en reçu
        if cfg["min_ratio"] > 0 and counted and down + counted_bytes + counted > 0:
            projected = up / (down + counted_bytes + counted)
            if projected <= cfg["min_ratio"]:
                skipped += 1
                log.info("ignoré (ratio après téléchargement : %.3f) : %s", projected, it["title"])
                continue

        kind = content_type(it["category"], it["title"])
        category = qbit_category(kind, cfg)
        if args.dry_run:
            log.info("[dry-run] + %s (%s, %d complétés, %d seeders, %s leechers) -> %s",
                     it["title"], _human(it["size"]), it["completed"], it["seeders"],
                     it["leechers"] if it["leechers"] >= 0 else "?", category)
            added += 1
            total_bytes += it["size"]
            counted_bytes += counted
            continue

        try:
            data = c411.download(it["link"])
            h = h or infohash_of(data)
            if h in in_client or state.has(h):
                continue
            known = ctx.setdefault("categories_ok", set())
            if category not in known:  # créée une fois par catégorie (409 si elle existe déjà)
                qbit.ensure_category(category, cfg["qbit_savepath"])
                known.add(category)
            qbit.add(f"{h}.torrent", data, category, cfg["qbit_tags"],
                     cfg["qbit_savepath"], cfg["qbit_paused"])
        except Exception as e:  # on continue avec les suivants
            log.error("Échec pour %s : %s", it["title"], e)
            continue

        state.add(h, it["title"], kind, it["size"])
        state.save()
        in_client.add(h)
        if budget_bytes is not None:
            budget_bytes -= it["size"]
        added += 1
        total_bytes += it["size"]
        counted_bytes += counted
        added_items.append(it)
        log.info("+ %s (%s, %d complétés, %d seeders, %s leechers)", it["title"], _human(it["size"]),
                 it["completed"], it["seeders"], it["leechers"] if it["leechers"] >= 0 else "?")

    return _finish(added, skipped, total_bytes, args, ctx, added_items, up, down + counted_bytes)


MAX_PAGES = 6  # c411 plafonne chaque recherche à 600 résultats (offset max 500)


def _scan(c411: C411, args, cfg: dict):
    """Enchaîne les recherches Torznab et renvoie chaque torrent une seule fois.

    Passage normal : une recherche toutes catégories confondues, sur --pages pages.
    Rattrapage : une recherche par catégorie et par mot-clé, chacune jusqu'à 600 résultats,
    pour contourner le plafond de c411.
    """
    if args.rattrapage:
        cats = [c.strip() for c in cfg["cats"].split(",") if c.strip()]
        searches = [(c, q) for c in cats for q in [""] + cfg["queries"]]
        pages = MAX_PAGES
    else:
        searches = [(cfg["cats"], "")]
        pages = min(args.pages, MAX_PAGES)

    seen: set[str] = set()
    for cats, query in searches:
        label = f"cat {cats}" + (f", « {query} »" if query else "")
        found = 0
        for page in range(pages):
            items = c411.search(cats, page * cfg["page_size"], cfg["page_size"], query)
            new = [it for it in items if (it["infohash"] or it["link"] or it["title"]) not in seen]
            for it in new:
                seen.add(it["infohash"] or it["link"] or it["title"])
            found += len(new)
            for it in new:
                yield it
            if len(items) < cfg["page_size"] or not new:
                break
        (log.debug if args.boucle else log.info)(
            "Recherche %s : %d nouveaux torrents (%d au total)", label, found, len(seen))


def _ordered(items, cfg: dict):
    """TRI=interet : traite d'abord les torrents les plus demandés (beaucoup de leechers pour peu
    de seeders), ceux qui rapporteront le plus d'upload. TRI=recent : ordre de c411 (plus récents d'abord)."""
    if cfg["tri"] != "interet":
        yield from items
        return
    items = list(items)
    # Tri stable : à intérêt égal, l'ordre de c411 (le plus récent d'abord) est conservé
    items.sort(key=_interest, reverse=True)
    yield from items


def _interest(it: dict) -> float:
    leechers = max(it.get("leechers", -1), 0)
    seeders = max(it.get("seeders", -1), 0)
    return (leechers + 1) / (seeders + 1)


def _has_token(title: str, token: str) -> bool:
    """Le mot apparaît-il dans le titre comme un élément à part (« [EPUB] », « .epub », « -EPUB- ») ?"""
    return re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", title) is not None


def _group(title: str) -> str:
    """Groupe de release : ce qui suit le dernier tiret (« …[EPUB]-NOTAG » -> « notag »)."""
    m = re.search(r"-\s*([A-Za-z0-9_.]+)\s*$", title)
    return m.group(1).lower() if m else ""


def _reject(it: dict, cfg: dict) -> str | None:
    if it["completed"] < cfg["min_completed"]:
        return "complétés" if it["completed"] >= 0 else "complétés inconnu"
    if it["seeders"] >= 0 and it["seeders"] < cfg["min_seeders"]:
        return "seeders"
    if cfg["max_seeders"] and it["seeders"] > cfg["max_seeders"]:
        return "trop de seeders"
    if cfg["min_leechers"] and it.get("leechers", -1) < cfg["min_leechers"]:
        return "pas assez de leechers"
    if cfg["max_size"] and it["size"] > cfg["max_size"]:
        return "trop gros"
    if cfg["min_size"] and it["size"] < cfg["min_size"]:
        return "trop petit"
    title = it["title"].lower()
    if any(w in title for w in cfg["exclude"]):
        return "mot exclu"
    if cfg["formats"] and not any(_has_token(title, f) for f in cfg["formats"]):
        return "format non accepté"
    if cfg["required"] and not any(w in title for w in cfg["required"]):
        return "aucun mot requis"
    if cfg["excluded_groups"] and _group(it["title"]) in cfg["excluded_groups"]:
        return "groupe exclu"
    if cfg["exclude_regex"] and cfg["exclude_regex"].search(it["title"]):
        return "regex d'exclusion"
    return None


def _human(n: int) -> str:
    if n >= 1024**3:
        return f"{n / 1024**3:.2f} Go"
    return f"{n / 1024**2:.1f} Mo"


# --------------------------------------------------------------------------- nettoyage

# Messages renvoyés par un tracker quand le torrent n'existe plus (c411 : « Torrent removed by its uploader »)
REMOVED_RE = re.compile(r"removed|unregistered|not registered|not found|deleted|supprim|inexistant|introuvable",
                        re.IGNORECASE)


def cleanup(args, cfg: dict, ctx: dict) -> int:
    """Retire de qBittorrent les torrents supprimés de c411. Retourne le nombre de torrents traités.

    Un torrent n'est retiré que si DEUX signaux concordent : les trackers c411 de qBittorrent signalent
    sa suppression ET l'API c411 répond 404. Une panne de c411 ne peut donc rien supprimer.
    """
    qbit, c411 = ctx["qbit"], ctx["c411"]
    action = cfg["cleanup_action"]
    qbit.login(quiet=True)
    everything = qbit.torrents()
    scope = [t for t in everything if cfg["own_tag"] in [x.strip() for x in t.get("tags", "").split(",")]]
    log.debug("Nettoyage : vérification de %d torrents (tag « %s »)", len(scope), cfg["own_tag"])

    done = 0
    for t in scope:
        h = t["hash"].lower()
        c411_trackers = [tr for tr in qbit.trackers(h)
                         if "c411" in (urllib.parse.urlsplit(tr.get("url", "")).hostname or "")]
        if not c411_trackers:
            continue
        # Au moins un tracker c411 signale la suppression, et aucun ne fonctionne (statut 2 = OK)
        if any(tr.get("status") == 2 for tr in c411_trackers):
            continue
        removed_msg = next((tr["msg"] for tr in c411_trackers if REMOVED_RE.search(tr.get("msg") or "")), None)
        if not removed_msg:
            continue
        if c411.exists(h) is not False:  # confirmation par l'API : seul un 404 compte
            log.info("Nettoyage : %s signalé « %s » mais toujours présent sur c411, on ne touche à rien",
                     t["name"], removed_msg)
            continue

        # Fichiers partagés avec un autre torrent (cross-seed sur un autre tracker) : on les garde
        shared = any(o["hash"] != t["hash"] and o.get("content_path") == t.get("content_path") for o in everything)
        if action == "pause":
            what = "mis en pause (tag c411-supprime)"
        elif action == "fichiers" and not shared:
            what = "retiré, fichiers supprimés"
        else:
            what = "retiré, fichiers conservés" + (" (utilisés par un autre torrent)" if shared else "")

        if args.dry_run:
            log.info("[dry-run] Supprimé de c411 (« %s ») : %s serait %s", removed_msg, t["name"], what)
            done += 1
            continue
        try:
            if action == "pause":
                qbit.stop(h)
                qbit.add_tags(h, "c411-supprime")
            else:
                qbit.delete(h, delete_files=(action == "fichiers" and not shared))
        except Exception as e:
            log.error("Nettoyage : échec pour %s : %s", t["name"], e)
            continue
        done += 1
        log.info("🗑️ Supprimé de c411 (« %s ») : %s %s", removed_msg, t["name"], what)
        if ctx.get("notifier"):
            ctx["notifier"].send(f"🗑️ **Supprimé de c411** ({removed_msg}) : {t['name']}, {what}.")
    return done


def _safe(func, *args):
    """Une fonction annexe qui échoue ne doit jamais arrêter le programme."""
    try:
        return func(*args)
    except Exception as e:
        log.error("%s interrompu : %s", func.__name__, e)
        return None


def maybe_cleanup(args, cfg: dict, ctx: dict, force: bool = False) -> None:
    if not cfg["cleanup"] and not force:
        return
    now = time.monotonic()
    if not force and args.boucle and now - ctx.get("last_cleanup", -1e9) < cfg["cleanup_minutes"] * 60:
        return
    ctx["last_cleanup"] = now
    try:
        n = cleanup(args, cfg, ctx)
        (log.info if n or not args.boucle else log.debug)("Nettoyage terminé : %d torrent(s) supprimé(s) de c411", n)
    except Exception as e:
        log.error("Nettoyage interrompu : %s", e)


# --------------------------------------------------------------------------- cross-seed

def maybe_crossseed(args, cfg: dict, ctx: dict) -> int:
    """Prévient cross-seed dès qu'un torrent ajouté par le programme a fini de télécharger.

    cross-seed cherche alors tout de suite la même release sur les autres trackers, au lieu
    d'attendre son prochain passage : on y arrive parmi les premiers seeders.
    """
    if not cfg["cs_url"]:
        return 0
    tracking = ctx["tracking"]
    sent = set(tracking.data.get("crossseed_envoyes", []))
    qbit = ctx["qbit"]
    qbit.login(quiet=True)
    complete = [t["hash"].lower() for t in qbit.torrents(tag=cfg["own_tag"]) if t.get("progress", 0) >= 1]

    if not tracking.data.get("crossseed_init"):
        # Premier lancement : les torrents déjà terminés sont couverts par la recherche quotidienne de
        # cross-seed, on ne les lui renvoie pas tous d'un coup
        if args.dry_run:
            log.info("[dry-run] cross-seed : %d torrents déjà terminés seraient marqués comme couverts",
                     len(complete))
            return 0
        tracking.data["crossseed_init"] = True
        tracking.data["crossseed_envoyes"] = sorted(set(complete) | sent)
        tracking.save()
        log.info("cross-seed : activé. %d torrents déjà terminés ne seront pas renvoyés", len(complete))
        return 0

    todo = [h for h in complete if h not in sent]
    done = 0
    for h in todo:
        if args.dry_run:
            log.info("[dry-run] cross-seed serait prévenu pour %s", h[:8])
            continue
        try:
            _crossseed_webhook(cfg, h)
        except urllib.error.HTTPError as e:
            log.error("cross-seed : refusé pour %s (HTTP %d%s)", h[:8], e.code,
                      " : vérifie CROSS_SEED_API_KEY" if e.code == 401 else "")
            if e.code == 401:
                break
            continue
        except Exception as e:  # cross-seed arrêté ou injoignable : on réessaiera au prochain passage
            if not ctx.get("cs_down"):
                log.warning("cross-seed injoignable (%s) : on réessaiera plus tard", e)
            ctx["cs_down"] = True
            break
        ctx["cs_down"] = False
        sent.add(h)
        done += 1
    if done:
        tracking.data["crossseed_envoyes"] = sorted(sent)
        tracking.save()
        log.info("cross-seed : %d torrent(s) terminé(s) envoyé(s) pour recherche immédiate", done)
    return done


def _crossseed_webhook(cfg: dict, infohash: str) -> None:
    req = urllib.request.Request(
        f"{cfg['cs_url'].rstrip('/')}/api/webhook",
        data=urllib.parse.urlencode({"infoHash": infohash}).encode(),
        headers={"X-Api-Key": cfg["cs_key"], "Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


# --------------------------------------------------------------------------- bilan quotidien

def build_report(cfg: dict, ctx: dict) -> tuple[str, dict]:
    """Bilan depuis le dernier relevé. Retourne (texte au format Markdown simple, nouveau relevé)."""
    qbit, state, tracking = ctx["qbit"], ctx["state"], ctx["tracking"]
    qbit.login(quiet=True)
    torrents = qbit.torrents(tag=cfg["own_tag"])
    snap = tracking.data.get("bilan") or {}
    prev_up, prev_down = snap.get("uploaded", {}), snap.get("downloaded", {})
    since = snap.get("time")

    up_delta = down_delta = 0
    by_type: dict[str, list] = {}
    top = []
    for t in torrents:
        h = t["hash"].lower()
        du = max(int(t.get("uploaded", 0)) - int(prev_up.get(h, 0)), 0)
        dd = max(int(t.get("downloaded", 0)) - int(prev_down.get(h, 0)), 0)
        up_delta += du
        down_delta += dd
        if du:
            top.append((du, t["name"]))
        kind = state.seen.get(h, {}).get("type") or guess_type(t["name"])
        agg = by_type.setdefault(kind, [0, 0, 0])  # [nombre, taille, envoyé depuis l'ajout]
        agg[0] += 1
        agg[1] += int(t.get("size", 0))
        agg[2] += int(t.get("uploaded", 0))

    added = 0
    for entry in state.seen.values():
        try:
            when = time.mktime(time.strptime(entry.get("added", ""), "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            continue
        if since is None or when >= since:
            added += 1

    period = "depuis le " + time.strftime("%d/%m à %H:%M", time.localtime(since)) if since else "depuis le début"
    lines = [f"📊 **Bilan c411-autodl** ({period})",
             f"• {added} torrent(s) ajouté(s) · {_human(down_delta)} téléchargés · **{_human(up_delta)} envoyés**"]

    new_snap = {"time": time.time(),
                "uploaded": {t["hash"].lower(): int(t.get("uploaded", 0)) for t in torrents},
                "downloaded": {t["hash"].lower(): int(t.get("downloaded", 0)) for t in torrents}}
    if cfg["profile_key"]:
        try:
            ratio, _, _, _ = ctx["profile"].ratio()
            new_snap["ratio"] = ratio
            evolution = f" ({ratio - snap['ratio']:+.2f})" if "ratio" in snap else ""
            lines.append(f"• Ratio c411 : {ratio:.2f}{evolution}")
        except Exception as e:
            log.warning("Bilan : ratio indisponible (%s)", e)

    if by_type:
        lines.append("**Rendement par type** (envoyé ÷ taille, depuis l'ajout) :")
        ranked = sorted(by_type.items(), key=lambda kv: kv[1][2] / kv[1][1] if kv[1][1] else 0, reverse=True)
        for kind, (n, size, up) in ranked:
            lines.append(f"• {kind} : ×{(up / size if size else 0):.2f} ({n} torrent(s), {_human(up)} envoyés)")
    if top:
        lines.append("**Ce qui a le plus envoyé** :")
        for du, name in sorted(top, reverse=True)[:3]:
            lines.append(f"• {name[:80]} — {_human(du)}")
    return "\n".join(lines), new_snap


def maybe_report(args, cfg: dict, ctx: dict, force: bool = False) -> None:
    """Bilan une fois par jour à BILAN_HEURE (ou tout de suite avec --bilan, sans changer le relevé)."""
    if not cfg["bilan"] and not force:
        return
    tracking = ctx["tracking"]
    today = time.strftime("%Y-%m-%d")
    if not force and (time.localtime().tm_hour < cfg["bilan_heure"] or tracking.data.get("bilan_date") == today):
        return
    try:
        if not force and not tracking.data.get("bilan"):
            # Tout premier relevé : rien à comparer encore, le premier bilan arrivera demain
            _, snap = build_report(cfg, ctx)
            tracking.data.update(bilan=snap, bilan_date=today)
            tracking.save()
            log.info("Bilan : premier relevé enregistré, premier bilan demain vers %d h", cfg["bilan_heure"])
            return
        text, snap = build_report(cfg, ctx)
    except Exception as e:
        log.error("Bilan impossible : %s", e)
        return
    for line in text.replace("**", "").splitlines():
        log.info("%s", line)
    if ctx.get("notifier"):
        ctx["notifier"].send(text)
    if not force:
        tracking.data.update(bilan=snap, bilan_date=today)
        tracking.save()


def _finish(added: int, skipped: int, total_bytes: int, args,
            ctx: dict | None = None, items: list | None = None, up: int = 0, down: int = 0) -> int:
    verb = "seraient ajoutés" if args.dry_run else "ajoutés"
    dl = "à télécharger" if args.dry_run else "téléchargés"
    (log.debug if args.boucle and not added else log.info)(
        "Terminé : %d %s (%s %s), %d ignorés par les filtres",
        added, verb, _human(total_bytes), dl, skipped)
    if items and ctx and ctx.get("notifier"):
        ratio = up / down if up and down else None
        ctx["notifier"].added(items, total_bytes, ratio)
    return added


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    load_env(HERE / ".env")
    DATA.mkdir(exist_ok=True)
    for name in ("state.json", "c411_autodl.log"):  # ancienne organisation : fichiers à côté du script
        old = HERE / name
        if old.exists() and not (DATA / name).exists():
            old.replace(DATA / name)

    p = argparse.ArgumentParser(description="Auto-téléchargement c411 -> qBittorrent")
    p.add_argument("--dry-run", action="store_true", help="n'ajoute rien, affiche seulement")
    p.add_argument("--pages", type=int, default=env_int("PAGES", 1),
                   help="nombre de pages Torznab à parcourir, 6 max (défaut : PAGES ou 1)")
    p.add_argument("--rattrapage", action="store_true",
                   help="parcourt le catalogue au maximum (par catégorie et par mot-clé)")
    # 300 s par défaut : c411 met son flux en cache 5 min, vérifier plus souvent ne sert à rien
    p.add_argument("--boucle", type=int, nargs="?", const=300, default=env_int("BOUCLE_SECONDES", 0),
                   metavar="SECONDES",
                   help="tourne en continu, un passage toutes les N secondes (défaut : 300)")
    p.add_argument("--test-notif", action="store_true", help="envoie une notification de test et quitte")
    p.add_argument("--nettoyage", action="store_true",
                   help="vérifie tout de suite les torrents supprimés de c411, puis quitte (combinable avec --dry-run)")
    p.add_argument("--bilan", action="store_true",
                   help="affiche (et envoie en notification) le bilan tout de suite, puis quitte")
    p.add_argument("--version", action="version", version=f"c411-autodl {__version__}")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(),
                  logging.handlers.RotatingFileHandler(  # 3 fichiers de 5 Mo maximum
                      DATA / "c411_autodl.log", maxBytes=5 * 1024**2, backupCount=3, encoding="utf-8")],
    )

    cfg = {
        "c411_url": env("C411_URL", "https://c411.org"),
        "api_key": env("C411_API_KEY", required=True),
        "cats": env("C411_CATEGORIES", "7020,7030"),
        "page_size": env_int("PAGE_SIZE", 100),
        "queries": [q.strip() for q in env(
            "RATTRAPAGE_MOTS", "epub,pdf,cbz,cbr,mobi,azw3,mp3,m4b,FR,FRENCH,MULTI,NOTAG,Tome,T01"
        ).split(",") if q.strip()],
        "delay": float(env("REQUEST_DELAY", "1")),
        "min_completed": env_int("MIN_COMPLETED", 1),
        "min_seeders": env_int("MIN_SEEDERS", 1),
        # TAILLE_MAX (ex : 500Mo, 2Go) ; MAX_SIZE_MB reste accepté pour les anciens .env
        "max_size": parse_size(env("TAILLE_MAX", "") or env("MAX_SIZE_MB", "0")),
        "exclude": _words("EXCLUDE_WORDS"),
        # Ciblage de l'upload
        "max_seeders": env_int("MAX_SEEDERS", 0),
        "min_leechers": env_int("MIN_LEECHERS", 0),
        "tri": env("TRI", "interet").strip().lower(),
        # Qualité
        "min_size": parse_size(env("TAILLE_MIN", "0")),
        "formats": _words("FORMATS"),
        "required": _words("MOTS_REQUIS"),
        "excluded_groups": _words("GROUPES_EXCLUS"),
        "exclude_regex": _regex("REGEX_EXCLUSION"),
        "max_per_run": env_int("MAX_PER_RUN", 50),
        "min_free_gb": env_int("MIN_FREE_GB", 20),
        "min_ratio": float(env("MIN_RATIO", "2.0").replace(",", ".")),
        "profile_key": env("C411_PROFILE_API_KEY", ""),
        "qbit_url": env("QBIT_URL", required=True),
        "qbit_user": env("QBIT_USER", required=True),
        "qbit_pass": env("QBIT_PASS", required=True),
        "qbit_category": env("QBIT_CATEGORY", "c411-ebook"),
        "qbit_tags": env("QBIT_TAGS", "c411,autodl"),
        "qbit_savepath": env("QBIT_SAVEPATH", ""),
        "qbit_paused": env_bool("QBIT_PAUSED", False),
        # Nettoyage des torrents supprimés de c411 (désactivé par défaut : il supprime des fichiers)
        "cleanup": env_bool("NETTOYAGE_SUPPRIMES", False),
        "cleanup_action": env("NETTOYAGE_ACTION", "fichiers").strip().lower(),
        # Tag des torrents gérés par le programme (nettoyage, cross-seed, bilan)
        "own_tag": env("NETTOYAGE_TAG", "autodl").strip(),
        "cleanup_minutes": env_int("NETTOYAGE_MINUTES", 60),
        # Une catégorie qBittorrent par type (c411-ebook, c411-bd, c411-presse…)
        "cat_par_type": env_bool("QBIT_CATEGORIE_PAR_TYPE", False),
        "cat_prefix": env("QBIT_CATEGORIE_PREFIXE", "c411").strip() or "c411",
        # Déclenchement de cross-seed à la fin de chaque téléchargement
        "cs_url": env("CROSS_SEED_URL", "").strip(),
        "cs_key": env("CROSS_SEED_API_KEY", "").strip(),
        # Bilan quotidien
        "bilan": env_bool("BILAN_QUOTIDIEN", False),
        "bilan_heure": env_int("BILAN_HEURE", 8),
    }
    if cfg["cs_url"] and not cfg["cs_key"]:
        sys.exit("CROSS_SEED_URL est rempli : ajoute aussi CROSS_SEED_API_KEY (commande : cross-seed api-key)")
    if cfg["cleanup_action"] not in ("fichiers", "torrent", "pause"):
        sys.exit("NETTOYAGE_ACTION doit valoir fichiers, torrent ou pause")
    if not cfg["own_tag"]:
        sys.exit("NETTOYAGE_TAG ne peut pas être vide (sinon tous les torrents seraient concernés)")

    if cfg["min_ratio"] > 0 and not cfg["profile_key"]:
        sys.exit("MIN_RATIO est activé : ajoute C411_PROFILE_API_KEY dans .env "
                 "(clé avec le scope « Profil (lecture) »), ou mets MIN_RATIO=0.")

    ctx = {
        "c411": C411(cfg["c411_url"], cfg["api_key"], cfg["delay"]),
        "profile": C411(cfg["c411_url"], cfg["profile_key"], 0),
        "qbit": QBit(cfg["qbit_url"], cfg["qbit_user"], cfg["qbit_pass"]),
        "state": State(DATA / "state.json"),
        "tracking": Tracking(DATA / "suivi.json"),
    }
    notifier = Notifier(env("DISCORD_WEBHOOK_URL"), env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID"),
                        env_bool("NOTIF_PAUSES", True))
    if notifier.enabled and not args.dry_run:  # pas de notification pour un essai à blanc
        ctx["notifier"] = notifier
        if args.test_notif:
            notifier.send("✅ **c411-autodl** : test de notification réussi.")
            log.info("Notification de test envoyée")
            return
    elif args.test_notif:
        sys.exit("Aucune notification configurée (DISCORD_WEBHOOK_URL ou TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID).")

    if args.nettoyage:
        maybe_cleanup(args, cfg, ctx, force=True)
        return
    if args.bilan:
        maybe_report(args, cfg, ctx, force=True)
        return

    if not args.boucle:
        try:
            run_once(args, cfg, ctx)
        except Exception as e:
            log.error("Passage interrompu : %s", e)
            sys.exit(1)
        maybe_cleanup(args, cfg, ctx)
        _safe(maybe_crossseed, args, cfg, ctx)
        maybe_report(args, cfg, ctx)
        return

    log.info("c411-autodl %s", __version__)
    log.info("Démarrage en continu : un passage toutes les %d s (ratio minimum %.2f%s%s). Ctrl+C pour arrêter.",
             args.boucle, cfg["min_ratio"], ", notifications actives" if ctx.get("notifier") else "",
             f", nettoyage des supprimés toutes les {cfg['cleanup_minutes']} min ({cfg['cleanup_action']})"
             if cfg["cleanup"] else "")
    extras = [name for name, on in (("catégorie par type", cfg["cat_par_type"]),
                                    ("cross-seed immédiat", cfg["cs_url"]),
                                    (f"bilan quotidien à {cfg['bilan_heure']} h", cfg["bilan"])) if on]
    if extras:
        log.info("Options actives : %s", ", ".join(extras))
    total_added = errors = 0
    last_beat = time.monotonic()
    try:
        while True:
            start = time.monotonic()
            try:
                total_added += run_once(args, cfg, ctx)
                errors = 0
            except Exception as e:
                errors += 1
                # On signale la première erreur, puis une sur dix pour ne pas inonder le journal
                if errors == 1 or errors % 10 == 0:
                    log.error("Passage interrompu (%d erreur(s) d'affilée) : %s", errors, e)
            # Indépendants du ratio : tournent même quand les ajouts sont en pause
            maybe_cleanup(args, cfg, ctx)
            _safe(maybe_crossseed, args, cfg, ctx)
            maybe_report(args, cfg, ctx)
            if time.monotonic() - last_beat >= 3600:  # signe de vie toutes les heures
                ratio = ctx.get("last_ratio")
                log.info("Toujours actif : %d torrents ajoutés depuis le démarrage%s", total_added,
                         f", ratio {ratio:.2f}" if ratio is not None else "")
                last_beat = time.monotonic()
            # En cas d'erreurs répétées (site ou seedbox injoignable), on espace les essais : 5 min max
            wait = args.boucle * min(2 ** max(errors - 1, 0), 5) if errors else args.boucle
            time.sleep(max(1, wait - (time.monotonic() - start)))
    except KeyboardInterrupt:
        log.info("Arrêt demandé : %d torrents ajoutés depuis le démarrage", total_added)


if __name__ == "__main__":
    main()
