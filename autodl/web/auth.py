"""Sécurité de l'interface : compte administrateur, sessions, blocage des tentatives, code d'installation.

- Mot de passe haché avec scrypt (bibliothèque standard), sel aléatoire, comparaison à temps constant.
- Sessions côté serveur (jeton aléatoire dans un cookie HttpOnly, SameSite=Strict), expiration après
  12 h d'inactivité, jeton anti-falsification (CSRF) propre à chaque session.
- 5 échecs de connexion en 15 min depuis une même adresse : blocage de 15 min.
- Premier lancement : la création du compte exige un code d'installation affiché dans le journal du
  programme. Même si quelqu'un atteignait la page avant toi, il ne pourrait pas créer le compte.
- Double authentification optionnelle (codes TOTP à 6 chiffres) : après le mot de passe, un code est
  demandé (5 min et 5 essais au maximum).
- Accès depuis Internet (domaine) : en plus du blocage par adresse, 30 échecs en 15 min, toutes adresses
  confondues, bloquent les connexions venues d'Internet pendant 15 min (le tunnel SSH reste ouvert).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from ..commun import DATA, _save_json, log
from . import totp

SCRYPT = {"n": 2**15, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024, "dklen": 64}
SESSION_IDLE = 12 * 3600
MAX_FAILURES, FAILURE_WINDOW, LOCK_DURATION = 5, 15 * 60, 15 * 60
MAX_REMOTE_FAILURES = 30  # toutes adresses Internet confondues, sur FAILURE_WINDOW
PENDING_TTL, PENDING_TRIES = 5 * 60, 5
MIN_PASSWORD = 10
GLOBAL = "*internet*"


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **SCRYPT)
    return salt.hex(), digest.hex()


def check_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    _, digest = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(digest, digest_hex)


def password_problem(password: str, confirmation: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"Le mot de passe doit faire au moins {MIN_PASSWORD} caractères."
    if password != confirmation:
        return "Les deux mots de passe ne correspondent pas."
    return None


class Auth:
    def __init__(self, path: Path | None = None):
        self.path = path or DATA / "interface.json"
        self.code_path = self.path.with_name("code-installation.txt")
        self._lock = threading.Lock()
        self._sessions: dict[str, dict] = {}
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._pending: dict[str, dict] = {}  # mot de passe validé, code à 6 chiffres attendu
        self.setup_code = None if self.has_admin() else self._setup_code()

    # ------------------------------------------------------------------ compte administrateur

    def has_admin(self) -> bool:
        return self.path.exists()

    def _admin(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _setup_code(self) -> str:
        """Code d'installation : gardé dans donnees/code-installation.txt jusqu'à la création du compte,
        pour qu'il ne change pas à chaque redémarrage."""
        code = ""
        if self.code_path.exists():
            code = self.code_path.read_text(encoding="utf-8").strip().upper()
        if not re.fullmatch(r"[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}", code):
            code = "-".join(secrets.token_hex(2).upper() for _ in range(3))  # ex : 4F2A-91C0-7B3E
            self.code_path.parent.mkdir(parents=True, exist_ok=True)
            self.code_path.write_text(code + "\n", encoding="utf-8")
            try:
                os.chmod(self.code_path, 0o600)
            except OSError:
                pass
        log.warning("Premier lancement de l'interface : code d'installation %s "
                    "(aussi enregistré dans donnees/%s, supprimé une fois ton compte créé)",
                    code, self.code_path.name)
        return code

    def create_admin(self, user: str, password: str, code: str) -> str | None:
        """Crée le compte. Retourne un message d'erreur, ou None si c'est fait."""
        with self._lock:
            if self.has_admin():
                return "Le compte existe déjà."
            if not self.setup_code or not hmac.compare_digest(code.strip().upper(), self.setup_code):
                return "Code d'installation incorrect. Il est affiché dans le journal du programme."
            user = user.strip()
            if not user:
                return "Choisis un nom d'utilisateur."
            salt, digest = hash_password(password)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _save_json(self.path, {"utilisateur": user, "sel": salt, "empreinte": digest,
                                   "cree_le": time.strftime("%Y-%m-%d %H:%M:%S")})
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            self.setup_code = None
            self.code_path.unlink(missing_ok=True)  # le code ne sert plus à rien
            log.info("Compte administrateur de l'interface créé (%s)", user)
            return None

    # ------------------------------------------------------------------ connexion

    def locked(self, client: str, remote: bool = False) -> int:
        """Secondes de blocage restantes pour cette adresse (0 = pas bloquée)."""
        now = time.time()
        until = max(self._locked_until.get(client, 0), self._locked_until.get(GLOBAL, 0) if remote else 0)
        return max(int(until - now), 0)

    def _failure(self, client: str, remote: bool) -> None:
        now = time.time()
        for key, limit in ((client, MAX_FAILURES), *(((GLOBAL, MAX_REMOTE_FAILURES),) if remote else ())):
            recent = [t for t in self._failures.get(key, []) if now - t < FAILURE_WINDOW] + [now]
            self._failures[key] = recent
            if len(recent) >= limit and self._locked_until.get(key, 0) < now:
                self._locked_until[key] = now + LOCK_DURATION
                who = "depuis Internet (toutes adresses)" if key == GLOBAL else f"depuis {client}"
                log.warning("Interface : %d échecs de connexion %s, bloqué %d min", len(recent), who,
                            LOCK_DURATION // 60)

    def login(self, user: str, password: str, client: str, remote: bool = False) -> str | None:
        """Retourne un jeton de session (ou d'attente du code à 6 chiffres), ou None si refusé ou bloqué."""
        with self._lock:
            if self.locked(client, remote) or not self.has_admin():
                return None
            admin = self._admin()
            ok_user = hmac.compare_digest(user.strip(), admin["utilisateur"])
            ok_pass = check_password(password, admin["sel"], admin["empreinte"])  # toujours calculé
            if not (ok_user and ok_pass):
                self._failure(client, remote)
                return None
            self._failures.pop(client, None)
            if admin.get("totp"):
                token = secrets.token_urlsafe(32)
                self._pending = {k: v for k, v in self._pending.items() if time.time() - v["t"] < PENDING_TTL}
                self._pending[token] = {"user": admin["utilisateur"], "t": time.time(), "tries": 0}
                return token
            return self._new_session(admin["utilisateur"])

    def is_pending(self, token: str | None) -> bool:
        p = self._pending.get(token or "")
        return bool(p) and time.time() - p["t"] < PENDING_TTL

    def finish_totp(self, token: str | None, code: str, client: str, remote: bool = False) -> str | None:
        """Deuxième étape : retourne un jeton de session, ou None (code faux, expiré, trop d'essais)."""
        with self._lock:
            p = self._pending.get(token or "")
            if not p or time.time() - p["t"] >= PENDING_TTL or self.locked(client, remote):
                self._pending.pop(token or "", None)
                return None
            admin = self._admin()
            counter = totp.verify(admin.get("totp", ""), code, admin.get("totp_dernier", -1))
            if counter is None:
                p["tries"] += 1
                self._failure(client, remote)
                if p["tries"] >= PENDING_TRIES:
                    self._pending.pop(token, None)
                return None
            self._pending.pop(token, None)
            self._update_admin(totp_dernier=counter)
            return self._new_session(p["user"])

    # ------------------------------------------------------------------ double authentification

    def _update_admin(self, **values) -> None:
        admin = self._admin()
        for k, v in values.items():
            if v is None:
                admin.pop(k, None)
            else:
                admin[k] = v
        _save_json(self.path, admin)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def totp_enabled(self) -> bool:
        return self.has_admin() and bool(self._admin().get("totp"))

    def enable_totp(self, secret: str, code: str) -> bool:
        """Active la double authentification si le code prouve que l'application est bien configurée."""
        with self._lock:
            counter = totp.verify(secret, code)
            if counter is None:
                return False
            self._update_admin(totp=secret, totp_dernier=counter, totp_le=time.strftime("%Y-%m-%d %H:%M:%S"))
            log.info("Interface : double authentification activée")
            return True

    def disable_totp(self, password: str, code: str) -> bool:
        with self._lock:
            admin = self._admin()
            if not check_password(password, admin["sel"], admin["empreinte"]):
                return False
            if totp.verify(admin.get("totp", ""), code, admin.get("totp_dernier", -1)) is None:
                return False
            self._update_admin(totp=None, totp_dernier=None, totp_le=None)
            log.info("Interface : double authentification désactivée")
            return True

    def reset_totp(self) -> bool:
        """Secours (ligne de commande, sur le serveur) : désactive la double authentification."""
        if not self.totp_enabled():
            return False
        self._update_admin(totp=None, totp_dernier=None, totp_le=None)
        return True

    def open_session(self, user: str) -> str:
        """Ouvre une session (juste après la création du compte)."""
        with self._lock:
            return self._new_session(user)

    def _new_session(self, user: str) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = {"user": user, "csrf": secrets.token_urlsafe(32), "seen": time.time()}
        return token

    def session(self, token: str | None) -> dict | None:
        if not token:
            return None
        with self._lock:
            s = self._sessions.get(token)
            if not s:
                return None
            if time.time() - s["seen"] > SESSION_IDLE:
                self._sessions.pop(token, None)
                return None
            s["seen"] = time.time()
            return s

    def logout(self, token: str | None) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)
