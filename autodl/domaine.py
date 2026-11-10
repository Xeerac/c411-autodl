"""Accès à l'interface par un nom de domaine (optionnel ; par défaut, l'interface reste derrière le tunnel SSH).

Le programme ne touche jamais lui-même au serveur web : il dépose une DEMANDE (le nom de domaine, rien
d'autre) dans donnees/domaine/demande.json. Un petit assistant installé sur la machine hôte
(serveur/assistant_domaine.py, lancé par systemd) la lit, écrit la configuration Caddy à partir d'un modèle
fixe, recharge Caddy, vérifie le certificat et répond dans donnees/domaine/etat.json.
Même si l'interface était compromise, elle ne pourrait que choisir un nom de domaine.

Ce module fait les vérifications côté programme : le nom pointe-t-il vers la machine ? Le proxy Cloudflare
est-il actif ? Et il construit la liste des étapes affichée dans la configuration.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
import urllib.request
from pathlib import Path

from .commun import DATA, USER_AGENT, _save_json, log

DIR = DATA / "domaine"
HELPER_STALE = 15 * 60  # l'assistant se manifeste toutes les 5 min : au-delà de 15, on le considère absent

DOMAIN_RE = re.compile(r"^(?=.{4,253}$)(?!-)([a-z0-9-]{1,63}(?<!-)\.)+[a-z]{2,63}$")

# Plages d'adresses de Cloudflare (https://www.cloudflare.com/ips/)
CLOUDFLARE = [ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
    "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
    "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32",
    "2a06:98c0::/29", "2c0f:f248::/32")]


def valid_domain(name: str) -> bool:
    return bool(DOMAIN_RE.fullmatch((name or "").strip().lower()))


def is_cloudflare(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in CLOUDFLARE if net.version == addr.version)


def resolve(domain: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return []
    return sorted({i[4][0] for i in infos})


_public_ip: dict = {}


def public_ip() -> str | None:
    """Adresse publique de la machine (gardée une heure)."""
    if _public_ip.get("t", 0) > time.time() - 3600:
        return _public_ip.get("ip")
    ip = None
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=8) as r:
                candidate = r.read(64).decode().strip()
            ipaddress.ip_address(candidate)
            ip = candidate
            break
        except Exception:
            continue
    _public_ip.update(t=time.time(), ip=ip)
    return ip


# ------------------------------------------------------------------ dialogue avec l'assistant

def write_request(domain: str, enabled: bool, base: Path | None = None) -> dict:
    """Dépose la demande pour l'assistant. Seul le nom de domaine (validé) est transmis."""
    domain = domain.strip().lower()
    if enabled and not valid_domain(domain):
        raise ValueError("nom de domaine invalide")
    base = base or DIR
    base.mkdir(parents=True, exist_ok=True)
    request = {"version": 1, "id": int(time.time() * 1000), "actif": bool(enabled),
               "domaine": domain if enabled else "", "le": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save_json(base / "demande.json", request)
    log.info("Domaine : demande transmise à l'assistant (%s)", domain if enabled else "désactivation")
    return request


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def current_request(base: Path | None = None) -> dict:
    return read_json((base or DIR) / "demande.json")


def helper_status(base: Path | None = None) -> dict:
    return read_json((base or DIR) / "etat.json")


# ------------------------------------------------------------------ étapes affichées dans l'interface

def _step(sid: str, title: str, state: str, message: str, **extra) -> dict:
    """state : ok, attente, alerte, erreur, inactif."""
    return {"id": sid, "titre": title, "etat": state, "message": message, **extra}


def check(cfg: dict, base: Path | None = None, now: float | None = None) -> dict:
    """Toutes les vérifications, dans l'ordre. Ne modifie rien."""
    now = now or time.time()
    domain = (cfg.get("domain") or "").strip().lower()
    enabled = bool(cfg.get("domain_on"))
    steps: list[dict] = []
    out = {"actif": enabled, "domaine": domain, "etapes": steps, "pret": False, "url": None, "cloudflare": False}

    if not enabled:
        steps.append(_step("mode", "Mode d'accès", "inactif",
                           "Accès par tunnel SSH uniquement (par défaut). Active l'option et indique un domaine "
                           "pour rendre l'interface accessible en HTTPS."))
        return out
    if not valid_domain(domain):
        steps.append(_step("nom", "Nom de domaine", "erreur",
                           "Indique un nom de domaine ou un sous-domaine valide, par exemple c411.mondomaine.fr."))
        return out
    steps.append(_step("nom", "Nom de domaine", "ok", domain))

    # 1. DNS
    ips = resolve(domain)
    status = helper_status(base)
    machine = set(status.get("adresses") or [])
    pub = public_ip()
    if pub:
        machine.add(pub)
    proxied = bool(ips) and all(is_cloudflare(ip) for ip in ips)
    out["cloudflare"] = proxied
    if not ips:
        steps.append(_step("dns", "DNS", "erreur",
                           f"{domain} ne pointe vers aucune adresse. Crée un enregistrement A vers "
                           f"{pub or 'l’adresse IP du serveur'} chez ton hébergeur de DNS, puis patiente quelques minutes."))
    elif proxied:
        steps.append(_step("dns", "DNS", "alerte",
                           f"{domain} passe par le proxy Cloudflare ({', '.join(ips[:2])}) : impossible de vérifier "
                           "l'adresse du serveur derrière."))
    elif machine and set(ips) & machine:
        steps.append(_step("dns", "DNS", "ok", f"{domain} pointe bien vers ce serveur ({', '.join(ips)})."))
    elif machine:
        steps.append(_step("dns", "DNS", "erreur",
                           f"{domain} pointe vers {', '.join(ips)}, mais ce serveur a l'adresse "
                           f"{', '.join(sorted(machine))}. Corrige l'enregistrement A."))
    else:
        steps.append(_step("dns", "DNS", "attente",
                           f"{domain} pointe vers {', '.join(ips)}. Adresse du serveur inconnue pour l'instant."))

    # 2. Cloudflare
    cert = status.get("certificat") or {}
    cert_ok = bool(cert.get("valide")) and status.get("domaine") == domain
    if proxied and not cert_ok:
        steps.append(_step("cloudflare", "Proxy Cloudflare", "alerte",
                           "Le proxy Cloudflare (nuage orange) est actif. Désactive-le le temps de l'installation : "
                           "dans Cloudflare, onglet DNS, clique sur le nuage orange de cet enregistrement pour le "
                           "passer en gris (« DNS only »). Le certificat SSL ne peut pas être obtenu à travers le proxy. "
                           "Tu pourras le réactiver à la fin."))
    elif proxied:
        steps.append(_step("cloudflare", "Proxy Cloudflare", "ok",
                           "Proxy Cloudflare actif. Vérifie que le mode SSL/TLS de Cloudflare est sur "
                           "« Full (strict) »."))
    else:
        steps.append(_step("cloudflare", "Proxy Cloudflare", "ok", "Pas de proxy Cloudflare : connexion directe."))

    # 3. Assistant serveur
    seen = status.get("vu_le") or 0
    if not seen:
        steps.append(_step("assistant", "Assistant serveur", "erreur",
                           "L'assistant n'est pas installé sur le serveur. Une seule fois, en root, depuis le "
                           "dossier c411-autodl : sudo bash serveur/installer_domaine.sh"))
        return out
    if now - seen > HELPER_STALE:
        steps.append(_step("assistant", "Assistant serveur", "erreur",
                           f"L'assistant ne répond plus depuis {int((now - seen) // 60)} min. "
                           "Sur le serveur : systemctl status c411-autodl-domaine.timer"))
        return out
    steps.append(_step("assistant", "Assistant serveur", "ok",
                       f"Installé (Caddy {status.get('caddy') or '?'})."))

    # 4. Configuration appliquée
    request = current_request(base)
    if request.get("domaine") != domain or not request.get("actif"):
        steps.append(_step("caddy", "Configuration du serveur web", "attente",
                           "Enregistre la configuration pour transmettre le domaine à l'assistant."))
        return out
    if status.get("demande_id") != request.get("id"):
        steps.append(_step("caddy", "Configuration du serveur web", "attente",
                           "Demande transmise, l'assistant l'applique (quelques secondes)."))
        return out
    if status.get("erreur"):
        steps.append(_step("caddy", "Configuration du serveur web", "erreur", status["erreur"]))
        return out
    steps.append(_step("caddy", "Configuration du serveur web", "ok", "Caddy est configuré pour ce domaine."))

    # 5. Certificat
    if not cert_ok:
        hint = ""
        if status.get("pare_feu_80") is False:
            hint = (" Le pare-feu du serveur n'autorise pas le port 80 pour tout le monde : Let's Encrypt ne peut "
                    "pas joindre le serveur. Ouvre-le le temps d'obtenir le certificat (ufw allow 80/tcp), puis "
                    "referme-le.")
        if proxied:
            hint += " Le proxy Cloudflare doit être désactivé pendant cette étape."
        detail = cert.get("erreur") or "Caddy demande le certificat à Let's Encrypt, cela prend en général moins d'une minute."
        steps.append(_step("ssl", "Certificat SSL", "attente", detail + hint))
        return out
    days = int((cert.get("expire_ts", now) - now) // 86400)
    state = "ok" if days >= 14 else "alerte"
    steps.append(_step("ssl", "Certificat SSL", state,
                       f"Valide, émis par {cert.get('emetteur') or '?'}, expire dans {days} jours "
                       f"({cert.get('expire') or '?'}). Caddy le renouvelle tout seul."
                       + ("" if state == "ok" else " Le renouvellement semble bloqué : vérifie le port 80.")))

    out["url"] = f"https://{domain}"
    if not proxied and status.get("pare_feu_443") is False:
        steps.append(_step("acces", "Accès depuis Internet", "alerte",
                           "Le certificat est prêt, mais le pare-feu du serveur n'accepte le port 443 (HTTPS) que "
                           "depuis certaines adresses, par exemple celles de Cloudflare : sans proxy, ton navigateur "
                           "est bloqué. Réactive le proxy Cloudflare (nuage orange, mode SSL/TLS « Full (strict) »), "
                           "ou ouvre le port 443 à tout le monde (ufw allow 443/tcp)."))
        return out
    out["pret"] = True
    if proxied:
        final = "L'interface est accessible, à travers Cloudflare."
    else:
        final = ("L'interface est accessible. Tu peux réactiver le proxy Cloudflare si tu le souhaites (nuage "
                 "orange) : mets alors le mode SSL/TLS de Cloudflare sur « Full (strict) ». Si tu as ouvert le port "
                 "80 pour le certificat, tu peux le refermer une fois le proxy réactivé (les renouvellements "
                 "passeront par Cloudflare) ; sans proxy, laisse-le ouvert.")
    steps.append(_step("fin", "Terminé", "ok", final, lien=out["url"]))
    return out
