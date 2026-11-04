#!/usr/bin/env bash
# Lance c411-autodl en continu (un passage toutes les 60 s) sous Linux.
# Si le programme s'arrête (plantage, coupure réseau...), il est relancé 30 s plus tard.
# Ctrl+C pour arrêter.
#
# Usage :  bash lancer_h24.sh            (intervalle de 60 s)
#          bash lancer_h24.sh 120        (intervalle de 120 s)

cd "$(dirname "$(readlink -f "$0")")" || exit 1
INTERVALLE="${1:-60}"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 est introuvable. Installe-le avec : sudo apt install python3"
    exit 1
fi
if [ ! -f .env ]; then
    echo "Fichier .env introuvable dans $(pwd). Copie .env.example en .env et remplis-le."
    exit 1
fi

trap 'echo; echo "Arrêt demandé."; exit 0' INT TERM

while true; do
    python3 c411_autodl.py --boucle "$INTERVALLE"
    code=$?
    # Code 0 = arrêt volontaire (Ctrl+C) ; on ne relance pas
    [ "$code" -eq 0 ] && exit 0
    echo "Programme arrêté (code $code), relance dans 30 s (Ctrl+C pour arrêter)..."
    sleep 30
done
