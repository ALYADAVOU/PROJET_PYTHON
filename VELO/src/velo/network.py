"""Couche réseau dédiée aux requêtes HTTP vers les flux JSON distants.

Toute erreur de connexion, de délai dépassé, de statut HTTP ou de JSON invalide
est convertie en ``NetworkError`` afin de garantir un arrêt propre sans traceback.
"""

import logging
from typing import Any

import requests

from velo.models import NetworkError

# Logger spécifique à ce module pour tracer les appels HTTP
logger = logging.getLogger(__name__)

# Délai maximal par défaut (en secondes) avant d'abandonner une requête HTTP
DEFAULT_TIMEOUT_SECONDS = 15.0


def fetch_json(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Télécharge une ressource JSON depuis ``url`` et vérifie sa structure racine.

    Args:
        url: Adresse HTTP(S) du document JSON à télécharger.
        timeout: Temps maximal d'attente pour la réponse en secondes.

    Returns:
        Le dictionnaire JSON décodé.

    Raises:
        NetworkError: Si la requête échoue ou si la réponse n'est pas un objet JSON.
    """
    logger.debug("Téléchargement JSON depuis %s", url)

    try:
        # En-tête User-Agent explicite pour identifier proprement l'outil CLI auprès du serveur
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "velo-cli/0.1 (+https://github.com/ALYADAVOU/PROJET_PYTHON)"},
        )
        # Lève HTTPError pour les codes 4xx et 5xx
        response.raise_for_status()
    except requests.Timeout as exc:
        logger.warning("Délai dépassé lors de la requête vers %s", url)
        raise NetworkError(
            f"Délai d'attente dépassé lors de la connexion à '{url}'."
        ) from exc
    except requests.ConnectionError as exc:
        logger.warning("Erreur de connexion vers %s : %s", url, exc)
        raise NetworkError(
            f"Impossible de joindre '{url}'. Vérifiez votre connexion réseau."
        ) from exc
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "inconnu"
        logger.warning("Erreur HTTP %s sur %s", status_code, url)
        raise NetworkError(
            f"Le serveur a renvoyé une erreur HTTP {status_code} pour '{url}'."
        ) from exc
    except requests.RequestException as exc:
        logger.warning("Erreur réseau inattendue sur %s : %s", url, exc)
        raise NetworkError(f"Erreur réseau lors de l'accès à '{url}' : {exc}") from exc

    # Décodage JSON et vérification que la racine est bien un objet (dict)
    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("Réponse non JSON reçue depuis %s", url)
        raise NetworkError(f"La réponse reçue depuis '{url}' n'est pas un JSON valide.") from exc

    if not isinstance(payload, dict):
        raise NetworkError(
            f"Format JSON inattendu depuis '{url}' : un objet JSON était attendu."
        )

    return payload

