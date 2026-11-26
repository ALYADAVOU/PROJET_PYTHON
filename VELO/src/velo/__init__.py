"""Package principal de l'outil en ligne de commande Vélo."""

from velo.cli import main

# Expose la fonction main à la racine du package pour compatibilité
__all__ = ["main"]
