# Historique des versions

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
