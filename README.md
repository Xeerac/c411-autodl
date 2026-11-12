# c411-autodl

[![GitHub stars](https://img.shields.io/github/stars/Xeerac/c411-autodl?style=social)](https://github.com/Xeerac/c411-autodl/stargazers)
[![Licence MIT](https://img.shields.io/github/license/Xeerac/c411-autodl)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Tests](https://github.com/Xeerac/c411-autodl/actions/workflows/tests.yml/badge.svg)](https://github.com/Xeerac/c411-autodl/actions/workflows/tests.yml)
[![Version](https://img.shields.io/github/v/release/Xeerac/c411-autodl)](https://github.com/Xeerac/c411-autodl/releases)

**Ajoute automatiquement dans ta seedbox les nouveaux torrents c411 qui t'intéressent, sans jamais faire passer ton ratio sous le seuil que tu choisis.**

Le programme surveille les catégories c411 de ton choix, par exemple eBooks ou Comics/Manga. Dès qu'un torrent correspond à tes critères, il l'envoie dans ton qBittorrent, qui le télécharge puis le seede. Tu peux être prévenu sur Discord ou Telegram, et tout suivre ou régler depuis une **interface web**.

- ✅ **Interface web** (nouveau en v2.0) : tableau de bord, configuration à la souris avec tests des services, journal en direct. Utilisable aussi sur téléphone.
- ✅ **Aucune installation compliquée** : Python seul, sans dépendance pour la ligne de commande. Il tourne sous Windows, Linux et sur un VPS.
- ✅ **Pas besoin de SSH sur la seedbox** : tout passe par l'API officielle de c411 et par la WebUI de qBittorrent.
- ✅ **Protection du ratio** : rien n'est téléchargé si ton ratio passerait sous le minimum choisi. Le freeleech est pris en compte.
- ✅ **Cible ce qui rapporte de l'upload** : ignore les torrents déjà sur-seedés et traite en priorité les plus demandés (beaucoup de leechers, peu de seeders).
- ✅ **Filtres** : catégories, complétés, seeders, leechers, taille min/max, formats (epub, cbz…), mots requis ou exclus, groupes exclus, expression régulière.
- ✅ **Réglages par catégorie et budget quotidien** : des filtres propres à chaque catégorie (musique en FLAC, films de 15 Go maximum…) et une limite de téléchargement par jour, sans compter les freeleech.
- ✅ **Suivi Hit & Run** : où en est chaque torrent par rapport aux 72 h de seed ou au ratio de 1,0 exigés par c411, avec une alerte si l'un d'eux ne seede plus avant d'être quitte.
- ✅ **Nettoyage automatique** (optionnel) : retire de qBittorrent les torrents supprimés de c411, avec une double vérification.
- ✅ **Bilan quotidien** (optionnel) : volume téléchargé et envoyé, évolution du ratio, et **ce qui rapporte le plus** par type de contenu.
- ✅ **Une catégorie qBittorrent par type** (optionnel) : `c411-ebook`, `c411-bd`, `c411-presse`…
- ✅ **Intégration cross-seed** (optionnel) : prévient cross-seed dès qu'un téléchargement est terminé.
- ✅ **Mode freeleech** (optionnel) : pendant un freeleech sur ton compte, la recherche s'élargit automatiquement (plus de catégories, plus de torrents, plus gros), puisque télécharger ne coûte rien.
- ✅ **Alertes** : panne du programme, espace disque bas, tracker c411 injoignable, certificat SSL qui expire, torrent à risque de Hit & Run.
- ✅ **Notifications** Discord et/ou Telegram, en option.
- ✅ **Fonctionne 24 h/24** : lanceur Windows, service systemd pour Linux ou **conteneur Docker**, avec redémarrage automatique.

> ⚠️ Projet communautaire, **non affilié à c411**. Il utilise uniquement l'API publique documentée sur c411.org (*Intégrations API*). Respecte les règles du site : tu restes responsable de ce que tu télécharges avec ton compte.

---

## Sommaire

1. [Comment ça marche](#comment-ça-marche)
2. [Prérequis](#prérequis)
3. [Installation pas à pas](#installation-pas-à-pas)
   - [Étape 1 : créer les clés API c411](#étape-1--créer-les-clés-api-c411)
   - [Étape 2 : récupérer les accès qBittorrent](#étape-2--récupérer-les-accès-qbittorrent)
   - [Étape 3 : télécharger le programme](#étape-3--télécharger-le-programme)
   - [Étape 4 : configurer le fichier `.env`](#étape-4--configurer-le-fichier-env)
   - [Étape 5 : faire un essai à blanc](#étape-5--faire-un-essai-à-blanc)
   - [Étape 6 (optionnel) : notifications Discord / Telegram](#étape-6-optionnel--notifications-discord--telegram)
4. [Lancer en continu](#lancer-en-continu)
   - [Sous Windows](#sous-windows)
   - [Sur un serveur Linux / VPS (Debian, Ubuntu…)](#sur-un-serveur-linux--vps-debian-ubuntu)
   - [Avec Docker](#avec-docker)
5. [Interface web](#interface-web)
   - [Lancer l'interface](#lancer-linterface)
   - [Premier lancement](#premier-lancement)
   - [Y accéder depuis ton PC : le tunnel SSH](#y-accéder-depuis-ton-pc--le-tunnel-ssh)
   - [Accès par un nom de domaine (optionnel)](#accès-par-un-nom-de-domaine-optionnel)
   - [Double authentification](#double-authentification)
6. [Tous les réglages](#tous-les-réglages)
7. [Commandes](#commandes)
8. [Mettre à jour](#mettre-à-jour)
9. [Dépannage / FAQ](#dépannage--faq)
10. [Sécurité](#sécurité)
11. [Contenu du dépôt](#contenu-du-dépôt)
12. [Comment ce projet est fait](#comment-ce-projet-est-fait)
13. [Contribuer](#contribuer)
14. [Licence](#licence)

---

## Comment ça marche

Toutes les 5 minutes (c'est réglable), le programme :

1. **Lit ton ratio** sur c411. S'il est inférieur ou égal au minimum choisi (2,00 par défaut), il se met en pause et réessaie plus tard.
2. **Lit les derniers torrents** des catégories choisies.
3. **Filtre** les torrents selon tes critères (complétés, seeders, leechers, taille, formats, mots, groupes) et écarte ceux déjà présents dans ta seedbox.
4. **Classe les torrents restants par intérêt** : ceux qui ont beaucoup de leechers pour peu de seeders passent en premier, car ce sont eux qui te feront envoyer le plus.
5. **Calcule ton ratio après téléchargement**. Si un torrent le ferait passer sous le minimum, il le saute. Un torrent freeleech ne compte pas.
6. **Envoie le .torrent à qBittorrent**, qui télécharge puis seede.
7. **Te prévient** sur Discord ou Telegram, si tu l'as activé.
8. **Toutes les heures** (si `NETTOYAGE_SUPPRIMES=true`), il retire de qBittorrent les torrents qui ont été supprimés de c411.
9. **Toutes les heures** (si `INACTIFS_RETIRER=true`), il retire les torrents qui n'envoient plus rien depuis 30 jours, une fois le temps de seed exigé par c411 largement dépassé.
10. **Dès qu'un téléchargement est terminé** (si `CROSS_SEED_URL` est rempli), il prévient cross-seed.
11. **Chaque matin** (si `BILAN_QUOTIDIEN=true`), il t'envoie un bilan.

Il garde une trace de tout ce qu'il a ajouté, pour ne jamais ajouter deux fois le même torrent.

---

## Prérequis

- Un **compte c411**.
- Un **qBittorrent avec la WebUI activée**, sur une seedbox (Seedhost, Ultra.cc, etc.) ou sur ta propre machine. Testé avec la version 5.3 ; les versions 4.x récentes devraient aussi fonctionner.
- Sur la machine qui fera tourner le programme, **au choix** :
  - **Python 3.10 ou plus récent**.
    - **Windows** : télécharge Python sur [python.org](https://www.python.org/downloads/). Pendant l'installation, **coche « Add python.exe to PATH »**.
    - **Debian / Ubuntu** : Python 3 est déjà installé. Sinon : `sudo apt install python3`.
  - **Docker** : Python n'est alors pas nécessaire, l'image le contient (voir [Avec Docker](#avec-docker)).

Le programme n'a **pas besoin d'être installé sur la seedbox**. Il peut tourner sur ton PC, sur un Raspberry Pi ou sur un petit VPS, tant que cette machine peut joindre c411 et la WebUI de qBittorrent.

---

## Installation pas à pas

### Étape 1 : créer les clés API c411

Va sur **https://c411.org/user/integrations**. Il faut créer **deux clés**, chacune avec **un seul droit** coché. Les droits d'une clé ne peuvent plus être modifiés après sa création : si tu te trompes, supprime la clé et recrées-en une.

| Clé | Libellé (au choix) | Droit à cocher | Sert à |
|---|---|---|---|
| 1 | `autodl-torznab` | ☑ **Torznab/RSS (lecture)** | Lire le catalogue et télécharger les .torrent |
| 2 | `autodl-profil` | ☑ **Profil (lecture)** | Lire ton ratio |

> 🔒 Ne coche **rien d'autre**, en particulier pas « Upload de torrents » ni « DL gratuits (dépense) ») : le programme n'en a pas besoin. Avec des droits minimaux, une clé volée ne permet pas grand-chose.

Garde les deux clés de côté pour l'étape 4.

### Étape 2 : récupérer les accès qBittorrent

Il te faut trois informations :

- **L'adresse de la WebUI.** C'est l'adresse que tu ouvres dans ton navigateur pour accéder à qBittorrent, **sans** `/api/v2` à la fin. Par exemple :
  - Seedhost : `https://serveur.seedhost.eu/tonpseudo/qbittorrent`
  - qBittorrent à la maison : `http://192.168.1.20:8080`
- **Le nom d'utilisateur** de la WebUI.
- **Le mot de passe** de la WebUI.

En général, ce sont les identifiants que tu utilises pour te connecter à qBittorrent dans ton navigateur. Chez la plupart des hébergeurs de seedbox, on les trouve dans l'espace client.

### Étape 3 : télécharger le programme

**Avec Git :**

```bash
git clone https://github.com/Xeerac/c411-autodl.git
cd c411-autodl
```

**Sans Git :** sur la page GitHub, clique sur le bouton vert **Code**, puis sur **Download ZIP**, et décompresse l'archive où tu veux.

### Étape 4 : configurer le fichier `.env`

Le fichier `.env` contient toute ta configuration. Crée-le à partir du modèle :

- **Windows** : copie `.env.example` et renomme la copie en `.env`. Si Windows cache les extensions, active « Extensions de noms de fichiers » dans le menu Affichage de l'Explorateur.
- **Linux** : `cp .env.example .env`

Ouvre ensuite `.env` avec un éditeur de texte : Bloc-notes, Notepad++ ou VS Code sous Windows, `nano .env` sous Linux. Remplis **au minimum** ces lignes :

```ini
C411_API_KEY=ta_cle_torznab
C411_PROFILE_API_KEY=ta_cle_profil

QBIT_URL=https://serveur.seedhost.eu/tonpseudo/qbittorrent
QBIT_USER=ton_utilisateur
QBIT_PASS=ton_mot_de_passe
```

Puis adapte tes critères :

```ini
# Catégories : 7020 = eBooks, 7030 = Comics/Manga, 3030 = Livres audio
C411_CATEGORIES=7020,7030
# Au moins 1 complété et 1 seeder
MIN_COMPLETED=1
MIN_SEEDERS=1
# Taille maximum d'un torrent (0 = pas de limite)
TAILLE_MAX=2Go
# Ne télécharge que si le ratio reste au-dessus de 2.00
MIN_RATIO=2.0
```

Tous les réglages sont décrits dans [Tous les réglages](#tous-les-réglages).

> Écris les valeurs **sans guillemets et sans espace** autour du `=`.

### Étape 5 : faire un essai à blanc

Ouvre un terminal **dans le dossier du programme** :

- **Windows** : dans l'Explorateur, ouvre le dossier, clique dans la barre d'adresse, tape `powershell`, puis appuie sur Entrée.
- **Linux** : `cd ~/c411-autodl`

Lance ensuite :

```bash
python c411_autodl.py --dry-run
```

Sous Linux, remplace `python` par `python3`.

Le mode `--dry-run` **n'ajoute rien** : il montre seulement ce qui serait fait. Si tout va bien, tu obtiens quelque chose comme :

```
2026-11-04 18:51:55 INFO    Ratio actuel : 3.12
2026-11-04 18:51:56 INFO    qBittorrent v5.3.0 connecté
2026-11-04 18:51:56 INFO    Espace libre seedbox : 812.4 Go
2026-11-04 18:51:57 INFO    [dry-run] + Exemple.De.Livre.2025.FR.[EPUB]-NOTAG (0.5 Mo, 2 complétés, 51 seeders)
2026-11-04 18:51:57 INFO    [dry-run] + Exemple.De.BD.T01.FR.[CBZ]-NOTAG (206.3 Mo, 1 complétés, 21 seeders)
2026-11-04 18:51:57 INFO    Recherche cat 7020,7030 : 200 nouveaux torrents (200 au total)
2026-11-04 18:51:57 INFO    Terminé : 21 seraient ajoutés (412.6 Mo à télécharger), 179 ignorés par les filtres
```

Si tu as une erreur, consulte le [Dépannage](#dépannage--faq).

Quand le résultat te convient, fais un vrai passage :

```bash
python c411_autodl.py
```

Les torrents apparaissent dans qBittorrent, dans la catégorie `c411-ebook`, avec les tags `c411` et `autodl`.

### Étape 6 (optionnel) : notifications Discord / Telegram

À chaque passage où quelque chose est ajouté, tu reçois **un seul message**. Il contient la liste des torrents avec un lien vers leur page c411, le volume total et le ratio estimé. Tu es aussi prévenu quand le programme se met en pause ou reprend à cause du ratio. Pour couper ces messages de pause, mets `NOTIF_PAUSES=false`.

<details>
<summary><b>Discord</b></summary>

1. Sur ton serveur Discord, ouvre les paramètres du salon voulu (icône ⚙️).
2. Va dans **Intégrations**, puis **Webhooks**, puis **Nouveau webhook**.
3. Clique sur **Copier l'URL du webhook**.
4. Colle l'URL dans `.env` :
   ```ini
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
   ```
</details>

<details>
<summary><b>Telegram</b></summary>

1. Dans Telegram, ouvre une conversation avec **@BotFather** et envoie `/newbot`. Choisis un nom ; BotFather te donne un **token**.
2. Ouvre une conversation avec **ton nouveau bot** et envoie-lui n'importe quel message, sinon il n'a pas le droit de t'écrire.
3. Ouvre une conversation avec **@userinfobot** : il t'affiche ton **Id**, un nombre.
4. Dans `.env` :
   ```ini
   TELEGRAM_BOT_TOKEN=123456789:AAH...
   TELEGRAM_CHAT_ID=987654321
   ```
</details>

Tu peux activer Discord et Telegram en même temps. Pour tester :

```bash
python c411_autodl.py --test-notif
```

---

## Lancer en continu

### Sous Windows

Double-clique sur **`lancer_h24.bat`**. Une fenêtre s'ouvre : le programme vérifie toutes les 5 minutes et se relance tout seul s'il plante. Pour l'arrêter, ferme la fenêtre.

**Pour le lancer automatiquement au démarrage de Windows :**

1. Appuie sur `Win + R`, tape `shell:startup`, puis appuie sur Entrée.
2. Dans le dossier qui s'ouvre, fais un clic droit, puis **Nouveau** et **Raccourci**, et choisis `lancer_h24.bat`.

Le PC doit rester allumé et ne pas se mettre en veille. Pour du vrai 24 h/24, un petit VPS Linux est plus adapté.

### Sur un serveur Linux / VPS (Debian, Ubuntu…)

Prévu pour Debian 13. Toute distribution qui utilise systemd devrait fonctionner (Ubuntu, Raspberry Pi OS…).

Deux façons de le faire tourner 24 h/24 : un **service systemd**, décrit ci-dessous, ou un **conteneur Docker** (voir [Avec Docker](#avec-docker)), pratique si tu utilises déjà Docker pour cross-seed, Prowlarr… Tu peux passer de l'un à l'autre à tout moment avec `migrer_vers_docker.sh`.

**1. Mettre le programme sur le serveur.** Directement depuis le serveur :

```bash
git clone https://github.com/Xeerac/c411-autodl.git ~/c411-autodl
cd ~/c411-autodl
cp .env.example .env
nano .env        # remplis la configuration (Ctrl+O pour enregistrer, Ctrl+X pour quitter)
```

Tu peux aussi envoyer depuis ton PC Windows un dossier déjà configuré, avec PowerShell :

```powershell
scp -r C:\chemin\vers\c411-autodl utilisateur@ip-du-vps:~/
```

`~/` est ton dossier personnel sur le serveur, et le dossier `c411-autodl` y est créé automatiquement. Si ton serveur n'utilise pas le port SSH 22, ajoute `-P 2222`, avec un P majuscule.

**2. Tester :**

```bash
python3 c411_autodl.py --dry-run
python3 c411_autodl.py --test-notif     # si tu as configuré les notifications
```

**3. Installer le service**, pour un fonctionnement 24 h/24, un démarrage automatique avec le serveur et un redémarrage en cas de plantage :

```bash
sudo bash installer_service.sh
```

Le script :
- crée le service systemd `c411-autodl`, qui tourne **avec ton utilisateur et non en root** ;
- rend le `.env` lisible par toi seul ;
- démarre le service et affiche son état. Si tout va bien, tu vois `Active: active (running)`.

**Commandes utiles :**

```bash
journalctl -u c411-autodl -f              # suivre le journal en direct (Ctrl+C pour quitter)
sudo systemctl status c411-autodl         # état du service
sudo systemctl restart c411-autodl        # à faire après chaque modification du .env
sudo systemctl stop c411-autodl           # arrêter
sudo systemctl start c411-autodl          # démarrer
sudo bash installer_service.sh desinstaller   # supprimer le service (les fichiers restent)
```

Pour changer l'intervalle de vérification : `sudo INTERVALLE=120 bash installer_service.sh`.

Pour un essai rapide sans installer de service : `bash lancer_h24.sh`. Attention, il s'arrête si tu fermes ta connexion SSH.

> ⚠️ Ne fais pas tourner le programme **à deux endroits en même temps**, par exemple sur ton PC et sur le VPS. Chacun a son propre historique et ils ajouteraient tous les deux les mêmes torrents.

### Avec Docker

Si tu utilises déjà Docker (VPS, Unraid, Synology…), c411-autodl peut tourner dans un conteneur, à côté de cross-seed ou Prowlarr par exemple. Une **image prête à l'emploi** est publiée sur GitHub à chaque version : `ghcr.io/xeerac/c411-autodl`, pour **amd64** (PC, VPS) et **arm64** (Raspberry Pi, serveurs ARM). Elle contient Python et l'[interface web](#interface-web). **Pas besoin de cloner le dépôt.**

**1. Récupérer les deux fichiers et configurer :**

```bash
mkdir -p ~/c411-autodl/donnees && cd ~/c411-autodl
curl -fsSLO https://raw.githubusercontent.com/Xeerac/c411-autodl/main/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/Xeerac/c411-autodl/main/.env.example -o .env
nano .env          # remplis ta configuration (étape 4)
```

**2. Tester, puis lancer :**

```bash
docker compose run --rm c411-autodl --dry-run      # essai à blanc (télécharge l'image la première fois)
docker compose up -d                               # lancement en continu, avec l'interface web
docker compose logs -f c411-autodl                 # journal en direct (Ctrl+C pour quitter)
```

| Étiquette | Contenu |
|---|---|
| `latest` | La dernière version (celle du `docker-compose.yml` fourni) |
| `2.3` | La dernière correction de la 2.3 : pas de changement majeur sans le vouloir |
| `2.3.1` | Une version précise, qui ne bouge plus |

**Tu préfères construire l'image toi-même** à partir du code ? Clone le dépôt (`git clone https://github.com/Xeerac/c411-autodl.git`), remplace la ligne `image:` du `docker-compose.yml` par `build: .`, puis lance `docker compose up -d --build`.

Le conteneur tourne **avec l'utilisateur 1000**, pas en root. Le dossier `donnees/` et le fichier `.env` doivent donc lui être accessibles. Si ton utilisateur n'a pas l'identifiant 1000 (commande `id`), adapte la ligne `user:` du `docker-compose.yml`, ou bien :

```bash
sudo chown -R 1000:1000 donnees .env
```

**Tu utilises déjà la version systemd** (`installer_service.sh`) ? Une seule commande suffit pour passer sous Docker :

```bash
cd ~/c411-autodl && git pull
sudo bash migrer_vers_docker.sh
```

Le script :
1. vérifie que Docker est installé et que ta configuration est en place ;
2. reprend l'**utilisateur** et l'**intervalle** de ton service systemd ;
3. construit l'image et lance un **essai à blanc dans le conteneur**. S'il échoue, il s'arrête **sans rien changer** et ton service continue de tourner ;
4. arrête et désactive le service systemd, puis démarre le conteneur ;
5. vérifie que le conteneur tourne bien. Sinon, il **relance automatiquement le service systemd**.

Ton `.env` et ton dossier `donnees/` sont repris tels quels. Le conteneur utilise le **réseau de la machine**, donc les adresses en `localhost` de ton `.env` (qBittorrent, cross-seed) continuent de fonctionner sans modification. Les réglages propres à ta machine sont écrits dans `docker-compose.override.yml`, que Git ignore : tes futurs `git pull` ne créeront aucun conflit.

Pour **revenir à systemd** : `sudo bash migrer_vers_docker.sh --retour`.

**Toutes les commandes ponctuelles** passent par `docker compose run --rm c411-autodl …`, par exemple `--bilan`, `--nettoyage --dry-run`, `--inactifs --dry-run` ou `--recategoriser --dry-run`.

**Tu as déjà un `docker-compose.yml`**, avec cross-seed, Prowlarr… ? Copie le bloc `c411-autodl` du fichier fourni dans le tien, en adaptant les chemins de `volumes:`. Dans ce cas :

- **cross-seed** se joint par le nom de son conteneur et non par `localhost` : mets `CROSS_SEED_URL=http://cross-seed:2468` dans le `.env` ;
- **qBittorrent sur la même machine** se joint de la même façon : par le nom de son conteneur s'il est dans Docker, par exemple `QBIT_URL=http://qbittorrent:8080`.

**Mettre à jour :** `docker compose pull && docker compose up -d`. Si tu construis l'image toi-même : `git pull && docker compose up -d --build`.

**Sans interface ?** Remplace la ligne `command:` du `docker-compose.yml` par `command: ["--boucle", "300"]` et retire le bloc `ports:`. C'est le fonctionnement de la v1.

> ⚠️ Si tu passes de systemd à Docker, **arrête d'abord le service** : `sudo systemctl disable --now c411-autodl`. Sinon, les deux copies tourneraient en même temps.

---

## Interface web

Depuis la v2.0, c411-autodl a une **interface web** : un tableau de bord pour suivre ce qu'il fait, une page de configuration pour tout régler sans toucher au `.env`, et un journal en direct. Elle est **facultative** : la ligne de commande fonctionne exactement comme avant.

### Ce qu'on y trouve

- **Tableau de bord** : l'état du programme (actif, en pause, freeleech, en panne), ton ratio avec une jauge, le volume envoyé par tes torrents, le dernier et le prochain passage. On y voit aussi l'état de qBittorrent, de cross-seed et de Prowlarr (ces deux derniers seulement s'ils sont configurés), les **derniers ajouts** avec ce qu'ils ont déjà envoyé, le **rendement par type** et le **suivi Hit & Run** (torrents quittes, en seed, à risque). Si un budget quotidien est réglé, ce qu'il en reste s'affiche sous le ratio.
- **Ajouts** : tous les torrents ajoutés par le programme, avec recherche, filtres (type, Hit & Run, rien envoyé, absents de qBittorrent…) et tri (date, rendement, volume envoyé, taille).
- **Actions** : passage immédiat, pause et reprise, essai à blanc et bilan. Pour le nettoyage, le retrait des inactifs et le rangement par type : un **aperçu**, qui ne modifie jamais rien, et un bouton **Exécuter** qui le fait vraiment, après une **confirmation**. Le rangement depuis l'interface ne déplace aucun fichier. En lecture seule, aucune action réelle n'est possible.
- **Configuration** : tous les réglages, rangés par thème, avec une explication sous chaque champ. Un bouton **« Tester »** vérifie chaque service (clés c411, qBittorrent, cross-seed, Prowlarr, notifications) **avant même d'enregistrer**. Les changements sont vérifiés, puis pris en compte **sans redémarrage**.
- **Relevés** : chaque matin, ton ratio, ton total envoyé et ton total reçu sur c411 sont relevés et **comparés à la veille** (écart et pourcentage, ▲ en hausse, ▼ en baisse), avec la courbe du ratio jour après jour (un point par jour), l'envoyé de chaque journée, **le rendement de chaque catégorie au fil des jours** et tout l'historique.
- **Sécurité** : double authentification optionnelle (code à 6 chiffres) et rappel des protections actives.
- **Journal en direct**, avec filtres (ajouts, problèmes, freeleech, nettoyage, cross-seed) et recherche.
- Un affichage adapté au **téléphone**, avec les onglets en bas de l'écran.

### Lancer l'interface

**Avec Docker** (recommandé) : le `docker-compose.yml` fourni lance déjà l'interface. Elle écoute sur le port **8411, uniquement depuis la machine** (`127.0.0.1:8411`).

```bash
docker compose up -d
docker compose logs c411-autodl | grep "code d'installation"
```

**Sans Docker**, installe d'abord les dépendances de l'interface, puis lance-la :

```bash
pip install -r requirements-interface.txt
python c411_autodl.py --interface
```

Elle remplace alors `--boucle` : le moteur tourne en tâche de fond, piloté par l'interface. Pour un service systemd, remplace `--boucle 300` par `--interface` dans la ligne `ExecStart` du service.

| Option | Défaut | Rôle |
|---|---|---|
| `--interface` | – | Lance l'interface web et le moteur |
| `--port` | `8411` | Port de l'interface |
| `--hote` | `127.0.0.1` | Adresse d'écoute. Garde `127.0.0.1` hors Docker : l'interface n'est alors joignable que depuis la machine |
| `--lecture-seule` | – | Le moteur ne fait **rien** : ni ajout, ni suppression, ni rangement, ni notification. Pratique pour essayer l'interface sur une autre machine que celle qui fait vraiment tourner le programme |

### Premier lancement

1. Au démarrage, le programme affiche dans son journal un **code d'installation**, par exemple `4F2A-91C0-7B3E`. Il est aussi enregistré dans `donnees/code-installation.txt`.
2. Ouvre l'interface : la page d'installation te demande ce code, puis un nom d'utilisateur et un mot de passe (10 caractères minimum).
3. Ton `.env` est **importé automatiquement** dans `donnees/config.json`. Tu retrouves tous tes réglages.

Le code sert à ce que personne d'autre ne puisse créer le compte à ta place. Une fois le compte créé, il est supprimé.

À partir de là, **c'est `donnees/config.json` qui fait foi** : modifie tes réglages depuis l'interface, le `.env` n'est plus lu. Sans interface, rien ne change : le `.env` reste utilisé comme avant.

### Y accéder depuis ton PC : le tunnel SSH

**Par défaut**, l'interface n'est **pas exposée sur Internet**. Depuis ton PC, on y accède par un **tunnel SSH** : ta connexion SSH habituelle transporte aussi la page de l'interface. Si tu préfères une adresse du type `https://c411.mondomaine.fr`, voir [Accès par un nom de domaine](#accès-par-un-nom-de-domaine-optionnel).

**Avec PuTTY :**
1. Charge ta session, puis va dans **Connection → SSH → Tunnels**.
2. Mets **Source port** `8411` et **Destination** `localhost:8411`, puis clique sur **Add**.
3. Reviens dans **Session**, clique sur **Save** pour ne plus avoir à le refaire, puis sur **Open**.
4. Tant que PuTTY est connecté, l'interface s'ouvre sur **http://localhost:8411**.

**Avec un terminal** (Windows, macOS ou Linux), garde cette fenêtre ouverte :

```bash
ssh -L 8411:localhost:8411 utilisateur@ip-du-vps
```

Si l'interface tourne directement sur ton PC, pas besoin de tunnel : ouvre simplement http://localhost:8411.

### Accès par un nom de domaine (optionnel)

Le tunnel SSH n'est pas toujours pratique. Tu peux rendre l'interface accessible en **HTTPS sur ton propre domaine ou sous-domaine**, avec un certificat **Let's Encrypt** obtenu et renouvelé automatiquement. Tout se règle et se vérifie depuis l'interface.

**Prérequis :** un serveur (VPS) avec **[Caddy](https://caddyserver.com/docs/install)** installé, les ports **80 et 443** libres pour lui, et un nom de domaine dont tu gères le DNS (par exemple chez Cloudflare).

**1. Installer l'assistant serveur** (une seule fois, en root, depuis le dossier `c411-autodl`) :

```bash
sudo bash serveur/installer_domaine.sh
```

Tu utilises l'image Docker sans avoir cloné le dépôt ? Récupère d'abord le dossier `serveur/` à côté de ton `docker-compose.yml` :

```bash
cd ~/c411-autodl && mkdir -p serveur
curl -fsSL https://raw.githubusercontent.com/Xeerac/c411-autodl/main/serveur/installer_domaine.sh -o serveur/installer_domaine.sh
curl -fsSL https://raw.githubusercontent.com/Xeerac/c411-autodl/main/serveur/assistant_domaine.py -o serveur/assistant_domaine.py
sudo bash serveur/installer_domaine.sh
```

Pour des raisons de sécurité, le programme ne modifie jamais lui-même ton serveur web. L'interface dépose seulement le **nom de domaine** dans `donnees/domaine/`. Un petit assistant installé sur la machine (service systemd `c411-autodl-domaine`) le vérifie, écrit la configuration Caddy à partir d'un **modèle fixe**, la **valide** puis recharge Caddy. Si Caddy refuse la configuration, l'ancienne est remise. L'installation ajoute une seule ligne `import /etc/caddy/c411-autodl.caddy` à ton `Caddyfile`, après en avoir fait une copie : tes autres sites ne sont pas touchés. Pour tout retirer : `sudo bash serveur/installer_domaine.sh --retirer`.

**2. Créer l'enregistrement DNS** : un enregistrement **A** de ton sous-domaine vers l'adresse IP du serveur. Chez Cloudflare, mets-le d'abord en **gris** (« DNS only ») : le certificat s'obtient plus sûrement sans le proxy.

**3. Activer l'accès** dans **Configuration → Accès par domaine** : coche l'option, saisis le domaine et enregistre. La page vérifie toute seule, toutes les 10 secondes :

| Étape | Ce qui est vérifié |
|---|---|
| Nom de domaine | Le nom saisi est valide |
| DNS | Le domaine pointe bien vers ce serveur, ou vers quelle autre adresse |
| Proxy Cloudflare | S'il est actif avant le certificat, une alerte t'explique comment le désactiver le temps de l'installation |
| Assistant serveur | Il est installé et répond |
| Serveur web | Caddy est configuré pour ce domaine |
| Certificat SSL | Il est valide, avec son émetteur et sa date d'expiration. Si ton pare-feu bloque le port 80, la page te le dit |
| Accès depuis Internet | Si ton pare-feu n'ouvre le port 443 qu'à Cloudflare, la page te dit de réactiver le proxy |

**4. Réactiver le proxy Cloudflare** si tu le souhaites (nuage orange), une fois le certificat obtenu, avec le mode SSL/TLS sur **« Full (strict) »**. La page l'indique à la fin.

> 💡 **Pare-feu limité à Cloudflare** (`ufw` n'autorise les ports 80 et 443 que depuis Cloudflare) : ouvre le port 80 à tous le temps du certificat (`ufw allow 80/tcp`), puis referme-le une fois le proxy réactivé (`ufw delete allow 80/tcp`). Les renouvellements passent ensuite par Cloudflare.

Pour revenir au tunnel seul, décoche l'option : l'assistant retire le domaine de Caddy.

### Double authentification

Dans l'onglet **Sécurité**, tu peux activer un **code à 6 chiffres** demandé après le mot de passe, avec n'importe quelle application d'authentification : Google Authenticator, Aegis, 2FAS, Bitwarden, 1Password…

1. Clique sur **Configurer**, puis **scanne le QR code** avec ton application. Impossible de scanner ? Ajoute un compte avec la **clé de configuration** affichée à côté, ou, depuis ton téléphone, touche le lien « ouvrir directement l'application ».
2. Saisis le code affiché par l'application pour confirmer : c'est activé.

Elle est **optionnelle**, mais fortement conseillée si l'interface est accessible par un nom de domaine. **Téléphone perdu ?** Sur le serveur, `python c411_autodl.py --desactiver-2fa` la désactive (avec Docker : `docker compose exec c411-autodl python c411_autodl.py --desactiver-2fa`).

### Sécurité de l'interface

- **Accessible uniquement depuis la machine**, ou par le tunnel, par défaut. Le mot de passe reste obligatoire, même ainsi.
- **Par un nom de domaine** (si tu l'as activé) : HTTPS obligatoire (HSTS), cookies envoyés uniquement en HTTPS, **seul ton domaine est accepté**, et la vraie adresse du visiteur est lue, même derrière Cloudflare. En plus du blocage par adresse, **30 échecs en 15 minutes** depuis Internet, toutes adresses confondues, bloquent les connexions par le domaine pendant 15 minutes, sans couper le tunnel. Les pages sont exclues des moteurs de recherche, et une notification te prévient à chaque connexion depuis Internet (`DOMAINE_NOTIF_CONNEXION`).
- **Double authentification** optionnelle (voir ci-dessus).
- **Mot de passe haché** (scrypt). Après **5 échecs** en 15 minutes, l'adresse est bloquée pendant 15 minutes.
- **Clés et mots de passe jamais réaffichés** : un champ secret indique seulement s'il est enregistré. Le journal masque automatiquement toute valeur secrète.
- Protection contre les requêtes forgées (CSRF), en-têtes de sécurité stricts, et **aucune ressource externe** : polices et icônes sont servies par l'interface elle-même.
- Le journal note **quels** réglages ont été modifiés, jamais leurs valeurs.

---

## Tous les réglages

Tous les réglages se trouvent dans le fichier `.env`.

### c411

| Réglage | Défaut | Description |
|---|---|---|
| `C411_API_KEY` | *(obligatoire)* | Clé API avec le droit « Torznab/RSS (lecture) » |
| `C411_PROFILE_API_KEY` | *(obligatoire si `MIN_RATIO` > 0)* | Clé API avec le droit « Profil (lecture) » |
| `C411_URL` | `https://c411.org` | Adresse du site |
| `C411_CATEGORIES` | `7020,7030` | Catégories surveillées, séparées par des virgules (voir le tableau ci-dessous) |

**Catégories disponibles :**

| ID | Catégorie | ID | Catégorie |
|---|---|---|---|
| `2000` | Films | `3010` | Musique |
| `5000` | Séries TV | `3030` | Livres audio |
| `2060` | Anime (films) | `7020` | eBooks |
| `5070` | Anime (séries) | `7030` | Comics / Manga |
| `2070` | Documentaires | `4050` | Jeux PC |
| | | `4000` | Applications |

### Filtres

| Réglage | Défaut | Description |
|---|---|---|
| `MIN_COMPLETED` | `1` | Nombre minimum de « complétés » sur c411 |
| `MIN_SEEDERS` | `1` | Nombre minimum de seeders |
| `TAILLE_MAX` | `0` | Taille maximum d'un torrent : `500Mo`, `2Go`, `1.5Go`… (`0` = pas de limite) |
| `EXCLUDE_WORDS` | *(vide)* | Mots à exclure du titre, séparés par des virgules, sans tenir compte des majuscules (ex : `pdf,sample`) |
| `TAILLE_MIN` | `0` | Taille minimum d'un torrent : `100Ko`, `1Mo`… Écarte les fichiers suspects (`0` = pas de minimum) |
| `FORMATS` | *(vide)* | Formats acceptés, cherchés dans le titre (ex : `epub,cbz,cbr`). Vide = tous |
| `MOTS_REQUIS` | *(vide)* | Le titre doit contenir **au moins un** de ces mots (ex : `fr,french,vf`) |
| `GROUPES_EXCLUS` | *(vide)* | Groupes de release à exclure, c'est-à-dire ce qui suit le dernier tiret du titre (ex : `notag`) |
| `REGEX_EXCLUSION` | *(vide)* | Pour les avancés : expression régulière d'exclusion, sans tenir compte des majuscules (ex : `\bscann?e?\b\|\bocr\b` pour écarter les scans) |

### Cibler ce qui rapporte de l'upload

| Réglage | Défaut | Description |
|---|---|---|
| `MAX_SEEDERS` | `0` | Ignore les torrents qui ont déjà plus de N seeders (`0` = pas de limite) |
| `MIN_LEECHERS` | `0` | Ne prend que les torrents avec au moins N leechers (`0` = pas de minimum) |
| `TRI` | `interet` | `interet` : les plus demandés d'abord (leechers ÷ seeders). `recent` : ordre de c411, les plus récents d'abord |

> 💡 **Pourquoi c'est important :** sur c411, un ebook a souvent **50 seeders ou plus**. En le seedant, tu n'enverras presque rien, puisque des dizaines d'autres seeders répondent déjà à la demande. Pour faire monter ton volume envoyé, vise les torrents peu seedés et demandés. Un bon point de départ : `MAX_SEEDERS=20` et `TRI=interet`. Lance d'abord un `--dry-run -v` pour voir combien de torrents restent avec tes réglages.

### Ratio

| Réglage | Défaut | Description |
|---|---|---|
| `MIN_RATIO` | `2.0` | Le ratio doit rester **strictement supérieur** à cette valeur, même après le téléchargement. `0` désactive la règle |

### Limites et rythme

| Réglage | Défaut | Description |
|---|---|---|
| `PAGES` | `1` | Pages lues à chaque passage, avec 100 torrents par page (6 au maximum) |
| `PAGE_SIZE` | `100` | Nombre de torrents par page. 100 est le maximum accepté par c411 |
| `MAX_PER_RUN` | `50` | Nombre maximum de torrents ajoutés par passage |
| `MIN_FREE_GB` | `20` | Espace disque à garder libre sur la seedbox, en Go |
| `BOUCLE_SECONDES` | `0` | Intervalle du mode continu si tu lances le programme sans `--boucle` (`0` = un seul passage) |
| `REQUEST_DELAY` | `1` | Pause entre deux requêtes vers c411, en secondes |
| `RATTRAPAGE_MOTS` | `epub,pdf,cbz,…` | Mots-clés utilisés par `--rattrapage` |

### Catégories et budget

Pour surveiller des catégories très différentes (eBooks, musique, films…), les réglages généraux ne suffisent plus : `FORMATS=epub,cbz` écarterait toute la musique. Les **réglages par catégorie** remplacent, pour une catégorie, certains réglages généraux.

| Réglage | Défaut | Description |
|---|---|---|
| `PROFILS_CATEGORIES` | *(vide)* | Une ligne par catégorie dans l'interface (ou « ; » entre deux profils dans le `.env`), au format `catégorie: réglage=valeur réglage=valeur` |
| `BUDGET_JOUR` | *(vide)* | Ce que c411 peut compter en « reçu » par jour, toutes catégories confondues. Les freeleech ne comptent pas. Vide = pas de limite. Exemple : `20Go` |

Exemple :

```
3010: formats=flac taille_max=2Go par_passage=3
2030: taille_max=15Go seeders_max=10 par_passage=1 budget_jour=30Go
2000: completes_min=5
```

| Réglage du profil | Remplace |
|---|---|
| `formats`, `mots_requis`, `mots_exclus` | `FORMATS`, `MOTS_REQUIS`, `EXCLUDE_WORDS` |
| `taille_min`, `taille_max` | `TAILLE_MIN`, `TAILLE_MAX` |
| `completes_min`, `seeders_min`, `seeders_max`, `leechers_min` | `MIN_COMPLETED`, `MIN_SEEDERS`, `MAX_SEEDERS`, `MIN_LEECHERS` |
| `par_passage` | Nombre maximum d'ajouts de cette catégorie par passage (`MAX_PER_RUN` reste la limite totale) |
| `budget_jour` | Budget quotidien propre à cette catégorie, en plus de `BUDGET_JOUR` |

- La catégorie exacte (`2030`) l'emporte sur sa famille (`2000`), qui vaut pour toutes ses sous-catégories.
- Ce qu'un profil ne précise pas reste réglé par la configuration générale.
- Pense à ajouter la catégorie à `C411_CATEGORIES`, sinon elle n'est pas surveillée.
- Le budget du jour compte ce que c411 comptera vraiment : rien pour un freeleech, la moitié pour un torrent à 50 %. Au-delà, plus rien n'est ajouté jusqu'au lendemain.

### qBittorrent

| Réglage | Défaut | Description |
|---|---|---|
| `QBIT_URL` | *(obligatoire)* | Adresse de la WebUI, sans `/api/v2` |
| `QBIT_USER` / `QBIT_PASS` | *(obligatoire)* | Identifiants de la WebUI |
| `QBIT_CATEGORY` | `c411-ebook` | Catégorie qBittorrent des torrents ajoutés (créée automatiquement) |
| `QBIT_TAGS` | `c411,autodl` | Tags ajoutés aux torrents |
| `QBIT_SAVEPATH` | *(vide)* | Dossier de téléchargement (vide = dossier par défaut de qBittorrent) |
| `QBIT_PAUSED` | `false` | `true` = les torrents sont ajoutés en pause |
| `QBIT_CATEGORIE_PAR_TYPE` | `false` | `true` = une catégorie par type de contenu, à la place de `QBIT_CATEGORY` (voir ci-dessous) |
| `QBIT_CATEGORIE_PREFIXE` | `c411` | Début du nom de ces catégories |

**Catégories par type** (`QBIT_CATEGORIE_PAR_TYPE=true`) : chaque torrent est rangé selon sa catégorie c411.

| Catégorie c411 | Catégorie qBittorrent |
|---|---|
| `7020` eBooks | `c411-ebook` |
| `7030` BD, comics, mangas | `c411-bd` |
| `7010` Presse | `c411-presse` |
| `3030` Livres audio | `c411-livre-audio` |
| `3xxx` Musique | `c411-musique` |
| `2xxx` Films et vidéos | `c411-film` |
| `5xxx` Séries et émissions | `c411-serie` |
| `4xxx` Logiciels | `c411-logiciel` |
| `1xxx` Jeux | `c411-jeu` |

Les catégories sont créées automatiquement dans qBittorrent.

**Ranger les torrents déjà présents** : `python c411_autodl.py --recategoriser --dry-run` montre ce qui serait rangé, puis `python c411_autodl.py --recategoriser` le fait. Le type exact de chaque torrent est retrouvé sur c411.

- Par défaut, qBittorrent **déplace les fichiers** dans le dossier de la nouvelle catégorie. Les torrents dont les fichiers servent aussi à un autre torrent (cross-seed) sont **laissés en place**, car les déplacer casserait l'autre torrent.
- Avec `--garder-emplacement`, seule l'étiquette change et **aucun fichier ne bouge**. Les torrents partagés sont alors rangés aussi.

### Nettoyage des torrents supprimés de c411

Quand un torrent est supprimé de c411 (retiré par son uploader, doublon, etc.), il reste dans qBittorrent avec une erreur de tracker et ne rapporte plus rien. Le nettoyage s'en occupe.

| Réglage | Défaut | Description |
|---|---|---|
| `NETTOYAGE_SUPPRIMES` | `false` | `true` active le nettoyage |
| `NETTOYAGE_ACTION` | `fichiers` | `fichiers` : retire le torrent **et supprime ses fichiers**. `torrent` : retire le torrent, garde les fichiers. `pause` : met en pause et ajoute le tag `c411-supprime`, sans rien supprimer |
| `NETTOYAGE_TAG` | `autodl` | Tag des torrents gérés par le programme : seuls eux sont nettoyés, envoyés à cross-seed et comptés dans le bilan |
| `NETTOYAGE_MINUTES` | `60` | Fréquence de la vérification |

**Sécurités :**
- un torrent n'est retiré que si **deux signaux concordent** : les trackers c411 de qBittorrent signalent sa suppression (par exemple « Torrent removed by its uploader »), **et** l'API c411 confirme qu'il n'existe plus. Une panne de c411 ou une erreur réseau ne peut donc rien supprimer ;
- si les fichiers servent aussi à un **autre torrent** (cross-seed sur un autre tracker), seul le torrent c411 est retiré et les fichiers sont gardés ;
- tes torrents ajoutés à la main ne sont jamais touchés, car ils n'ont pas le tag `autodl`.

Pour voir ce qui serait retiré, sans rien toucher : `python c411_autodl.py --nettoyage --dry-run`.

### Retrait des torrents inactifs

Un torrent qui n'envoie plus rien depuis des semaines occupe de la place sans rapporter. Le retrait des inactifs fait le tri, en respectant la règle **Hit & Run de c411** : un torrent doit être seedé **72 h** (ou atteindre un ratio de 1,0) avant de pouvoir être retiré.

| Réglage | Défaut | Description |
|---|---|---|
| `INACTIFS_RETIRER` | `false` | `true` active le retrait des inactifs |
| `INACTIFS_JOURS` | `30` | Un torrent est inactif s'il n'a rien envoyé depuis ce nombre de jours |
| `INACTIFS_SEED_MIN_HEURES` | `96` | Temps de seed minimum avant tout retrait. **Jamais moins de 72 h**, même si tu indiques moins ; 96 h = 24 h de marge |
| `INACTIFS_ACTION` | `fichiers` | `fichiers` : retire le torrent **et supprime ses fichiers**. `torrent` : garde les fichiers. `pause` : met en pause avec le tag `inactif` |
| `INACTIFS_MAX_PAR_JOUR` | `10` | Retraits maximum par jour, le reste attend le lendemain |

**Un torrent n'est retiré que si toutes ces conditions sont réunies :**
- il porte le tag `autodl` : tes torrents ajoutés à la main et les cross-seeds ne sont jamais touchés ;
- il est complet et a seedé au moins `INACTIFS_SEED_MIN_HEURES`, d'après le temps de seed de qBittorrent. Le ratio par torrent n'est pas utilisé pour aller plus vite, car celui de qBittorrent peut différer de celui de c411 ;
- il n'a rien transféré depuis `INACTIFS_JOURS` jours ;
- **personne ne l'attend** : aucun leecher connecté, ni annoncé par le tracker ;
- un tracker c411 répond normalement : un tracker en panne fausserait les informations précédentes.

Si les fichiers servent aussi à un **autre torrent** (cross-seed), ils sont gardés. Les plus anciennement inactifs partent en premier.

Pour voir ce qui serait retiré, sans rien toucher : `python c411_autodl.py --inactifs --dry-run`, ou le bouton « Aperçu des inactifs » du tableau de bord.

### Mode freeleech

Pendant un **freeleech sur ton compte** (événement du site, fenêtre freeleech, freeleech personnel), ce que tu télécharges **ne compte pas** dans ton ratio, mais ce que tu envoies compte. C'est le meilleur moment pour récupérer beaucoup de contenu à seeder. Avec `FREELEECH_MODE=true`, le programme le détecte via ton profil c411 et :

- ajoute les catégories de `FREELEECH_CATEGORIES` à sa recherche, par exemple les films et les séries ;
- autorise jusqu'à `FREELEECH_MAX_PAR_PASSAGE` torrents par passage, et des torrents jusqu'à `FREELEECH_TAILLE_MAX` ;
- ne se met **pas** en pause même si ton ratio est sous `MIN_RATIO`, puisque télécharger ne peut plus le faire baisser ;
- ajoute le tag `freeleech` aux torrents récupérés ;
- te prévient au **début** et à la **fin** du freeleech, puis revient tout seul aux réglages normaux.

| Réglage | Défaut | Description |
|---|---|---|
| `FREELEECH_MODE` | `false` | `true` active le mode (nécessite `C411_PROFILE_API_KEY`) |
| `FREELEECH_CATEGORIES` | *(vide)* | Catégories ajoutées pendant le freeleech, par exemple `2030,5000` (films, séries) |
| `FREELEECH_MAX_PAR_PASSAGE` | `100` | Nombre maximum d'ajouts par passage pendant le freeleech |
| `FREELEECH_TAILLE_MAX` | *(vide)* | Taille maximum pendant le freeleech, par exemple `30Go` (vide = `TAILLE_MAX`) |
| `FREELEECH_IGNORER_FORMATS` | `true` | Ignore `FORMATS` pendant le freeleech, sinon `FORMATS=epub,cbz` écarterait films et séries |

Tous tes autres filtres (`MAX_SEEDERS`, `MIN_COMPLETED`, `MIN_FREE_GB`…) restent actifs, et `MIN_FREE_GB` protège toujours l'espace disque de la seedbox.

> 💡 **Conseil de prudence :** pendant un freeleech, le programme compte les téléchargements comme gratuits, d'après ce qu'indique ton profil c411. Pour ton premier freeleech, commence avec des réglages modestes, par exemple `FREELEECH_CATEGORIES` vide, `FREELEECH_MAX_PAR_PASSAGE=30` et `FREELEECH_TAILLE_MAX=5Go`. Vérifie ensuite dans le bilan du lendemain que ton volume **reçu** n'a pas augmenté. Une fois que c'est confirmé, tu peux ouvrir les films et les séries.

### Alerte en cas de panne

Si le programme échoue `ALERTE_APRES` passages d'affilée (seedbox injoignable, c411 en panne, clé expirée…), tu reçois une notification avec la dernière erreur. Une autre suit quand tout repart, avec la durée de la panne. Il faut que les notifications Discord ou Telegram soient configurées.

| Réglage | Défaut | Description |
|---|---|---|
| `ALERTE_PANNE` | `true` | `false` désactive l'alerte |
| `ALERTE_APRES` | `3` | Nombre de passages en échec avant l'alerte (3 = 15 min avec un passage toutes les 5 min) |
| `ALERTE_DISQUE_GO` | `50` | Alerte quand la seedbox passe sous ce nombre de Go libres (`0` = désactivée) |
| `ALERTE_TRACKER` | `10` | Alerte quand au moins ce nombre de torrents n'a plus de tracker fonctionnel depuis plus d'une heure : maintenance de c411, passkey changée… (`0` = désactivée) |
| `ALERTE_CERTIFICAT` | `true` | Accès par domaine : alerte si le certificat SSL expire dans moins de 14 jours, ou si l'assistant serveur ne répond plus |
| `ALERTE_HIT_AND_RUN` | `true` | Alerte quand un torrent pas encore quitte ne seede plus (voir [Suivi Hit & Run](#suivi-hit--run)) |

Les alertes sont vérifiées une fois par heure. Chacune n'est envoyée qu'une fois, puis de nouveau seulement si le problème disparaît et revient.

### Suivi Hit & Run

La règle de c411 : quand tu télécharges un torrent, tu dois le seeder **72 h**, ou atteindre un **ratio de 1,0** sur ce torrent. Le compteur démarre 24 h après le début du téléchargement. (Le système est désactivé sur c411 pour l'instant, mais il peut revenir.)

Le tableau de bord suit chaque torrent ajouté par le programme :

| État | Signification |
|---|---|
| **Quitte** | 72 h de seed ou ratio de 1,0 atteints |
| **En seed** | Il seede normalement, avec le nombre d'heures restantes |
| **Téléchargement** | Pas encore complet |
| **À risque** | Pas encore quitte, et il ne seede plus (en pause, arrêté, en erreur, fichiers manquants), ou il est encore en téléchargement plus de 24 h après l'ajout |

Le décompte est **prudent** : il s'appuie sur le temps de seed de qBittorrent, qui ne démarre qu'à la fin du téléchargement. Le suivi ne supprime jamais rien : il te prévient seulement, pour que tu relances le torrent.

### cross-seed

Si tu utilises [cross-seed](https://www.cross-seed.org) **sur la même machine**, le programme le prévient dès qu'un torrent qu'il a ajouté a fini de télécharger. cross-seed cherche alors tout de suite la même release sur tes autres trackers, au lieu d'attendre son prochain passage. Tu y arrives ainsi **parmi les premiers seeders**, et c'est là qu'on envoie le plus.

| Réglage | Défaut | Description |
|---|---|---|
| `CROSS_SEED_URL` | *(vide)* | Adresse de cross-seed, par exemple `http://localhost:2468`. Vide = désactivé |
| `CROSS_SEED_API_KEY` | *(vide)* | Clé de l'API cross-seed : `cross-seed api-key`, ou avec Docker `docker compose exec cross-seed cross-seed api-key` |

Au premier lancement, les torrents déjà terminés ne sont **pas** renvoyés : la recherche quotidienne de cross-seed s'en occupe déjà. Si cross-seed est arrêté, le programme réessaie au passage suivant.

### Bilan quotidien

| Réglage | Défaut | Description |
|---|---|---|
| `BILAN_QUOTIDIEN` | `false` | `true` = un bilan par jour, dans le journal et sur Discord/Telegram |
| `BILAN_HEURE` | `8` | Heure d'envoi (0 à 23). C'est aussi l'heure du relevé quotidien de l'onglet « Relevés » |

Exemple :

```
📊 Bilan c411-autodl (depuis le 04/11 à 08:00)
• 12 torrent(s) ajouté(s) · 1.80 Go téléchargés · 6.40 Go envoyés
• Ratio c411 : 2.80 (+0.04)
Rendement par type (envoyé ÷ taille, depuis l'ajout) :
• bd : ×7.31 (47 torrent(s), 47.46 Go envoyés)
• ebook : ×6.50 (94 torrent(s), 12.76 Go envoyés)
• livre-audio : ×0.19 (1 torrent(s), 53.0 Mo envoyés)
```

Le **rendement** indique combien chaque type de contenu a renvoyé par rapport à sa taille : ×7 veut dire qu'en moyenne, chaque torrent a été envoyé 7 fois. Ça permet de voir quelles catégories et quels réglages valent le coup.

Le premier bilan arrive le lendemain de l'activation, une fois qu'il y a une journée à comparer. Indépendamment du bilan, l'onglet **Relevés** de l'interface note chaque jour à cette heure ton ratio, ton envoyé et ton reçu. Il faut pour ça la clé API Profil, et le premier relevé est pris dès le démarrage. Pour en voir un tout de suite : `python c411_autodl.py --bilan`.

### Notifications

| Réglage | Défaut | Description |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | *(vide)* | URL du webhook Discord |
| `TELEGRAM_BOT_TOKEN` | *(vide)* | Token du bot Telegram |
| `TELEGRAM_CHAT_ID` | *(vide)* | Ton identifiant Telegram |
| `NOTIF_PAUSES` | `true` | Prévenir aussi des pauses et reprises liées au ratio |

Sur Discord, les messages arrivent sous forme d'**embeds** : une barre de couleur selon le type de message (vert pour un ajout, orange pour une pause, rouge pour une panne…). Le **bilan quotidien** y est présenté en tuiles (envoyé, téléchargé, ajouts, ratio avec ▲ ou ▼, envoyé ÷ téléchargé, torrents en seed), avec un tableau du rendement par type et le podium des torrents qui ont le plus envoyé. Telegram reçoit le même contenu en texte.

### Accès par domaine

Voir [Accès par un nom de domaine](#accès-par-un-nom-de-domaine-optionnel).

| Réglage | Défaut | Description |
|---|---|---|
| `DOMAINE_ACTIF` | `false` | `true` rend l'interface accessible en HTTPS sur `DOMAINE_NOM` (nécessite Caddy et l'assistant serveur) |
| `DOMAINE_NOM` | *(vide)* | Domaine ou sous-domaine, par exemple `c411.mondomaine.fr` |
| `DOMAINE_NOTIF_CONNEXION` | `true` | Notification à chaque connexion à l'interface depuis Internet |

---

## Commandes

| Commande | Effet |
|---|---|
| `python c411_autodl.py --dry-run` | Essai à blanc : affiche ce qui serait ajouté, sans rien ajouter |
| `python c411_autodl.py` | Un seul passage |
| `python c411_autodl.py --boucle` | En continu, un passage toutes les 300 s (5 min) |
| `python c411_autodl.py --boucle 600` | En continu, un passage toutes les 600 s |
| `python c411_autodl.py --pages 6` | Lit 6 pages au lieu de la valeur de `PAGES` |
| `python c411_autodl.py --rattrapage` | Parcourt le catalogue au maximum, pour remplir la seedbox la première fois |
| `python c411_autodl.py --test-notif` | Envoie une notification de test |
| `python c411_autodl.py --nettoyage --dry-run` | Affiche les torrents supprimés de c411 qui seraient retirés, sans rien toucher |
| `python c411_autodl.py --nettoyage` | Lance le nettoyage tout de suite |
| `python c411_autodl.py --inactifs --dry-run` | Affiche les torrents inactifs qui seraient retirés, sans rien toucher |
| `python c411_autodl.py --inactifs` | Retire tout de suite les torrents inactifs (même si `INACTIFS_RETIRER=false`) |
| `python c411_autodl.py --bilan` | Affiche le bilan tout de suite (et l'envoie en notification) |
| `python c411_autodl.py --recategoriser --dry-run` | Montre comment les torrents existants seraient rangés par type |
| `python c411_autodl.py --recategoriser` | Range les torrents existants (ajoute `--garder-emplacement` pour ne déplacer aucun fichier) |
| `python c411_autodl.py --interface` | Lance l'interface web et le moteur (voir [Interface web](#interface-web)) |
| `python c411_autodl.py --interface --lecture-seule` | Interface pour essayer, sans rien ajouter, supprimer ni notifier |
| `python c411_autodl.py --desactiver-2fa` | Secours : désactive la double authentification de l'interface (téléphone perdu) |
| `sudo bash serveur/installer_domaine.sh` | Installe l'assistant d'accès par nom de domaine (Caddy), voir [Accès par un nom de domaine](#accès-par-un-nom-de-domaine-optionnel) |
| `python c411_autodl.py --version` | Affiche la version |
| `python c411_autodl.py -v` | Mode détaillé : affiche chaque torrent ignoré et la raison |

Les options se combinent, par exemple `--rattrapage --dry-run`.

> 💡 **Premier remplissage :** l'API de c411 renvoie au maximum 600 résultats par recherche. `--rattrapage` contourne cette limite en lançant une recherche par catégorie et par mot-clé. Lance-le d'abord avec `--dry-run` pour voir le volume total, puis vérifie que ton ratio peut le supporter.

---

## Mettre à jour

```bash
cd c411-autodl
git pull
```

Sur un VPS avec le service installé, relance-le ensuite : `sudo systemctl restart c411-autodl`.
Avec Docker et l'image publiée : `docker compose pull && docker compose up -d` (pas besoin de `git pull`).
Avec Docker et une image construite par toi : `git pull && docker compose up -d --build`.

Ton `.env`, ta configuration de l'interface et ton historique (`donnees/`) ne sont jamais écrasés par une mise à jour.

**Passer de la v1 à la v2 :** rien n'est perdu. Avec Docker, mets à jour comme d'habitude, en prenant le nouveau `docker-compose.yml` pour avoir l'interface. Au premier lancement, ton `.env` est importé automatiquement.

---

## Dépannage / FAQ

<details>
<summary><b>Mon domaine ne répond pas (« a mis trop de temps à répondre »), alors que tout est vert</b></summary>

Le plus souvent, le domaine pointe en direct vers le serveur (proxy Cloudflare désactivé, nuage gris) alors que le pare-feu n'accepte le port 443 que depuis Cloudflare. Réactive le proxy (nuage orange, mode SSL/TLS « Full (strict) »), ou ouvre le port 443 à tous (`ufw allow 443/tcp`). La page **Accès par domaine** le signale par l'étape « Accès depuis Internet ».

Juste après un changement dans Cloudflare, ton navigateur peut garder l'ancienne adresse quelques minutes : ferme-le complètement et rouvre-le.
</details>

<details>
<summary><b>Le certificat SSL reste « en cours »</b></summary>

- Let's Encrypt doit pouvoir joindre le serveur sur le **port 80** : vérifie ton pare-feu (la page le signale si `ufw` le bloque).
- Avec le proxy Cloudflare actif, si l'option « Always Use HTTPS » est activée, désactive le proxy le temps d'obtenir le certificat.
- Les messages de Caddy sont visibles avec `journalctl -u caddy -n 50`.
</details>

<details>
<summary><b>« qBittorrent : identifiants refusés » ou « connexion refusée (HTTP 401/403) »</b></summary>

- Vérifie `QBIT_USER` et `QBIT_PASS` en te connectant à la WebUI dans ton navigateur.
- Vérifie `QBIT_URL` : c'est l'adresse de la WebUI, **sans** `/api/v2` à la fin.
- Après plusieurs échecs, qBittorrent bloque ton adresse IP pendant un moment : attends quelques minutes.
</details>

<details>
<summary><b>« la clé C411_PROFILE_API_KEY n'a pas le scope Profil (lecture) »</b></summary>

La clé indiquée n'a pas le droit « Profil (lecture) ». Les droits d'une clé ne se modifient pas : crée une nouvelle clé avec ce droit coché et remplace-la dans `.env`.

Si tu ne veux pas de protection du ratio, mets `MIN_RATIO=0` : la clé Profil n'est alors plus nécessaire.
</details>

<details>
<summary><b>« Torznab : … » ou HTTP 401 côté c411</b></summary>

`C411_API_KEY` est absente, invalide ou n'a pas le droit « Torznab/RSS (lecture) ». Vérifie-la sur https://c411.org/user/integrations.
</details>

<details>
<summary><b>« Terminé : 0 seraient ajoutés »</b></summary>

C'est normal si :
- tout ce qui correspond à tes critères est **déjà dans ta seedbox** ;
- tes filtres sont trop stricts. Lance `python c411_autodl.py --dry-run -v` pour voir chaque torrent ignoré et pourquoi.

Un torrent qui vient de sortir a souvent **0 complété** : il ne sera pris qu'au passage suivant, une fois qu'au moins une personne l'aura terminé (avec `MIN_COMPLETED=1`).
</details>

<details>
<summary><b>« En pause : ratio X ≤ 2.00 »</b></summary>

Ton ratio est sous le minimum : le programme attend qu'il remonte et reprend tout seul. Pour changer le seuil, modifie `MIN_RATIO`.
</details>

<details>
<summary><b>« python » n'est pas reconnu (Windows)</b></summary>

Python n'est pas installé, ou il n'a pas été ajouté au PATH. Réinstalle-le depuis [python.org](https://www.python.org/downloads/) en cochant **« Add python.exe to PATH »**. Tu peux aussi essayer la commande `py` à la place de `python`.
</details>

<details>
<summary><b>Linux : « bash\r: No such file or directory » ou « $'\r': command not found »</b></summary>

Le fichier a été enregistré avec des fins de ligne Windows. Corrige-le avec `sed -i 's/\r$//' *.sh .env`, ou récupère le projet avec `git clone`.
</details>

<details>
<summary><b>Un nouveau torrent met quelques minutes à être détecté</b></summary>

c411 met son flux en cache pendant 5 minutes : c'est pour ça que le programme vérifie toutes les 5 minutes par défaut. Vérifier plus souvent ne rendrait pas la détection plus rapide.
</details>

<details>
<summary><b>Docker : « Permission denied » sur <code>donnees/</code> ou <code>.env</code></b></summary>

Le conteneur tourne avec l'utilisateur indiqué par la ligne `user:` du `docker-compose.yml` (1000 par défaut), et non en root. Ce même utilisateur doit pouvoir lire `.env` et écrire dans `donnees/` : `sudo chown -R 1000:1000 donnees .env`. Tu peux aussi mettre ton propre identifiant dans `user:` (commande `id`).
</details>

<details>
<summary><b>Docker : qBittorrent ou cross-seed injoignable alors que ça marchait avant</b></summary>

Dans un conteneur, `localhost` désigne le conteneur lui-même, pas ta machine. Deux solutions :
- utiliser le **nom du conteneur** visé, s'il est dans le même `docker-compose.yml` : `CROSS_SEED_URL=http://cross-seed:2468`, `QBIT_URL=http://qbittorrent:8080` ;
- ou faire tourner c411-autodl **sur le réseau de la machine** avec `network_mode: host`, ce que fait `migrer_vers_docker.sh`. Les adresses en `localhost` restent alors valables.
</details>

<details>
<summary><b>Interface : j'ai perdu le code d'installation</b></summary>

Il est enregistré dans `donnees/code-installation.txt` jusqu'à la création de ton compte. Il apparaît aussi dans le journal du programme : `docker compose logs c411-autodl | grep "code d'installation"`.
</details>

<details>
<summary><b>Interface : j'ai oublié mon mot de passe</b></summary>

Supprime le fichier `donnees/interface.json`, puis redémarre le programme. Un nouveau code d'installation s'affiche dans le journal, et tu peux recréer ton compte. Ta configuration (`donnees/config.json`) et ton historique ne sont pas touchés.
</details>

<details>
<summary><b>Interface : « localhost:8411 » ne s'ouvre pas</b></summary>

- Vérifie que ton tunnel SSH est bien ouvert. PuTTY doit rester connecté, avec la ligne `L8411  localhost:8411` dans Connection → SSH → Tunnels.
- Vérifie que l'interface tourne : `docker compose ps` doit montrer `127.0.0.1:8411->8411/tcp`.
- Si un autre programme utilise déjà le port 8411 sur ton PC, le tunnel ne peut pas s'ouvrir. Choisis un autre port local, par exemple `8412`, et ouvre http://localhost:8412.
</details>

<details>
<summary><b>Où sont les journaux ?</b></summary>

- Dans `donnees/c411_autodl.log`, limité à 4 fichiers de 5 Mo. L'historique des torrents ajoutés est dans `donnees/state.json`.
- Avec le service Linux, tu peux aussi utiliser `journalctl -u c411-autodl`.
- Avec Docker : `docker compose logs -f c411-autodl`.
- En mode continu, le journal ne note que l'essentiel : ajouts, pauses et reprises liées au ratio, erreurs, et un signe de vie toutes les heures. Ajoute `-v` pour tout voir.
</details>

---

## Sécurité

- Le fichier **`.env` contient tes clés et tes mots de passe : ne le partage jamais**, ni en capture d'écran ni dans un message d'aide. Il est exclu de Git par le `.gitignore`.
- Donne à chaque clé API **le minimum de droits** nécessaire (voir l'étape 1). Si une clé fuit, supprime-la sur c411 et crées-en une nouvelle.
- Ta **passkey c411** (dans l'URL d'annonce) n'est pas utilisée par ce programme : ne la mets nulle part.
- Le programme ne contacte que c411, ta WebUI qBittorrent et, si tu les as configurés, cross-seed, Discord ou Telegram.
- Avec Docker, le programme tourne avec un **utilisateur non root**, et l'image ne contient ni ta configuration ni tes données : elles sont montées au lancement.
- Par défaut, l'interface web n'est **pas exposée sur Internet**. Si tu l'ouvres sur un nom de domaine, active la **double authentification** : voir [Sécurité de l'interface](#sécurité-de-linterface).
- `donnees/config.json` (ta configuration de l'interface) et `donnees/interface.json` (ton compte, mot de passe haché) sont lisibles par leur propriétaire seulement. Ne les partage pas.

---

## Contenu du dépôt

| Fichier | Rôle |
|---|---|
| `c411_autodl.py` | Le lanceur : c'est la commande à utiliser |
| `autodl/` | Le programme : moteur, accès à c411 et qBittorrent, filtres, configuration, et l'interface web (`autodl/web/`) |
| `requirements-interface.txt` | Dépendances de l'interface web, déjà incluses dans l'image Docker |
| `.env.example` | Modèle de configuration à copier en `.env` |
| `lancer_h24.bat` | Lancement en continu sous Windows |
| `lancer_h24.sh` | Lancement en continu sous Linux |
| `installer_service.sh` | Installation en service systemd (Linux) |
| `Dockerfile`, `docker-compose.yml` | Lancement avec Docker (image publiée sur `ghcr.io/xeerac/c411-autodl` à chaque version, ou construite par toi) |
| `migrer_vers_docker.sh` | Bascule d'une installation systemd vers Docker, avec retour possible |
| `serveur/` | Assistant d'accès par nom de domaine (`installer_domaine.sh`, `assistant_domaine.py`), installé sur la machine hôte |
| `LICENSE` | Licence MIT |
| `CHANGELOG.md` | Historique des versions |
| `tests/` | Tests automatiques (`python -m unittest discover -s tests`), lancés par GitHub à chaque modification. Ceux de l'interface demandent `requirements-interface.txt` et `httpx` |
| `donnees/` | Créé au premier lancement : historique des ajouts, relevés quotidiens (`releves.json`), journal et configuration de l'interface, non versionnés |

---

## Comment ce projet est fait

Par souci de transparence : **ce projet est développé avec l'aide d'une IA** (Claude, d'Anthropic). Le code, les textes de l'interface et cette documentation sont écrits avec elle. Je ne suis pas développeur de métier.

Ce que je fais moi-même :
- je décide de ce que l'outil doit faire, à partir de mon propre usage de c411 et de ma seedbox ;
- je teste chaque nouveauté **en réel sur ma seedbox**, souvent plusieurs jours en version d'essai, avant de la publier ;
- je relis les règles de c411 (API, Hit & Run) avant toute fonction qui pourrait les toucher, et les options risquées sont **désactivées par défaut**, avec un aperçu qui ne modifie rien.

Et pour la fiabilité :
- chaque modification passe une **batterie de tests automatiques** (plus de 150), lancés par GitHub sous Linux et Windows, avec plusieurs versions de Python et la construction de l'image Docker ;
- le code est **ouvert** : tout le monde peut le lire, le vérifier et signaler un problème.

Si tu repères un bug ou quelque chose de mal fait, une [issue](https://github.com/Xeerac/c411-autodl/issues) est la bienvenue.

---

## Contribuer

Bugs, idées, améliorations : ouvre une [issue](https://github.com/Xeerac/c411-autodl/issues) ou une pull request. **Ne colle jamais ton `.env` ni tes clés** dans une issue : copie seulement le message d'erreur.

⭐ **Si ce projet te sert, laisse une étoile sur GitHub** (bouton *Star* en haut de la page) : c'est gratuit, et ça aide d'autres membres de c411 à le trouver.

## Licence

[MIT](LICENSE) : tu peux utiliser, modifier et redistribuer le code librement, à condition de conserver la mention de licence. Le logiciel est fourni sans aucune garantie.
