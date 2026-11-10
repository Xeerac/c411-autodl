#!/usr/bin/env bash
# Installe l'assistant « domaine » de c411-autodl sur la machine hôte (une seule fois, en root).
#
#   sudo bash serveur/installer_domaine.sh            installe (ou met à jour) l'assistant
#   sudo bash serveur/installer_domaine.sh --retirer  le désinstalle et retire le domaine de Caddy
#
# Prérequis : Caddy installé sur la machine (https://caddyserver.com/docs/install), ports 80 et 443 libres
# pour lui. Le script ajoute une seule ligne à /etc/caddy/Caddyfile (import /etc/caddy/c411-autodl.caddy),
# après en avoir fait une copie, et vérifie que la configuration reste valide.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "À lancer en root : sudo bash $0" >&2; exit 1; }
DIR="$(cd "$(dirname "$0")/.." && pwd)"
DONNEES="$DIR/donnees"
CADDYFILE=/etc/caddy/Caddyfile
SNIPPET=/etc/caddy/c411-autodl.caddy
UNIT=c411-autodl-domaine
AMONT="${AMONT:-127.0.0.1:8411}"

if [ "${1:-}" = "--retirer" ]; then
  systemctl disable --now "$UNIT.path" "$UNIT.timer" 2>/dev/null || true
  rm -f "/etc/systemd/system/$UNIT".{service,path,timer}
  systemctl daemon-reload
  if [ -f "$SNIPPET" ]; then
    echo "# c411-autodl : accès par domaine retiré." > "$SNIPPET"
    caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null && systemctl reload caddy
  fi
  echo "Assistant retiré. La ligne « import $SNIPPET » reste dans $CADDYFILE (sans effet) : supprime-la si tu veux."
  exit 0
fi

command -v caddy >/dev/null || { echo "Caddy n'est pas installé. Voir https://caddyserver.com/docs/install" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 est nécessaire (apt install python3)." >&2; exit 1; }
[ -f "$CADDYFILE" ] || { echo "$CADDYFILE introuvable." >&2; exit 1; }

# Dossier d'échange, au nom de l'utilisateur du conteneur (1000 par défaut)
OWNER="$(stat -c %u:%g "$DONNEES" 2>/dev/null || echo 1000:1000)"
mkdir -p "$DONNEES/domaine"
chown "$OWNER" "$DONNEES/domaine"
chmod 755 "$DONNEES/domaine"

# Fichier Caddy du domaine (vide au départ) et import dans le Caddyfile
[ -f "$SNIPPET" ] || echo "# Généré par c411-autodl (assistant domaine) : accès par domaine désactivé." > "$SNIPPET"
chmod 644 "$SNIPPET"
if ! grep -q "import $SNIPPET" "$CADDYFILE"; then
  cp -a "$CADDYFILE" "$CADDYFILE.avant-c411-autodl.$(date +%Y%m%d-%H%M%S)"
  printf '\n# Accès à l'"'"'interface c411-autodl par un nom de domaine (géré par l'"'"'assistant)\nimport %s\n' "$SNIPPET" >> "$CADDYFILE"
  if ! caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null 2>&1; then
    cp -a "$(ls -t "$CADDYFILE".avant-c411-autodl.* | head -1)" "$CADDYFILE"
    echo "Caddy refuse la configuration modifiée : Caddyfile remis comme avant." >&2
    exit 1
  fi
  systemctl reload caddy
  echo "Import ajouté à $CADDYFILE (copie de l'original à côté)."
fi

cat > "/etc/systemd/system/$UNIT.service" <<EOF
[Unit]
Description=c411-autodl : assistant d'accès par nom de domaine (Caddy)
After=caddy.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 $DIR/serveur/assistant_domaine.py --donnees $DONNEES --amont $AMONT
EOF

cat > "/etc/systemd/system/$UNIT.path" <<EOF
[Unit]
Description=c411-autodl : surveille les demandes de l'interface (domaine)

[Path]
PathChanged=$DONNEES/domaine/demande.json
Unit=$UNIT.service

[Install]
WantedBy=multi-user.target
EOF

cat > "/etc/systemd/system/$UNIT.timer" <<EOF
[Unit]
Description=c411-autodl : vérifie le domaine et le certificat toutes les 5 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
Unit=$UNIT.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now "$UNIT.path" "$UNIT.timer" >/dev/null
systemctl start "$UNIT.service"
echo "Assistant installé. Active l'accès par domaine dans l'interface : Configuration > Accès par domaine."
