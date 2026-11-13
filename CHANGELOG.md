# Historique des versions

## v2.6.0 — 2026-11-13

**Récap quotidien du profil c411** (`RECAP_PROFIL`, à l'heure du bilan) :
- niveau et XP avec une barre de progression, classe, emblème et étoiles, bonus de l'arbre ;
- quêtes et avancement des quatre voies (seed, upload, spécialisation, compétitivité) ;
- Zen (solde, gagné, dépensé), ratio officiel et ratio mesuré par le tracker (sans le crédit), envoyé et reçu, équipe ;
- état du compte quand il y a quelque chose à signaler : téléchargement bloqué (et pourquoi), freeleech, silver leech, bonus ;
- comparaison avec la veille : XP gagnée, niveaux, quêtes terminées, Zen gagné ou dépensé, envoyé depuis hier ;
- bot Discord : salon « Profil » (`DISCORD_SALON_PROFIL`) et nouvelle commande `/profil`.

Bot Discord : plus d'avertissements inutiles de discord.py sur la voix dans le journal.

- 195 tests (5 de plus).

## v2.5.0 — 2026-11-12

**Bot Discord** (optionnel, `DISCORD_BOT_ACTIF`), à la place du webhook :
- **un salon par type de message** : ajouts, retraits, bilan quotidien, espace disque, tracker c411, certificat SSL, Hit & Run ; le reste va dans le salon principal ;
- **commandes** : `/statut`, `/ratio`, `/bilan`, `/hitrun`, `/pause`, `/reprise`, `/passage`, `/aide` ;
- commandes **réservées à un rôle Discord** (`DISCORD_ROLE`) sur ton serveur ; sans rôle choisi, tout est refusé ; jamais de bot en lecture seule ;
- configuration à la souris : le bot fournit la liste des serveurs, salons et rôles, et le lien pour l'inviter ; bouton « Tester le bot » qui envoie un message dans chaque salon choisi ;
- les messages automatiques passent par l'API de Discord : ils partent même si le bot est momentanément déconnecté ;
- fonctionne aussi sans l'interface (`--boucle`) ; le bot redémarre tout seul si ses réglages changent ;
- nouvelle dépendance de l'interface : `discord.py` (incluse dans l'image Docker). La ligne de commande seule reste sans dépendance.

Le webhook (`DISCORD_WEBHOOK_URL`) reste disponible pour ceux qui ne veulent pas de bot.

Interface : blocs repliables compacts dans la configuration (salons par type).

- 190 tests (10 de plus).

## v2.4.0 — 2026-11-12

**Réglages par catégorie et budget quotidien** (nouveau groupe « Catégories et budget ») :
- `PROFILS_CATEGORIES` : des filtres propres à chaque catégorie, par exemple `3010: formats=flac taille_max=2Go par_passage=3`. Réglages possibles : formats, mots requis ou exclus, tailles, complétés, seeders, leechers, ajouts par passage, budget du jour. Une famille (`2000`) vaut pour toutes ses sous-catégories ; le reste suit la configuration générale ;
- `BUDGET_JOUR` : ce que c411 peut compter en « reçu » par jour (les freeleech ne comptent pas, un torrent à 50 % compte pour moitié). Ce qu'il reste s'affiche au tableau de bord.

**Suivi Hit & Run** (règle de c411 : 72 h de seed ou ratio de 1,0 par torrent) :
- panneau du tableau de bord : torrents quittes, en seed (heures restantes), en téléchargement, à risque ;
- alerte (`ALERTE_HIT_AND_RUN`) quand un torrent pas encore quitte ne seede plus : en pause, arrêté, en erreur, ou bloqué en téléchargement. Une seule fois par torrent.

**Nouvelle page « Ajouts »** : tous les torrents ajoutés par le programme, avec recherche, filtres (type, Hit & Run, rien envoyé, absents de qBittorrent) et tri (date, rendement, envoyé, taille).

**Relevés** : rendement de chaque catégorie au fil des jours (une courbe par catégorie) et ce qu'elle a envoyé en 24 h.

**Actions réelles depuis l'interface**, après confirmation : nettoyage des torrents supprimés de c411, retrait des inactifs, rangement par type (sans déplacer aucun fichier). Impossible en lecture seule.

**Double authentification** : QR code à scanner, généré sans bibliothèque externe.

**Nouvelles alertes** : espace disque bas (`ALERTE_DISQUE_GO`), tracker c411 injoignable pour plusieurs torrents pendant plus d'une heure (`ALERTE_TRACKER`), certificat SSL qui expire ou assistant serveur muet (`ALERTE_CERTIFICAT`).

**Tableau de bord** rééquilibré : le Hit & Run sous les derniers ajouts.

- 180 tests (27 de plus).

## v2.3.1 — 2026-11-11

**Image Docker prête à l'emploi** (merci à u/Aldarone pour l'idée) :
- publiée automatiquement sur GitHub à chaque version : `ghcr.io/xeerac/c411-autodl`, étiquettes `latest`, `2.3` et `2.3.1` ;
- pour **amd64** (PC, VPS) et **arm64** (Raspberry Pi, serveurs ARM) ;
- vérifiée avant publication : tests, démarrage, aucun `.env` ni donnée dans l'image, utilisateur non root ;
- **plus besoin de cloner le dépôt** : le `docker-compose.yml` et le `.env` suffisent. Mise à jour : `docker compose pull && docker compose up -d` ;
- la construction locale reste possible (`build: .`) ; `migrer_vers_docker.sh` continue de construire l'image depuis le dépôt cloné.

Le programme lui-même ne change pas.

## v2.3.0 — 2026-11-10

**Accès à l'interface par un nom de domaine** (optionnel, `DOMAINE_ACTIF` ; le tunnel SSH reste le mode par défaut) :
- l'interface devient accessible en **HTTPS** sur ton domaine ou sous-domaine, avec un certificat **Let's Encrypt** obtenu et renouvelé par **Caddy** ;
- nouvel **assistant serveur** (`serveur/installer_domaine.sh`) : l'interface ne transmet qu'un nom de domaine, l'assistant écrit la configuration Caddy à partir d'un modèle fixe, la valide, recharge Caddy (l'ancienne configuration est remise en cas d'erreur) et vérifie le certificat ;
- page **Configuration → Accès par domaine** avec les vérifications en direct : DNS vers l'adresse du serveur, **alerte si le proxy Cloudflare est actif** pendant l'installation, assistant, Caddy, certificat (émetteur, expiration), pare-feu (ports 80 et 443), puis le feu vert pour **réactiver le proxy** (mode « Full (strict) ») ;
- protections en accès Internet : HTTPS obligatoire (HSTS), cookies « Secure », seul le domaine est accepté, vraie adresse du visiteur (même derrière Cloudflare), blocage global après 30 échecs en 15 min sans couper le tunnel, pages exclues des moteurs de recherche, notification à chaque connexion (`DOMAINE_NOTIF_CONNEXION`).

**Double authentification** (optionnelle) : onglet **Sécurité**, code à 6 chiffres (TOTP) de n'importe quelle application d'authentification, code jamais accepté deux fois ; secours en ligne de commande : `--desactiver-2fa`.

**Notifications Discord en embeds** : barre de couleur selon le type de message ; bilan quotidien en tuiles (envoyé, téléchargé, ajouts, ratio ▲▼, envoyé ÷ téléchargé, torrents en seed), tableau du rendement par type et podium des plus gros envois. Telegram reste en texte.

**Relevés** : un point par jour sur la courbe du ratio, et la date de chaque jour sous les graphiques tant qu'il y a la place.

**Interface** : les fichiers (scripts, styles) portent le numéro de version dans leur adresse, le navigateur charge donc toujours la dernière version après une mise à jour.

- 153 tests (18 de plus).

## v2.2.0 — 2026-11-05

**Retrait des torrents inactifs** (`INACTIFS_RETIRER`, désactivé par défaut) :
- retire les torrents autodl qui n'ont **rien envoyé depuis 30 jours** (`INACTIFS_JOURS`) et que **personne n'attend** (aucun leecher) ;
- respecte la règle **Hit & Run de c411** : au moins **96 h de seed** (`INACTIFS_SEED_MIN_HEURES`), jamais moins de 72 h quoi qu'on règle ;
- ne touche à rien si aucun tracker c411 ne répond normalement ; garde les fichiers partagés avec un cross-seed ;
- 10 retraits maximum par jour (`INACTIFS_MAX_PAR_JOUR`), les plus anciennement inactifs d'abord, et une notification récapitulative ;
- action au choix : supprimer les fichiers, garder les fichiers, ou mettre en pause (tag `inactif`) ;
- aperçu sans rien toucher : `--inactifs --dry-run`, ou le bouton « Aperçu des inactifs » du tableau de bord ; nouveau groupe « Torrents inactifs » dans la configuration ;
- 134 tests (11 de plus).

## v2.1.0 — 2026-11-05

**Nouvel onglet « Relevés »** dans l'interface web :
- chaque jour à `BILAN_HEURE` (8 h par défaut), le programme relève ton **ratio**, ton **total envoyé** et ton **total reçu** sur c411, même si le bilan quotidien est désactivé. Le tout premier relevé est pris dès le démarrage ;
- **comparaison avec la veille** : écart et pourcentage, ▲ en hausse, ▼ en baisse. Une hausse du reçu, qui fait baisser le ratio, est signalée en orange ;
- **courbe du ratio** sur 30 jours, **barres de l'envoyé** de chaque journée, et tout l'historique ;
- relevés gardés dans `donnees/releves.json`, environ trois ans, quelques octets par jour. Il faut la clé API Profil ; rien n'est enregistré en essai à blanc ;
- 123 tests (8 de plus).

## v2.0.1 — 2026-11-05

Corrections d'affichage du tableau de bord :
- la colonne « Torrent » des derniers ajouts n'est plus écrasée (largeurs de colonnes fixes) ;
- le nom et la version en haut à gauche ne sont plus soulignés comme des liens ;
- l'étiquette et le titre du bandeau d'état ne se répètent plus (« Actif » / « Surveillance en cours ») ;
- le rendement n'est affiché qu'une fois que le torrent a commencé à envoyer ;
- les tailles au-delà de 1 To s'affichent en To (espace disque de la seedbox).

## v2.0.0 — 2026-11-05

**L'interface web** (`--interface`, lancée par défaut avec Docker)
- **Tableau de bord** : état du programme, ratio et jauge, volume envoyé, dernier et prochain passage ; état de qBittorrent, cross-seed et Prowlarr (ces deux derniers seulement s'ils sont configurés) ; derniers ajouts avec ce qu'ils ont envoyé ; rendement par type de contenu.
- **Actions** : passage immédiat, pause, reprise, essai à blanc, bilan, aperçus du nettoyage et du rangement (les aperçus ne modifient jamais rien).
- **Configuration** de tous les réglages, rangés par thème : vérification avant enregistrement, prise en compte sans redémarrage, boutons « Tester » pour chaque service (même sur des valeurs non encore enregistrées).
- **Journal en direct** avec filtres et recherche.
- Affichage adapté au téléphone, thème sombre, polices et icônes servies localement.
- **Sécurité** : accessible uniquement depuis la machine (tunnel SSH), code d'installation au premier lancement, mot de passe haché (scrypt), blocage après 5 échecs, protection CSRF, en-têtes stricts, secrets jamais réaffichés et masqués dans le journal.
- Premier lancement : le `.env` est importé automatiquement dans `donnees/config.json`.
- `--lecture-seule` : pour essayer l'interface sans rien ajouter, supprimer ni notifier.

**Sous le capot**
- Le programme est découpé en modules (`autodl/`) ; `c411_autodl.py` reste la commande à utiliser.
- Tous les réglages sont décrits à un seul endroit (`autodl/config.py`) ; toutes les erreurs de configuration sont listées d'un coup ; une valeur vide prend la valeur par défaut.
- Nouveaux réglages facultatifs : `PROWLARR_URL`, `PROWLARR_API_KEY` (état de Prowlarr dans l'interface).
- Le bilan n'enregistre plus de relevé pendant un essai à blanc.
- 115 tests (59 de plus).

**Mise à jour depuis la v1** : rien n'est perdu. Avec Docker, prends le nouveau `docker-compose.yml` pour avoir l'interface ; sans interface, la ligne de commande fonctionne exactement comme avant.

## v1.5.1 — 2026-11-05

Mise à jour de la documentation :
- **Prérequis** : Python 3.10+ **ou** Docker, qui ne demande pas Python.
- La section **Linux / VPS** présente les deux façons de tourner 24 h/24 (systemd ou Docker) et le passage de l'une à l'autre avec `migrer_vers_docker.sh`.
- **Mode freeleech** : conseil de prudence pour un premier freeleech (réglages modestes, vérification dans le bilan).
- **FAQ Docker** : « Permission denied » sur `donnees/` ou `.env`, et adresses `localhost` injoignables depuis un conteneur.
- **Sécurité** : cross-seed parmi les services contactés, et conteneur non root sans données personnelles dans l'image.
- Réglage `PAGE_SIZE` documenté, sommaire complété.

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
