"""Codes à usage unique (TOTP, RFC 6238) : Google Authenticator, Aegis, 2FAS, Bitwarden, 1Password…

SHA-1, 6 chiffres, 30 secondes : les réglages que toutes les applications comprennent.
Un code est accepté pendant la période en cours et la précédente ou la suivante (décalage d'horloge),
et jamais deux fois.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

STEP, DIGITS, WINDOW = 30, 6, 1


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    s = secret.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret: str, counter: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def verify(secret: str, code: str, last_counter: int = -1, now: float | None = None) -> int | None:
    """Retourne la période du code s'il est bon (à mémoriser pour refuser sa réutilisation), sinon None."""
    code = "".join(c for c in (code or "") if c.isdigit())
    if len(code) != DIGITS:
        return None
    current = int((now or time.time()) // STEP)
    found = None
    for counter in range(current - WINDOW, current + WINDOW + 1):
        if hmac.compare_digest(code_at(secret, counter), code) and counter > last_counter:
            found = counter  # pas de « break » : même durée quel que soit le résultat
    return found


def uri(secret: str, account: str, issuer: str = "c411-autodl") -> str:
    label = urllib.parse.quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?" + urllib.parse.urlencode(
        {"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": STEP})


def grouped(secret: str) -> str:
    """Clé lisible, par groupes de 4, pour la saisie à la main."""
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))
