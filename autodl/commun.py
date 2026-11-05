"""Éléments partagés : version, journal, chemins, petits utilitaires."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from pathlib import Path


__version__ = "2.1.0"


# Dossier du programme (au-dessus du paquet autodl/) : on y trouve .env et donnees/
HERE = Path(__file__).resolve().parent.parent


DATA = HERE / "donnees"  # historique des ajouts et journal


USER_AGENT = f"c411-autodl/{__version__}"


log = logging.getLogger("c411")


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


def _float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1  # inconnu


def _save_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)  # remplacement atomique : jamais de fichier à moitié écrit


def _human(n: int) -> str:
    if n >= 1024**4:
        return f"{n / 1024**4:.2f} To"
    if n >= 1024**3:
        return f"{n / 1024**3:.2f} Go"
    return f"{n / 1024**2:.1f} Mo"


def _duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d}"
