#!/usr/bin/env bash
# Installe c411-autodl comme service systemd (Debian 13) : démarrage automatique avec le VPS,
# redémarrage automatique en cas de plantage.
#
# Usage (depuis le dossier du programme) :
#   sudo bash installer_service.sh             installe et démarre le service
#   sudo bash installer_service.sh desinstaller

set -euo pipefail

SERVICE=c411-autodl
UNIT="/etc/systemd/system/${SERVICE}.service"
DIR="$(dirname "$(readlink -f "$0")")"
INTERVALLE="${INTERVALLE:-60}"

if [ "$(id -u)" -ne 0 ]; then
    echo "À lancer avec sudo : sudo bash $0 $*"
    exit 1
fi

if [ "${1:-}" = "desinstaller" ]; then
    systemctl disable --now "$SERVICE" 2>/dev/null || true
    rm -f "$UNIT"
    systemctl daemon-reload
    echo "Service $SERVICE supprimé (les fichiers dans $DIR sont conservés)."
    exit 0
fi

# Le service tourne avec l'utilisateur propriétaire du dossier, pas en root
UTILISATEUR="${SUDO_USER:-$(stat -c %U "$DIR")}"
[ "$UTILISATEUR" = "root" ] && echo "Attention : le service tournera en root (déconseillé)."

if ! command -v python3 >/dev/null 2>&1; then
    echo "Installation de python3..."
    apt-get update -qq && apt-get install -y -qq python3
fi
PYTHON="$(command -v python3)"

[ -f "$DIR/c411_autodl.py" ] || { echo "c411_autodl.py introuvable dans $DIR"; exit 1; }
[ -f "$DIR/.env" ] || { echo "Fichier .env introuvable dans $DIR : copie .env.example en .env et remplis-le."; exit 1; }

# Le .env contient tes clés : lisible uniquement par toi
chown "$UTILISATEUR" "$DIR/.env"
chmod 600 "$DIR/.env"
# Dossier des données (historique des ajouts, journal) : doit appartenir à l'utilisateur du service
mkdir -p "$DIR/donnees"
chown -R "$UTILISATEUR" "$DIR/donnees"
# Fichiers copiés depuis Windows : on retire les fins de ligne CRLF éventuelles
sed -i 's/\r$//' "$DIR/.env" "$DIR"/*.sh

cat > "$UNIT" <<EOF
[Unit]
Description=c411-autodl (téléchargement automatique c411 vers qBittorrent)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$UTILISATEUR
WorkingDirectory=$DIR
ExecStart=$PYTHON $DIR/c411_autodl.py --boucle $INTERVALLE
Restart=always
RestartSec=30
Environment=PYTHONUNBUFFERED=1
# Durcissement : le programme n'a besoin d'écrire que dans son dossier
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$DIR
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$SERVICE"
sleep 3
systemctl --no-pager --lines=5 status "$SERVICE" || true

cat <<EOF

Service installé et démarré (utilisateur : $UTILISATEUR, un passage toutes les $INTERVALLE s).

Commandes utiles :
  journalctl -u $SERVICE -f          suivre le journal en direct
  sudo systemctl restart $SERVICE    relancer (après une modification du .env)
  sudo systemctl stop $SERVICE       arrêter
  sudo systemctl start $SERVICE      démarrer
  sudo bash $0 desinstaller          supprimer le service
EOF
