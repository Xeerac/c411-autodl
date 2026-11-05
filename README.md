# c411-autodl

[![GitHub stars](https://img.shields.io/github/stars/Xeerac/c411-autodl?style=social)](https://github.com/Xeerac/c411-autodl/stargazers)
[![Licence MIT](https://img.shields.io/github/license/Xeerac/c411-autodl)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Tests](https://github.com/Xeerac/c411-autodl/actions/workflows/tests.yml/badge.svg)](https://github.com/Xeerac/c411-autodl/actions/workflows/tests.yml)
[![Version](https://img.shields.io/github/v/release/Xeerac/c411-autodl)](https://github.com/Xeerac/c411-autodl/releases)

**Ajoute automatiquement dans ta seedbox les nouveaux torrents c411 qui t'intéressent, sans jamais faire passer ton ratio sous le seuil que tu choisis.**

Le programme surveille les catégories c411 de ton choix, par exemple eBooks ou Comics/Manga. Dès qu'un torrent correspond à tes critères, il l'envoie dans ton qBittorrent, qui le télécharge puis le seede. Tu peux être prévenu sur Discord ou Telegram.

- ✅ **Aucune installation compliquée** : un seul fichier Python, sans dépendance. Il tourne sous Windows, Linux et sur un VPS.
- ✅ **Pas besoin de SSH sur la seedbox** : tout passe par l'API officielle de c411 et par la WebUI de qBittorrent.
- ✅ **Protection du ratio** : rien n'est téléchargé si ton ratio passerait sous le minimum choisi. Le freeleech est pris en compte.
- ✅ **Cible ce qui rapporte de l'upload** : ignore les torrents déjà sur-seedés et traite en priorité les plus demandés (beaucoup de leechers, peu de seeders).
- ✅ **Filtres** : catégories, complétés, seeders, leechers, taille min/max, formats (epub, cbz…), mots requis ou exclus, groupes exclus, expression régulière.
- ✅ **Nettoyage automatique** (optionnel) : retire de qBittorrent les torrents supprimés de c411, avec une double vérification.
- ✅ **Bilan quotidien** (optionnel) : volume téléchargé et envoyé, évolution du ratio, et **ce qui rapporte le plus** par type de contenu.
- ✅ **Une catégorie qBittorrent par type** (optionnel) : `c411-ebook`, `c411-bd`, `c411-presse`…
- ✅ **Intégration cross-seed** (optionnel) : prévient cross-seed dès qu'un téléchargement est terminé.
- ✅ **Mode freeleech** (optionnel) : pendant un freeleech sur ton compte, la recherche s'élargit automatiquement (plus de catégories, plus de torrents, plus gros), puisque télécharger ne coûte rien.
- ✅ **Alerte en cas de panne** : notification si le programme échoue plusieurs fois d'affilée, puis quand tout repart.
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
8. **Toutes les heures** (si `NETTOYAGE_SUPPRIMES=true`), il retire de qBittorrent les torrents qui ont été supprimés de c411.
9. **Dès qu'un téléchargement est terminé** (si `CROSS_SEED_URL` est rempli), il prévient cross-seed.
10. **Chaque matin** (si `BILAN_QUOTIDIEN=true`), il t'envoie un bilan.

Il garde une trace de tout ce qu'il a ajouté, pour ne jamais ajouter deux fois le même torrent.

---

## Prérequis

- Un **compte c411**.
- Un **qBittorrent avec la WebUI activée**, sur une seedbox (Seedhost, Ultra.cc, etc.) ou sur ta propre machine. Testé avec la version 5.3 ; les versions 4.x récentes devraient aussi fonctionner.
- **Python 3.10 ou plus récent** sur la machine qui fera tourner le programme :
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

### Alerte en cas de panne

Si le programme échoue `ALERTE_APRES` passages d'affilée (seedbox injoignable, c411 en panne, clé expirée…), tu reçois une notification avec la dernière erreur. Une autre suit quand tout repart, avec la durée de la panne. Il faut que les notifications Discord ou Telegram soient configurées.

| Réglage | Défaut | Description |
|---|---|---|
| `ALERTE_PANNE` | `true` | `false` désactive l'alerte |
| `ALERTE_APRES` | `3` | Nombre de passages en échec avant l'alerte (3 = 15 min avec un passage toutes les 5 min) |

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
| `BILAN_HEURE` | `8` | Heure d'envoi (0 à 23) |

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

Le premier bilan arrive le lendemain de l'activation, une fois qu'il y a une journée à comparer. Pour en voir un tout de suite : `python c411_autodl.py --bilan`.

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
| `python c411_autodl.py --nettoyage --dry-run` | Affiche les torrents supprimés de c411 qui seraient retirés, sans rien toucher |
| `python c411_autodl.py --nettoyage` | Lance le nettoyage tout de suite |
| `python c411_autodl.py --bilan` | Affiche le bilan tout de suite (et l'envoie en notification) |
| `python c411_autodl.py --recategoriser --dry-run` | Montre comment les torrents existants seraient rangés par type |
| `python c411_autodl.py --recategoriser` | Range les torrents existants (ajoute `--garder-emplacement` pour ne déplacer aucun fichier) |
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
| `CHANGELOG.md` | Historique des versions |
| `tests/` | Tests automatiques (`python -m unittest discover -s tests`), lancés par GitHub à chaque modification |
| `donnees/` | Créé au premier lancement : historique et journal, non versionnés |

---

## Contribuer

Bugs, idées, améliorations : ouvre une [issue](https://github.com/Xeerac/c411-autodl/issues) ou une pull request. **Ne colle jamais ton `.env` ni tes clés** dans une issue : copie seulement le message d'erreur.

⭐ **Si ce projet te sert, laisse une étoile sur GitHub** (bouton *Star* en haut de la page) : c'est gratuit, et ça aide d'autres membres de c411 à le trouver.

## Licence

[MIT](LICENSE) : tu peux utiliser, modifier et redistribuer le code librement, à condition de conserver la mention de licence. Le logiciel est fourni sans aucune garantie.
