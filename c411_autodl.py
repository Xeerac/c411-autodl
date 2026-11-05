#!/usr/bin/env python3
"""
c411-autodl - Surveille des catégories c411 (API Torznab) et ajoute automatiquement
dans qBittorrent les torrents qui respectent tes critères, tant que ton ratio le permet.

Ce fichier n'est qu'un lanceur : le programme se trouve dans le dossier autodl/.
Configuration dans le fichier .env, à côté de ce fichier.

Usage :
    python c411_autodl.py                # un passage
    python c411_autodl.py --dry-run      # montre ce qui serait ajouté, n'ajoute rien
    python c411_autodl.py --boucle       # en continu, un passage toutes les 5 min
    python c411_autodl.py --help         # toutes les options

Voir README.md pour le tutoriel complet.
"""
import sys
from pathlib import Path

# Le paquet autodl/ est à côté de ce fichier (nécessaire aussi avec « python -I »)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from autodl.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
