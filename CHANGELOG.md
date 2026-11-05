# Historique des versions

## v1.5.0 — 2026-11-05

- **Docker** : `Dockerfile` (image légère, Python seul, utilisateur non root, fuseaux horaires inclus pour `BILAN_HEURE`) et `docker-compose.yml` d'exemple. La configuration (`.env`) et les données (`donnees/`) sont montées, rien de personnel dans l'image. Les commandes ponctuelles passent par `docker compose run --rm c411-autodl …`.
- **`migrer_vers_docker.sh`** : bascule une installation systemd vers Docker en une commande. Il reprend l'utilisateur et l'intervalle, utilise le réseau de la machine pour que les adresses `localhost` du `.env` restent valables, lance un essai à blanc dans le conteneur avant toute modification et revient automatiquement à systemd en cas d'échec. Option `--retour` pour revenir à systemd.
- **Arrêt propre** sur `SIGTERM`, le signal envoyé par Docker et systemd : le journal indique l'arrêt et le nombre de torrents ajoutés.
- La vérification automatique de GitHub construit et teste aussi l'image Docker.

## v1.4.0 — 2026-11-05

**Nouveautés**
- **Mode freeleech** (`FREELEECH_MODE`, désactivé par défaut) : quand un freeleech est actif sur le compte (détecté via le profil c411), la recherche s'élargit (`FREELEECH_CATEGORIES`, `FREELEECH_MAX_PAR_PASSAGE`, `FREELEECH_TAILLE_MAX`, `FREELEECH_IGNORER_FORMATS`), sans pause liée au ratio ; tag `freeleech` sur les torrents récupérés, notification au début et à la fin.
- **Ranger les torrents existants** par type : `--recategoriser` (avec `--dry-run` pour l'aperçu). Le type exact est retrouvé via la recherche c411 ; les torrents dont les fichiers sont partagés (cross-seed) ne sont pas déplacés. `--garder-emplacement` change seulement l'étiquette, sans déplacer de fichier.
- **Alerte en cas de panne** (`ALERTE_PANNE`, `ALERTE_APRES`, activée par défaut si les notifications sont configurées) : notification après plusieurs passages en échec d'affilée, puis à la reprise avec la durée de la panne.

**Tests** : 56 tests (16 de plus).

## v1.3.0 — 2026-11-05

**Nouveautés** (toutes optionnelles, désactivées par défaut)
- **Bilan quotidien** (`BILAN_QUOTIDIEN`, `BILAN_HEURE`) : torrents ajoutés, volume téléchargé et envoyé, évolution du ratio et **rendement par type de contenu**, pour voir ce qui rapporte vraiment. Nouvelle commande `--bilan`.
- **Une catégorie qBittorrent par type** (`QBIT_CATEGORIE_PAR_TYPE`, `QBIT_CATEGORIE_PREFIXE`) : `c411-ebook`, `c411-bd`, `c411-presse`, `c411-livre-audio`, `c411-film`…
- **Intégration cross-seed** (`CROSS_SEED_URL`, `CROSS_SEED_API_KEY`) : cross-seed est prévenu dès qu'un téléchargement est terminé et cherche tout de suite sur les autres trackers.

**Améliorations**
- La session qBittorrent est gardée entre deux passages, avec reconnexion automatique si elle expire.
- L'historique (`donnees/state.json`) enregistre le type et la taille des torrents ajoutés.
- Nouvelle commande `--version`.
- **Tests automatiques** (40 tests, sans accès réseau) lancés par GitHub à chaque modification, sous Linux et Windows, de Python 3.10 à 3.13.

## v1.2.0 — 2026-11-05

- **Nettoyage des torrents supprimés de c411** (`NETTOYAGE_SUPPRIMES`) : double vérification (message du tracker + absence confirmée par l'API c411), limité aux torrents ajoutés par le programme, fichiers conservés s'ils servent à un autre torrent (cross-seed). Actions possibles : `fichiers`, `torrent`, `pause`.
- Nouvelle commande `--nettoyage` (combinable avec `--dry-run`).

## v1.1.0 — 2026-11-04

- **Cibler ce qui rapporte de l'upload** : `MAX_SEEDERS`, `MIN_LEECHERS`, `TRI=interet` (les plus demandés d'abord).
- **Filtres qualité** : `FORMATS`, `TAILLE_MIN`, `MOTS_REQUIS`, `GROUPES_EXCLUS`, `REGEX_EXCLUSION`.
- Intervalle par défaut à 5 minutes (le flux de c411 est en cache 5 minutes).

## v1.0.0 — 2026-11-04

- Première version : surveillance des catégories c411 via Torznab, ajout dans qBittorrent, protection du ratio (freeleech compris), filtres de base, notifications Discord/Telegram, mode continu, lanceurs Windows/Linux et service systemd.
