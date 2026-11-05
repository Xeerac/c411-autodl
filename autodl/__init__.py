"""c411-autodl : ajoute automatiquement dans qBittorrent les nouveaux torrents c411 selon tes critères.

Organisation du paquet :
  commun         version, journal, chemins, petits utilitaires
  config         lecture de la configuration (.env)
  c411           accès à c411 (Torznab, profil)
  qbit           pilotage de qBittorrent
  notifications  Discord et Telegram
  stockage       historique des ajouts et suivi
  contenu        types de contenu et catégories
  filtres        recherche, tri et filtrage
  moteur         passages, nettoyage, rangement, cross-seed, bilan, freeleech, pannes
  cli            ligne de commande et boucle principale
"""
from .commun import __version__

__all__ = ["__version__"]
