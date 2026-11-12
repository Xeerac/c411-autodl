"""Configuration : le schéma de tous les réglages et leur lecture.

Chaque réglage est décrit UNE seule fois dans SETTINGS : nom dans le .env, clé interne, type, valeur
par défaut, groupe, libellé, explication, secret ou non. Tout le reste en découle : lecture du .env,
vérification, valeurs par défaut, et plus tard les formulaires de l'interface web.

Ajouter un réglage = ajouter une ligne dans SETTINGS.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .commun import parse_size


# --------------------------------------------------------------------------- lecture du fichier .env

def load_env(path: Path) -> None:
    """Charge un fichier .env simple (CLE=valeur) sans écraser l'environnement."""
    if not path.exists():
        return
    for key, value in read_env_file(path).items():
        os.environ.setdefault(key, value)


def read_env_file(path: Path) -> dict[str, str]:
    """Lit un fichier .env. La première occurrence d'une clé l'emporte (comme load_env)."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


# --------------------------------------------------------------------------- schéma

@dataclass(frozen=True)
class Setting:
    env: str                    # nom dans le .env
    key: str                    # clé interne (cfg[...])
    kind: str                   # str, secret, int, float, bool, size, size_opt, words, list, regex, choice, profiles
    default: Any                # valeur par défaut, déjà convertie
    group: str                  # identifiant du groupe (GROUPS)
    label: str                  # libellé court
    help: str = ""              # explication
    required: bool = False
    choices: tuple = ()         # pour kind=choice
    minimum: float | None = None
    aliases: tuple = ()         # anciens noms encore acceptés
    advanced: bool = False      # réglage rarement modifié
    section: str = ""           # bloc repliable du groupe (SECTIONS), vide = affiché normalement

    @property
    def secret(self) -> bool:
        return self.kind == "secret"


# Blocs repliables à l'intérieur d'un groupe : identifiant -> (titre, explication)
SECTIONS: dict[str, tuple[str, str]] = {
    "webhooks": ("Un salon Discord par type de message",
                 "Optionnel. Colle le webhook d'un autre salon pour y envoyer ce type de message. "
                 "Un champ vide = le webhook principal."),
}

# Groupes, dans l'ordre d'affichage : identifiant -> (titre, description)
GROUPS: dict[str, tuple[str, str]] = {
    "c411": ("c411", "Accès à c411 et catégories surveillées."),
    "qbittorrent": ("qBittorrent", "Ta WebUI qBittorrent et la façon dont les torrents y sont rangés."),
    "filtres": ("Filtres", "Les critères qu'un torrent doit remplir pour être ajouté."),
    "upload": ("Cibler l'upload", "Privilégier les torrents qui te feront envoyer le plus."),
    "qualite": ("Qualité", "Écarter les formats, groupes ou titres dont tu ne veux pas."),
    "ratio": ("Ratio", "Protection de ton ratio c411."),
    "limites": ("Limites et rythme", "Fréquence des passages, quantités et marges de sécurité."),
    "categories": ("Catégories et budget", "Des réglages propres à chaque catégorie, et une limite de "
                                           "téléchargement par jour pour protéger ton ratio."),
    "freeleech": ("Mode freeleech", "Recherche élargie quand un freeleech est actif sur ton compte."),
    "nettoyage": ("Nettoyage", "Retrait des torrents supprimés de c411."),
    "inactifs": ("Torrents inactifs", "Retrait des torrents qui n'envoient plus rien, après le temps de seed "
                                      "exigé par c411 (72 h)."),
    "integrations": ("Intégrations", "cross-seed et Prowlarr, si tu les utilises. Laisse vide sinon : "
                                     "l'interface s'adapte."),
    "bilan": ("Bilan quotidien", "Résumé de la journée : volumes, ratio, rendement par type."),
    "notifications": ("Notifications", "Discord et Telegram."),
    "alertes": ("Alertes", "Être prévenu quand le programme est en panne."),
    "domaine": ("Accès par domaine", "Ouvrir l'interface sur un nom de domaine en HTTPS. Par défaut, elle reste "
                                     "accessible uniquement par le tunnel SSH."),
}

SETTINGS: tuple[Setting, ...] = (
    # --- c411
    Setting("C411_URL", "c411_url", "str", "https://c411.org", "c411", "Adresse de c411", advanced=True),
    Setting("C411_API_KEY", "api_key", "secret", "", "c411", "Clé API Torznab",
            "Clé créée sur c411 (Intégrations) avec uniquement le droit « Torznab/RSS (lecture) ».", required=True),
    Setting("C411_PROFILE_API_KEY", "profile_key", "secret", "", "c411", "Clé API Profil",
            "Clé avec uniquement le droit « Profil (lecture) ». Nécessaire pour la protection du ratio "
            "et le mode freeleech."),
    Setting("C411_CATEGORIES", "cats", "str", "7020,7030", "c411", "Catégories surveillées",
            "Numéros Torznab séparés par des virgules : 7020 eBooks, 7030 BD/comics/mangas, 7010 presse, "
            "3030 livres audio, 2030 films, 5000 séries…"),

    # --- qBittorrent
    Setting("QBIT_URL", "qbit_url", "str", "", "qbittorrent", "Adresse de la WebUI",
            "L'adresse que tu ouvres dans ton navigateur, sans /api/v2 à la fin.", required=True),
    Setting("QBIT_USER", "qbit_user", "str", "", "qbittorrent", "Utilisateur", required=True),
    Setting("QBIT_PASS", "qbit_pass", "secret", "", "qbittorrent", "Mot de passe", required=True),
    Setting("QBIT_CATEGORY", "qbit_category", "str", "c411-ebook", "qbittorrent", "Catégorie qBittorrent",
            "Catégorie unique des torrents ajoutés (si la catégorie par type est désactivée)."),
    Setting("QBIT_CATEGORIE_PAR_TYPE", "cat_par_type", "bool", False, "qbittorrent", "Une catégorie par type",
            "Range les torrents dans c411-ebook, c411-bd, c411-presse, c411-livre-audio…"),
    Setting("QBIT_CATEGORIE_PREFIXE", "cat_prefix", "str", "c411", "qbittorrent", "Préfixe des catégories",
            advanced=True),
    Setting("QBIT_TAGS", "qbit_tags", "str", "c411,autodl", "qbittorrent", "Tags ajoutés", advanced=True),
    Setting("QBIT_SAVEPATH", "qbit_savepath", "str", "", "qbittorrent", "Dossier de téléchargement",
            "Vide = dossier par défaut de qBittorrent.", advanced=True),
    Setting("QBIT_PAUSED", "qbit_paused", "bool", False, "qbittorrent", "Ajouter en pause", advanced=True),

    # --- Filtres
    Setting("MIN_COMPLETED", "min_completed", "int", 1, "filtres", "Complétés minimum",
            "Nombre minimum de personnes ayant terminé le torrent sur c411.", minimum=0),
    Setting("MIN_SEEDERS", "min_seeders", "int", 1, "filtres", "Seeders minimum", minimum=0),
    Setting("TAILLE_MAX", "max_size", "size", 0, "filtres", "Taille maximum",
            "Exemples : 500Mo, 2Go. 0 = pas de limite.", aliases=("MAX_SIZE_MB",)),
    Setting("EXCLUDE_WORDS", "exclude", "words", [], "filtres", "Mots exclus",
            "Un torrent dont le titre contient l'un de ces mots est écarté (séparés par des virgules)."),

    # --- Cibler l'upload
    Setting("MAX_SEEDERS", "max_seeders", "int", 0, "upload", "Seeders maximum",
            "Ignore les torrents déjà très partagés. 0 = pas de limite. 20 est un bon point de départ.",
            minimum=0),
    Setting("MIN_LEECHERS", "min_leechers", "int", 0, "upload", "Leechers minimum",
            "Ne prend que les torrents demandés. 0 = pas de minimum.", minimum=0),
    Setting("TRI", "tri", "choice", "interet", "upload", "Ordre de traitement",
            "interet : les plus demandés d'abord. recent : ordre de c411.", choices=("interet", "recent")),

    # --- Qualité
    Setting("TAILLE_MIN", "min_size", "size", 0, "qualite", "Taille minimum",
            "Écarte les fichiers suspects. Exemples : 100Ko, 1Mo. 0 = pas de minimum."),
    Setting("FORMATS", "formats", "words", [], "qualite", "Formats acceptés",
            "Cherchés dans le titre, par exemple epub,cbz,cbr. Vide = tous les formats."),
    Setting("MOTS_REQUIS", "required", "words", [], "qualite", "Mots requis",
            "Le titre doit contenir au moins un de ces mots, par exemple fr,french."),
    Setting("GROUPES_EXCLUS", "excluded_groups", "words", [], "qualite", "Groupes exclus",
            "Ce qui suit le dernier tiret du titre, par exemple notag."),
    Setting("REGEX_EXCLUSION", "exclude_regex", "regex", None, "qualite", "Expression régulière d'exclusion",
            "Pour les utilisateurs avancés, sans tenir compte des majuscules.", advanced=True),

    # --- Ratio
    Setting("MIN_RATIO", "min_ratio", "float", 2.0, "ratio", "Ratio minimum",
            "Le ratio doit rester strictement au-dessus, même après le téléchargement. 0 = désactivé.",
            minimum=0),

    # --- Limites et rythme
    Setting("BOUCLE_SECONDES", "boucle", "int", 0, "limites", "Intervalle du mode continu (s)",
            "Utilisé si le programme est lancé sans --boucle. 0 = un seul passage.", minimum=0, advanced=True),
    Setting("PAGES", "pages", "int", 1, "limites", "Pages lues par passage",
            "100 torrents par page, 6 au maximum.", minimum=1),
    Setting("PAGE_SIZE", "page_size", "int", 100, "limites", "Torrents par page", minimum=1, advanced=True),
    Setting("MAX_PER_RUN", "max_per_run", "int", 50, "limites", "Ajouts maximum par passage", minimum=0),
    Setting("MIN_FREE_GB", "min_free_gb", "int", 20, "limites", "Espace libre à garder (Go)", minimum=0),
    Setting("REQUEST_DELAY", "delay", "float", 1.0, "limites", "Pause entre deux requêtes c411 (s)",
            minimum=0, advanced=True),
    Setting("RATTRAPAGE_MOTS", "queries", "list",
            ["epub", "pdf", "cbz", "cbr", "mobi", "azw3", "mp3", "m4b", "FR", "FRENCH", "MULTI", "NOTAG",
             "Tome", "T01"], "limites", "Mots-clés du rattrapage", advanced=True),

    # --- Catégories et budget
    Setting("PROFILS_CATEGORIES", "profiles", "profiles", {}, "categories", "Réglages par catégorie",
            "Une ligne par catégorie, par exemple « 3010: formats=flac taille_max=2Go par_passage=3 ». "
            "Réglages possibles : formats, mots_requis, mots_exclus, taille_min, taille_max, completes_min, "
            "seeders_min, seeders_max, leechers_min, par_passage, budget_jour. Une famille (2000) vaut pour "
            "toutes ses catégories (2030, 2040…). Le reste suit la configuration générale."),
    Setting("BUDGET_JOUR", "budget_day", "size_opt", None, "categories", "Budget de téléchargement par jour",
            "Ce que c411 compte en « reçu », toutes catégories confondues. Les freeleech ne comptent pas. "
            "Vide = pas de limite. Exemple : 20Go."),

    # --- Mode freeleech
    Setting("FREELEECH_MODE", "fl_mode", "bool", False, "freeleech", "Activer le mode freeleech",
            "Nécessite la clé API Profil."),
    Setting("FREELEECH_CATEGORIES", "fl_cats", "list", [], "freeleech", "Catégories en plus",
            "Ajoutées pendant un freeleech, par exemple 2030,5000 (films, séries)."),
    Setting("FREELEECH_MAX_PAR_PASSAGE", "fl_max_per_run", "int", 100, "freeleech", "Ajouts maximum par passage",
            minimum=0),
    Setting("FREELEECH_TAILLE_MAX", "fl_max_size", "size_opt", None, "freeleech", "Taille maximum",
            "Vide = même valeur que la taille maximum normale."),
    Setting("FREELEECH_IGNORER_FORMATS", "fl_ignore_formats", "bool", True, "freeleech", "Ignorer les formats",
            "Sinon, la liste des formats acceptés écarterait films et séries."),

    # --- Nettoyage
    Setting("NETTOYAGE_SUPPRIMES", "cleanup", "bool", False, "nettoyage", "Retirer les torrents supprimés",
            "Double vérification : message du tracker et absence confirmée par l'API c411."),
    Setting("NETTOYAGE_ACTION", "cleanup_action", "choice", "fichiers", "nettoyage", "Action",
            "fichiers : retire le torrent et ses fichiers (gardés s'ils sont partagés). torrent : garde les "
            "fichiers. pause : met en pause.", choices=("fichiers", "torrent", "pause")),
    Setting("NETTOYAGE_TAG", "own_tag", "str", "autodl", "nettoyage", "Tag des torrents gérés",
            "Seuls ces torrents sont nettoyés, envoyés à cross-seed et comptés dans le bilan.", advanced=True),
    Setting("NETTOYAGE_MINUTES", "cleanup_minutes", "int", 60, "nettoyage", "Fréquence (minutes)", minimum=1),

    # --- Torrents inactifs
    Setting("INACTIFS_RETIRER", "inactive", "bool", False, "inactifs", "Retirer les torrents inactifs",
            "Seulement ceux du tag géré (autodl), complets, sans leecher, et dont le tracker c411 répond. "
            "Fais d'abord un aperçu depuis le tableau de bord."),
    Setting("INACTIFS_JOURS", "inactive_days", "int", 30, "inactifs", "Inactif depuis (jours)",
            "Rien envoyé depuis ce nombre de jours.", minimum=1),
    Setting("INACTIFS_SEED_MIN_HEURES", "inactive_seed_hours", "int", 96, "inactifs", "Seed minimum (heures)",
            "Jamais moins de 72 h, la règle Hit & Run de c411. 96 h = 24 h de marge.", minimum=72),
    Setting("INACTIFS_ACTION", "inactive_action", "choice", "fichiers", "inactifs", "Action",
            "fichiers : retire le torrent et ses fichiers (gardés s'ils sont partagés). torrent : garde les "
            "fichiers. pause : met en pause avec le tag inactif.", choices=("fichiers", "torrent", "pause")),
    Setting("INACTIFS_MAX_PAR_JOUR", "inactive_max_per_day", "int", 10, "inactifs", "Retraits maximum par jour",
            "Garde-fou : le reste attend le lendemain.", minimum=1),

    # --- cross-seed
    Setting("CROSS_SEED_URL", "cs_url", "str", "", "integrations", "Adresse de cross-seed",
            "Par exemple http://localhost:2468, ou http://cross-seed:2468 depuis Docker. Vide = désactivé."),
    Setting("CROSS_SEED_API_KEY", "cs_key", "secret", "", "integrations", "Clé API cross-seed",
            "Commande : cross-seed api-key."),
    Setting("PROWLARR_URL", "prowlarr_url", "str", "", "integrations", "Adresse de Prowlarr",
            "Pour afficher son état au tableau de bord, par exemple http://localhost:9696. Vide = masqué."),
    Setting("PROWLARR_API_KEY", "prowlarr_key", "secret", "", "integrations", "Clé API Prowlarr",
            "Dans Prowlarr : Settings > General > API Key."),

    # --- Bilan
    Setting("BILAN_QUOTIDIEN", "bilan", "bool", False, "bilan", "Bilan quotidien"),
    Setting("BILAN_HEURE", "bilan_heure", "int", 8, "bilan", "Heure du bilan", minimum=0),

    # --- Notifications
    Setting("DISCORD_WEBHOOK_URL", "discord_webhook", "secret", "", "notifications", "Webhook Discord",
            "Webhook principal : tous les messages, sauf ceux qui ont leur propre webhook ci-dessous."),
    # Un webhook par type de message (vide = webhook principal) : un salon Discord par sujet
    Setting("DISCORD_WEBHOOK_AJOUTS", "discord_webhook_ajout", "secret", "", "notifications",
            "Ajouts", "Torrents ajoutés à la seedbox.", section="webhooks"),
    Setting("DISCORD_WEBHOOK_RETRAITS", "discord_webhook_retrait", "secret", "", "notifications",
            "Retraits", "Supprimés de c411 et inactifs retirés.", section="webhooks"),
    Setting("DISCORD_WEBHOOK_BILAN", "discord_webhook_bilan", "secret", "", "notifications",
            "Bilan quotidien", "", section="webhooks"),
    Setting("DISCORD_WEBHOOK_DISQUE", "discord_webhook_disque", "secret", "", "notifications",
            "Espace disque", "", section="webhooks"),
    Setting("DISCORD_WEBHOOK_TRACKER", "discord_webhook_tracker", "secret", "", "notifications",
            "Tracker c411", "", section="webhooks"),
    Setting("DISCORD_WEBHOOK_SSL", "discord_webhook_ssl", "secret", "", "notifications",
            "Certificat SSL", "", section="webhooks"),
    Setting("DISCORD_WEBHOOK_HIT_AND_RUN", "discord_webhook_hitrun", "secret", "", "notifications",
            "Hit & Run", "", section="webhooks"),
    Setting("TELEGRAM_BOT_TOKEN", "telegram_token", "secret", "", "notifications", "Token du bot Telegram"),
    Setting("TELEGRAM_CHAT_ID", "telegram_chat", "str", "", "notifications", "Identifiant Telegram"),
    Setting("NOTIF_PAUSES", "notif_pauses", "bool", True, "notifications", "Prévenir des pauses liées au ratio"),

    # --- Alertes
    Setting("ALERTE_PANNE", "alert", "bool", True, "alertes", "Alerte en cas de panne"),
    Setting("ALERTE_APRES", "alert_after", "int", 3, "alertes", "Échecs avant l'alerte", minimum=1),
    Setting("ALERTE_DISQUE_GO", "alert_disk_gb", "int", 50, "alertes", "Alerte espace disque (Go)",
            "Notification quand la seedbox passe sous ce nombre de Go libres. 0 = désactivée.", minimum=0),
    Setting("ALERTE_TRACKER", "alert_tracker", "int", 10, "alertes", "Alerte tracker c411 (torrents)",
            "Notification quand au moins ce nombre de torrents n'a plus de tracker fonctionnel depuis plus "
            "d'une heure (maintenance de c411, passkey changée…). 0 = désactivée.", minimum=0),
    Setting("ALERTE_CERTIFICAT", "alert_cert", "bool", True, "alertes", "Alerte certificat SSL",
            "Accès par domaine : notification si le certificat expire dans moins de 14 jours, ou si "
            "l'assistant serveur ne répond plus."),
    Setting("ALERTE_HIT_AND_RUN", "hr_alert", "bool", True, "alertes", "Alerte Hit & Run",
            "Notification quand un torrent pas encore quitte (72 h de seed ou ratio 1,0) ne seede plus : "
            "en pause, arrêté, en erreur, ou bloqué en téléchargement."),

    # --- Accès par domaine (interface web)
    Setting("DOMAINE_ACTIF", "domain_on", "bool", False, "domaine", "Accès par nom de domaine",
            "Désactivé : interface accessible uniquement par le tunnel SSH. Activé : en HTTPS sur ton domaine, "
            "avec un certificat Let's Encrypt (nécessite Caddy et l'assistant serveur)."),
    Setting("DOMAINE_NOM", "domain", "str", "", "domaine", "Nom de domaine",
            "Domaine ou sous-domaine, par exemple c411.mondomaine.fr, avec un enregistrement A vers ce serveur."),
    Setting("DOMAINE_NOTIF_CONNEXION", "domain_notify", "bool", True, "domaine", "Prévenir à chaque connexion",
            "Notification Discord / Telegram quand quelqu'un se connecte à l'interface depuis Internet."),
)

BY_ENV: dict[str, Setting] = {s.env: s for s in SETTINGS}
BY_KEY: dict[str, Setting] = {s.key: s for s in SETTINGS}


# --------------------------------------------------------------------------- conversion et vérification

TRUE_WORDS = ("1", "true", "yes", "oui", "on")


def parse_value(s: Setting, raw: str | None) -> Any:
    """Convertit une valeur brute (texte du .env). Vide ou absente = valeur par défaut.

    Lève ValueError avec un message en français si la valeur est invalide.
    """
    raw = "" if raw is None else str(raw).strip()
    if s.kind in ("str", "secret"):
        return raw or s.default
    if not raw:
        return s.default
    if s.kind == "bool":
        return raw.lower() in TRUE_WORDS
    if s.kind == "int":
        try:
            value = int(raw)
        except ValueError:
            raise ValueError(f"{s.env} doit être un nombre entier (valeur actuelle : {raw})") from None
        return _check_min(s, value)
    if s.kind == "float":
        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            raise ValueError(f"{s.env} doit être un nombre (valeur actuelle : {raw})") from None
        return _check_min(s, value)
    if s.kind in ("size", "size_opt"):
        try:
            return parse_size(raw)
        except ValueError:
            raise ValueError(f"{s.env} : taille invalide ({raw}), exemples : 500Mo, 2Go") from None
    if s.kind == "words":
        return [w.strip().lower() for w in raw.split(",") if w.strip()]
    if s.kind == "list":
        return [w.strip() for w in raw.split(",") if w.strip()]
    if s.kind == "regex":
        try:
            return re.compile(raw, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"{s.env} : expression régulière invalide ({e})") from None
    if s.kind == "profiles":
        from .profils import parse
        return parse(raw)
    if s.kind == "choice":
        value = raw.lower()
        if value not in s.choices:
            raise ValueError(f"{s.env} doit valoir {', '.join(s.choices[:-1])} ou {s.choices[-1]}")
        return value
    raise ValueError(f"type de réglage inconnu : {s.kind}")


def _check_min(s: Setting, value):
    if s.minimum is not None and value < s.minimum:
        if s.env == "ALERTE_APRES":  # comportement historique : ramené à 1
            return int(s.minimum)
        raise ValueError(f"{s.env} doit être supérieur ou égal à {s.minimum:g} (valeur actuelle : {value})")
    return value


def build_cfg(source: Mapping[str, str] | None = None) -> tuple[dict, list[str]]:
    """Construit la configuration à partir de valeurs brutes (par défaut : les variables d'environnement).

    Retourne (cfg, erreurs). cfg contient toutes les clés, même en cas d'erreur (valeur par défaut).
    """
    source = os.environ if source is None else source
    cfg: dict[str, Any] = {}
    errors: list[str] = []
    for s in SETTINGS:
        raw = source.get(s.env)
        if (raw is None or not str(raw).strip()) and s.aliases:
            raw = next((source.get(a) for a in s.aliases if source.get(a, "").strip()), raw)
        try:
            cfg[s.key] = parse_value(s, raw)
        except ValueError as e:
            errors.append(str(e))
            cfg[s.key] = s.default
        if s.required and not cfg[s.key]:
            errors.append(f"Variable manquante dans .env : {s.env}")
    errors += cross_check(cfg)
    return cfg, errors


def cross_check(cfg: dict) -> list[str]:
    """Vérifications qui dépendent de plusieurs réglages."""
    errors = []
    if cfg["fl_mode"] and not cfg["profile_key"]:
        errors.append("FREELEECH_MODE est activé : ajoute C411_PROFILE_API_KEY dans .env "
                      "(clé avec le scope « Profil (lecture) ») pour détecter le freeleech")
    if cfg["cs_url"] and not cfg["cs_key"]:
        errors.append("CROSS_SEED_URL est rempli : ajoute aussi CROSS_SEED_API_KEY (commande : cross-seed api-key)")
    if cfg["min_ratio"] > 0 and not cfg["profile_key"]:
        errors.append("MIN_RATIO est activé : ajoute C411_PROFILE_API_KEY dans .env "
                      "(clé avec le scope « Profil (lecture) »), ou mets MIN_RATIO=0.")
    if not 0 <= cfg["bilan_heure"] <= 23:
        errors.append("BILAN_HEURE doit être compris entre 0 et 23")
    if cfg["domain_on"]:
        from .domaine import valid_domain
        if not valid_domain(cfg["domain"]):
            errors.append("DOMAINE_ACTIF est activé : indique un nom de domaine valide dans DOMAINE_NOM "
                          "(par exemple c411.mondomaine.fr)")
    return errors


def load_cfg_or_exit(source: Mapping[str, str] | None = None) -> dict:
    """Pour la ligne de commande : configuration valide, ou arrêt avec la liste des problèmes."""
    cfg, errors = build_cfg(source)
    if errors:
        sys.exit("Configuration invalide :\n  - " + "\n  - ".join(errors))
    return cfg


# --------------------------------------------------------------------------- compatibilité

def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        sys.exit(f"Variable manquante dans .env : {name}")
    return value or ""


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in TRUE_WORDS
