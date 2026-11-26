"""Configuration centralisée du système de journalisation (logging).

Les messages de suivi passent par ce module (jamais par `print`) afin d'écrire
vers la console et vers un fichier de log avec des niveaux adaptés.
"""

import logging
import sys
from pathlib import Path

# Niveaux de journalisation autorisés dans config.yaml
VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def setup_logging(level_name: str = "INFO", log_file: Path | None = None) -> logging.Logger:
    """Configure le logger racine ``velo`` pour la console et un fichier optionnel.

    Args:
        level_name: Niveau de log souhaité (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Chemin optionnel vers le fichier de log (créé si besoin).

    Returns:
        L'instance de ``logging.Logger`` configurée pour le package ``velo``.
    """
    # Normalise le nom du niveau en majuscules pour correspondre aux constantes logging
    normalized = level_name.strip().upper()
    numeric_level = getattr(logging, normalized, logging.INFO)

    # Récupère le logger principal du package afin que tous ses sous-modules en héritent
    logger = logging.getLogger("velo")
    logger.setLevel(numeric_level)

    # Évite d'empiler plusieurs handlers si setup_logging est appelé plusieurs fois (ex: tests)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    # Empêche la propagation vers le logger root Python pour éviter les doublons
    logger.propagate = False

    # Format détaillé destiné au fichier de log (horodatage + niveau + module + message)
    file_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Format plus sobre destiné à la console (stderr)
    console_formatter = logging.Formatter(fmt="%(levelname)s: %(message)s")

    # Le handler console reste discret (WARNING+) en usage normal,
    # mais affiche tout dès que l'utilisateur active le niveau DEBUG.
    console_handler = logging.StreamHandler(sys.stderr)
    console_level = numeric_level if numeric_level <= logging.DEBUG else logging.WARNING
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Si un chemin de fichier de log est fourni, on crée le dossier parent puis le handler UTF-8
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger

