# c411-autodl

[![GitHub stars](https://img.shields.io/github/stars/Xeerac/c411-autodl?style=social)](https://github.com/Xeerac/c411-autodl/stargazers)
[![Licence MIT](https://img.shields.io/github/license/Xeerac/c411-autodl)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)

**Ajoute automatiquement dans ta seedbox les nouveaux torrents c411 qui t'intéressent, sans jamais faire passer ton ratio sous le seuil que tu choisis.**

Le programme surveille les catégories c411 de ton choix, par exemple eBooks ou Comics/Manga. Dès qu'un torrent correspond à tes critères, il l'envoie dans ton qBittorrent, qui le télécharge puis le seede. Tu peux être prévenu sur Discord ou Telegram.

- ✅ **Aucune installation compliquée** : un seul fichier Python, sans dépendance. Il tourne sous Windows, Linux et sur un VPS.
- ✅ **Pas besoin de SSH sur la seedbox** : tout passe par l'API officielle de c411 et par la WebUI de qBittorrent.
- ✅ **Protection du ratio** : rien n'est téléchargé si ton ratio passerait sous le minimum choisi. Le freeleech est pris en compte.
- ✅ **Cible ce qui rapporte de l'upload** : ignore les torrents déjà sur-seedés et traite en priorité les plus demandés (beaucoup de leechers, peu de seeders).
- ✅ **Filtres** : catégories, complétés, seeders, leechers, taille min/max, formats (epub, cbz…), mots requis ou exclus, groupes exclus, expression régulière.
- ✅ **Notifications** Discord et/ou Telegram, en option.
- ✅ **Fonctionne 24 h/24** : lanceur Windows et service systemd pour Linux, avec redémarrage automatique.

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
5. [Tous les réglages](#tous-les-réglages)
6. [Commandes](#commandes)
7. [Mettre à jour](#mettre-à-jour)
8. [Dépannage / FAQ](#dépannage--faq)
9. [Sécurité](#sécurité)

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

Il garde une trace de tout ce qu'il a ajouté, pour ne jamais ajouter deux fois le même torrent.

---

## Prérequis

- Un **compte c411**.
- Un **qBittorrent avec la WebUI activée**, sur une seedbox (Seedhost, Ultra.cc, etc.) ou sur ta propre machine. Testé avec la version 5.3 ; les versions 4.x récentes devraient aussi fonctionner.
- **Python 3.9 ou plus récent** sur la machine qui fera tourner le programme :
  - **Windows** : télécharge Python sur [python.org](https://www.python.org/downloads/). Pendant l'installation, **coche « Add python.exe to PATH »**.
  - **Debian / Ubuntu** : Python 3 est déjà installé. Sinon : `sudo apt install python3`.

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
| `PAGES` | `2` | Pages lues à chaque passage, avec 100 torrents par page (6 au maximum) |
| `MAX_PER_RUN` | `50` | Nombre maximum de torrents ajoutés par passage |
| `MIN_FREE_GB` | `20` | Espace disque à garder libre sur la seedbox, en Go |
| `BOUCLE_SECONDES` | `0` | Intervalle du mode continu si tu lances le programme sans `--boucle` (`0` = un seul passage) |
| `REQUEST_DELAY` | `1` | Pause entre deux requêtes vers c411, en secondes |
| `RATTRAPAGE_MOTS` | `epub,pdf,cbz,…` | Mots-clés utilisés par `--rattrapage` |

### qBittorrent

| Réglage | Défaut | Description |
|---|---|---|
| `QBIT_URL` | *(obligatoire)* | Adresse de la WebUI, sans `/api/v2` |
| `QBIT_USER` / `QBIT_PASS` | *(obligatoire)* | Identifiants de la WebUI |
| `QBIT_CATEGORY` | `c411-ebook` | Catégorie qBittorrent des torrents ajoutés (créée automatiquement) |
| `QBIT_TAGS` | `c411,autodl` | Tags ajoutés aux torrents |
| `QBIT_SAVEPATH` | *(vide)* | Dossier de téléchargement (vide = dossier par défaut de qBittorrent) |
| `QBIT_PAUSED` | `false` | `true` = les torrents sont ajoutés en pause |

### Notifications

| Réglage | Défaut | Description |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | *(vide)* | URL du webhook Discord |
| `TELEGRAM_BOT_TOKEN` | *(vide)* | Token du bot Telegram |
| `TELEGRAM_CHAT_ID` | *(vide)* | Ton identifiant Telegram |
| `NOTIF_PAUSES` | `true` | Prévenir aussi des pauses et reprises liées au ratio |

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

Ton `.env` et ton historique (`donnees/`) ne sont jamais écrasés par une mise à jour.

---

## Dépannage / FAQ

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
<summary><b>Où sont les journaux ?</b></summary>

- Dans `donnees/c411_autodl.log`, limité à 4 fichiers de 5 Mo. L'historique des torrents ajoutés est dans `donnees/state.json`.
- Avec le service Linux, tu peux aussi utiliser `journalctl -u c411-autodl`.
- En mode continu, le journal ne note que l'essentiel : ajouts, pauses et reprises liées au ratio, erreurs, et un signe de vie toutes les heures. Ajoute `-v` pour tout voir.
</details>

---

## Sécurité

- Le fichier **`.env` contient tes clés et tes mots de passe : ne le partage jamais**, ni en capture d'écran ni dans un message d'aide. Il est exclu de Git par le `.gitignore`.
- Donne à chaque clé API **le minimum de droits** nécessaire (voir l'étape 1). Si une clé fuit, supprime-la sur c411 et crées-en une nouvelle.
- Ta **passkey c411** (dans l'URL d'annonce) n'est pas utilisée par ce programme : ne la mets nulle part.
- Le programme ne contacte que c411, ta WebUI qBittorrent et, si tu les as configurés, Discord ou Telegram.

---

## Contenu du dépôt

| Fichier | Rôle |
|---|---|
| `c411_autodl.py` | Le programme |
| `.env.example` | Modèle de configuration à copier en `.env` |
| `lancer_h24.bat` | Lancement en continu sous Windows |
| `lancer_h24.sh` | Lancement en continu sous Linux |
| `installer_service.sh` | Installation en service systemd (Linux) |
| `LICENSE` | Licence MIT |
| `donnees/` | Créé au premier lancement : historique et journal, non versionnés |

---

## Contribuer

Bugs, idées, améliorations : ouvre une [issue](https://github.com/Xeerac/c411-autodl/issues) ou une pull request. **Ne colle jamais ton `.env` ni tes clés** dans une issue : copie seulement le message d'erreur.

⭐ **Si ce projet te sert, laisse une étoile sur GitHub** (bouton *Star* en haut de la page) : c'est gratuit, et ça aide d'autres membres de c411 à le trouver.

## Licence

[MIT](LICENSE) : tu peux utiliser, modifier et redistribuer le code librement, à condition de conserver la mention de licence. Le logiciel est fourni sans aucune garantie.
