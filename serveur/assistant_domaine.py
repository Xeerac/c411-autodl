#!/usr/bin/env python3
"""Assistant « domaine » de c411-autodl : tourne sur la machine hôte (root, lancé par systemd).

Il lit la demande déposée par le programme (donnees/domaine/demande.json), dont il n'utilise QUE le nom
de domaine, vérifié par une expression stricte. La configuration Caddy est écrite à partir d'un modèle
fixe : l'interface ne peut jamais injecter autre chose qu'un nom de domaine.

Étapes : écrire /etc/caddy/c411-autodl.caddy, valider TOUTE la configuration Caddy (en cas d'erreur,
l'ancienne est remise), recharger Caddy, vérifier le certificat, puis répondre dans
donnees/domaine/etat.json (adresses de la machine, état du pare-feu, certificat).

Bibliothèque standard uniquement. Installation : serveur/installer_domaine.sh
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VERSION = 1
SNIPPET = Path("/etc/caddy/c411-autodl.caddy")
CADDYFILE = Path("/etc/caddy/Caddyfile")
DOMAIN_RE = re.compile(r"^(?=.{4,253}$)(?!-)([a-z0-9-]{1,63}(?<!-)\.)+[a-z]{2,63}$")
UPSTREAM_RE = re.compile(r"^(127\.0\.0\.1|localhost|\[::1\]):\d{2,5}$")
CLOUDFLARE = ("173.245.48.0/20 103.21.244.0/22 103.22.200.0/22 103.31.4.0/22 141.101.64.0/18 108.162.192.0/18 "
              "190.93.240.0/20 188.114.96.0/20 197.234.240.0/22 198.41.128.0/17 162.158.0.0/15 104.16.0.0/13 "
              "104.24.0.0/14 172.64.0.0/13 131.0.72.0/22 2400:cb00::/32 2606:4700::/32 2803:f800::/32 "
              "2405:b500::/32 2405:8100::/32 2a06:98c0::/29 2c0f:f248::/32")
EMPTY = "# Généré par c411-autodl (assistant domaine) : accès par domaine désactivé.\n"

TEMPLATE = """# Généré par c411-autodl (assistant domaine). Ne pas modifier : réécrit à chaque changement.
{domain} {{
	encode zstd gzip
	# Derrière le proxy Cloudflare, la vraie adresse du visiteur est dans CF-Connecting-IP
	@cloudflare remote_ip {cloudflare}
	handle @cloudflare {{
		reverse_proxy {upstream} {{
			header_up X-Real-IP {{http.request.header.CF-Connecting-IP}}
		}}
	}}
	handle {{
		reverse_proxy {upstream} {{
			header_up X-Real-IP {{remote_host}}
		}}
	}}
	header {{
		-Server
		Strict-Transport-Security "max-age=31536000"
		X-Robots-Tag "noindex, nofollow"
	}}
}}
"""


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def snippet_for(request: dict, upstream: str) -> tuple[str, str]:
    """(contenu du fichier Caddy, domaine retenu). Lève ValueError si la demande n'est pas valable."""
    if not request.get("actif"):
        return EMPTY, ""
    domain = str(request.get("domaine", "")).strip().lower()
    if not DOMAIN_RE.fullmatch(domain):
        raise ValueError("nom de domaine refusé par l'assistant")
    return TEMPLATE.format(domain=domain, upstream=upstream, cloudflare=CLOUDFLARE), domain


def apply(content: str) -> str | None:
    """Écrit le fichier, valide la configuration complète, recharge Caddy. Retourne une erreur ou None."""
    if "c411-autodl.caddy" not in CADDYFILE.read_text(encoding="utf-8"):
        return f"{CADDYFILE} n'importe pas {SNIPPET} : relance serveur/installer_domaine.sh"
    old = SNIPPET.read_text(encoding="utf-8") if SNIPPET.exists() else EMPTY
    if old == content:
        return None
    SNIPPET.write_text(content, encoding="utf-8")
    os.chmod(SNIPPET, 0o644)
    code, out = run(["caddy", "validate", "--config", str(CADDYFILE), "--adapter", "caddyfile"])
    if code != 0:
        SNIPPET.write_text(old, encoding="utf-8")  # on ne laisse jamais une configuration cassée
        last = [line for line in out.splitlines() if line.strip()][-1:] or ["?"]
        return f"Caddy refuse la configuration (rien n'a été changé) : {last[0][:300]}"
    code, out = run(["systemctl", "reload", "caddy"])
    if code != 0:
        SNIPPET.write_text(old, encoding="utf-8")
        run(["systemctl", "reload", "caddy"])
        return f"Rechargement de Caddy impossible (ancienne configuration remise) : {out[:300]}"
    return None


def certificate(domain: str) -> dict:
    """Certificat servi localement par Caddy pour ce domaine, vérifié comme le ferait un navigateur."""
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection(("127.0.0.1", 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as tls:
                cert = tls.getpeercert()
    except ssl.SSLCertVerificationError as e:
        reason = getattr(e, "verify_message", "") or str(e)
        return {"valide": False, "erreur": f"Pas encore de certificat valide ({reason[:120]})."}
    except OSError as e:
        return {"valide": False, "erreur": f"Caddy ne répond pas sur le port 443 ({e})."}
    issuer = dict(x[0] for x in cert.get("issuer", ()))
    expires = ssl.cert_time_to_seconds(cert["notAfter"])
    return {"valide": True, "emetteur": issuer.get("organizationName") or issuer.get("commonName"),
            "expire": datetime.datetime.fromtimestamp(expires).strftime("%d/%m/%Y"), "expire_ts": expires}


def firewall_allows(port: int) -> bool | None:
    """Le port est-il ouvert à tout le monde ? True / False selon ufw, None si ufw n'est pas utilisé."""
    if not shutil.which("ufw"):
        return None
    code, out = run(["ufw", "status"])
    if code != 0 or "Status: active" not in out and "État : actif" not in out:
        return None if code != 0 else True
    for line in out.splitlines():
        cols = line.split()
        if len(cols) >= 3 and "ALLOW" in line and str(port) in cols[0].split("/")[0].split(",") \
                and ("Anywhere" in line or "Partout" in line):
            return True
    return False


def addresses() -> list[str]:
    code, out = run(["ip", "-j", "addr"])
    if code != 0:
        return []
    found = []
    for itf in json.loads(out or "[]"):
        if itf.get("ifname", "").startswith(("docker", "br-", "veth", "lo")):
            continue
        for a in itf.get("addr_info", []):
            if a.get("scope") == "global":
                found.append(a["local"])
    return found


def write_status(path: Path, status: dict) -> None:
    owner = path.parent.stat()
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".etat-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o644)
    os.chown(tmp, owner.st_uid, owner.st_gid)  # lisible par le programme (utilisateur du conteneur)
    os.replace(tmp, path)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--donnees", required=True, help="dossier donnees/ de c411-autodl")
    p.add_argument("--amont", default="127.0.0.1:8411", help="adresse locale de l'interface (défaut : 127.0.0.1:8411)")
    args = p.parse_args()
    if not UPSTREAM_RE.fullmatch(args.amont):
        sys.exit("--amont doit être une adresse locale, par exemple 127.0.0.1:8411")
    base = Path(args.donnees) / "domaine"
    base.mkdir(parents=True, exist_ok=True)
    try:
        request = json.loads((base / "demande.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        request = {"actif": False}

    code, version = run(["caddy", "version"])
    status = {"version": VERSION, "vu_le": time.time(), "demande_id": request.get("id"),
              "caddy": version.split()[0] if code == 0 and version else None,
              "adresses": addresses(), "pare_feu_80": firewall_allows(80), "pare_feu_443": firewall_allows(443), "domaine": "", "erreur": None,
              "certificat": None}
    try:
        content, domain = snippet_for(request, args.amont)
        status["domaine"] = domain
        status["erreur"] = apply(content) if status["caddy"] else "Caddy n'est pas installé sur le serveur."
    except (ValueError, OSError) as e:
        status["erreur"] = str(e)
        domain = ""
    if domain and not status["erreur"]:
        # Juste après un changement, Caddy met quelques secondes à obtenir le certificat : on patiente un peu
        deadline = time.time() + 90
        while True:
            status["certificat"] = certificate(domain)
            if status["certificat"]["valide"] or time.time() > deadline:
                break
            time.sleep(10)
    write_status(base / "etat.json", status)
    print(json.dumps({k: status[k] for k in ("domaine", "erreur", "certificat")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
