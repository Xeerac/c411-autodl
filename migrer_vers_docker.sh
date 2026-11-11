#!/usr/bin/env bash
# Bascule c411-autodl du service systemd (installer_service.sh) vers Docker, en une commande.
#
# Usage, depuis le dossier du programme :
#   sudo bash migrer_vers_docker.sh            bascule vers Docker
#   sudo bash migrer_vers_docker.sh --retour   revient au service systemd
#
# Sécurités :
#   - ton .env et ton dossier donnees/ sont repris tels quels, rien n'est modifié ;
#   - le conteneur utilise le réseau de la machine : les adresses en localhost (qBittorrent, cross-seed)
#     continuent de fonctionner ;
#   - un essai à blanc est lancé DANS le conteneur avant de toucher au service : s'il échoue, rien ne change ;
#   - si le conteneur ne démarre pas correctement, le service systemd est relancé automatiquement.

set -euo pipefail

SERVICE="${SERVICE:-c411-autodl}"       # nom du service systemd
CONTAINER="${CONTAINER:-c411-autodl}"   # nom du conteneur
DIR="$(dirname "$(readlink -f "$0")")"
OVERRIDE="$DIR/docker-compose.override.yml"
cd "$DIR"

ok()   { echo "  ✅ $*"; }
info() { echo "  • $*"; }
fail() { echo "  ❌ $*" >&2; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
    echo "À lancer avec sudo : sudo bash $0 $*"
    exit 1
fi

compose() { docker compose --project-directory "$DIR" "$@"; }

# --------------------------------------------------------------------- retour vers systemd
if [ "${1:-}" = "--retour" ]; then
    echo "Retour au service systemd…"
    [ -f "/etc/systemd/system/$SERVICE.service" ] || fail "Service $SERVICE introuvable : lance d'abord sudo bash installer_service.sh"
    compose down 2>/dev/null || true
    ok "conteneur arrêté"
    systemctl enable --now "$SERVICE" >/dev/null 2>&1
    sleep 3
    systemctl is-active --quiet "$SERVICE" && ok "service $SERVICE relancé" || fail "le service ne démarre pas : journalctl -u $SERVICE"
    exit 0
fi

echo "Bascule de c411-autodl vers Docker"
echo

# --------------------------------------------------------------------- 1. vérifications
echo "1/5 Vérifications"
command -v docker >/dev/null 2>&1 || fail "Docker n'est pas installé. Installe-le avec : curl -fsSL https://get.docker.com | sh"
docker compose version >/dev/null 2>&1 || fail "« docker compose » est absent. Installe le plugin : apt install docker-compose-plugin"
[ -f "$DIR/c411_autodl.py" ] || fail "c411_autodl.py introuvable dans $DIR"
[ -f "$DIR/Dockerfile" ] && [ -f "$DIR/docker-compose.yml" ] || fail "Dockerfile ou docker-compose.yml absent : mets à jour le projet (git pull)"
[ -f "$DIR/.env" ] || fail ".env introuvable dans $DIR"
ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null) et docker compose disponibles"

UNIT="/etc/systemd/system/$SERVICE.service"
HAS_SERVICE=false
if [ -f "$UNIT" ]; then
    HAS_SERVICE=true
    ok "service systemd $SERVICE trouvé ($(systemctl is-active "$SERVICE" 2>/dev/null || true))"
else
    info "pas de service systemd $SERVICE : simple installation Docker"
fi
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    fail "un conteneur « $CONTAINER » existe déjà : c411-autodl tourne peut-être déjà dans Docker (docker ps)"
fi

# --------------------------------------------------------------------- 2. reprise des réglages du service
echo "2/5 Reprise des réglages"
OWNER="$(stat -c %u "$DIR/.env"):$(stat -c %g "$DIR/.env")"
INTERVAL=300
if $HAS_SERVICE; then
    svc_user="$(sed -n 's/^User=//p' "$UNIT" | head -1)"
    if [ -n "$svc_user" ] && id "$svc_user" >/dev/null 2>&1; then
        OWNER="$(id -u "$svc_user"):$(id -g "$svc_user")"
    fi
    found="$(grep -o -- '--boucle [0-9]*' "$UNIT" | head -1 | awk '{print $2}' || true)"
    [ -n "$found" ] && INTERVAL="$found"
fi
mkdir -p "$DIR/donnees"
chown -R "$OWNER" "$DIR/donnees"   # le conteneur doit pouvoir écrire son historique et son journal
ok "utilisateur du conteneur : $OWNER (le même que le service)"
ok "intervalle : $INTERVAL s"

cat > "$OVERRIDE" <<EOF
# Créé par migrer_vers_docker.sh : réglages propres à cette machine (non versionné).
services:
  c411-autodl:
    # Image construite depuis ce dossier (dépôt cloné) : « git pull && docker compose up -d --build » met à jour
    build: .
    image: c411-autodl:local
    container_name: $CONTAINER
    user: "$OWNER"
    # Réseau de la machine : les adresses en localhost du .env (qBittorrent, cross-seed) restent valables
    network_mode: host
    # Incompatible avec le réseau de la machine : on annule la publication de ports du fichier principal
    ports: !reset []
    # Même fonctionnement que le service systemd. Pour l'interface web : ["--interface", "--port", "8411"]
    command: ["--boucle", "$INTERVAL"]
EOF
compose config --quiet || fail "docker-compose.yml invalide"
ok "réglages écrits dans docker-compose.override.yml"

# --------------------------------------------------------------------- 3. image et essai à blanc
echo "3/5 Construction de l'image et essai à blanc dans le conteneur (le service tourne toujours)"
compose build -q c411-autodl >/dev/null || fail "la construction de l'image a échoué"
ok "image construite : $(compose run --rm --no-deps c411-autodl --version 2>/dev/null)"
if ! compose run --rm --no-deps c411-autodl --dry-run > /tmp/c411-essai.log 2>&1; then
    tail -15 /tmp/c411-essai.log >&2
    rm -f "$OVERRIDE"
    fail "l'essai à blanc a échoué dans le conteneur : rien n'a été changé, le service continue de tourner"
fi
ok "essai à blanc réussi : $(grep -o 'Terminé.*' /tmp/c411-essai.log | tail -1)"
rm -f /tmp/c411-essai.log

# --------------------------------------------------------------------- 4. bascule
echo "4/5 Bascule"
if $HAS_SERVICE; then
    systemctl disable --now "$SERVICE" >/dev/null 2>&1
    ok "service systemd arrêté et désactivé (gardé pour un éventuel retour)"
fi
compose up -d c411-autodl >/dev/null 2>&1
info "démarrage du conteneur…"
sleep 20

# --------------------------------------------------------------------- 5. vérification (et retour automatique si besoin)
echo "5/5 Vérification"
running="$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || echo false)"
restarts="$(docker inspect -f '{{.RestartCount}}' "$CONTAINER" 2>/dev/null || echo 0)"
if [ "$running" != "true" ] || [ "$restarts" -gt 0 ]; then
    echo "  ❌ le conteneur ne tourne pas correctement :" >&2
    compose logs --tail 15 c411-autodl >&2 || true
    compose down >/dev/null 2>&1 || true
    if $HAS_SERVICE; then
        systemctl enable --now "$SERVICE" >/dev/null 2>&1
        echo "  ↩️  retour automatique au service systemd : tout est comme avant." >&2
    fi
    exit 1
fi
ok "conteneur $CONTAINER en marche"
compose logs --no-log-prefix c411-autodl 2>&1 | grep -E "INFO|ERROR" | tail -3 | sed 's/^/     /'

cat <<EOF

C'est fait : c411-autodl tourne dans Docker, avec la même configuration et le même historique.

Commandes utiles (depuis $DIR) :
  docker compose logs -f c411-autodl                 journal en direct
  docker compose run --rm c411-autodl --bilan        commande ponctuelle
  git pull && docker compose up -d --build           mise à jour
  sudo bash migrer_vers_docker.sh --retour           revenir au service systemd
EOF
