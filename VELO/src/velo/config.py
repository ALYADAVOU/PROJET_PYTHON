"""Gestion et validation de la configuration YAML de l'outil Vélo.

Ce module applique la règle de priorité du cahier des charges :
1. option passée en ligne de commande ;
2. valeur lue dans ``config.yaml`` ;
3. valeur par défaut définie dans le code.
"""

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from velo.logging_config import VALID_LOG_LEVELS
from velo.models import ConfigError

# Valeurs par défaut inscrites dans le code (niveau 3 de priorité)
DEFAULT_NETWORK_NAME = "V'Lille"
DEFAULT_GBFS_URL = "https://media.ilevia.fr/opendata/gbfs.json"
DEFAULT_MAX_AGE_DAYS = 7
DEFAULT_INTERVAL_SECONDS = 120
MIN_INTERVAL_SECONDS = 60
DEFAULT_LOW_BIKES = 2
DEFAULT_LOW_DOCKS = 2
DEFAULT_DASHBOARD_REFRESH_SECONDS = 60
MIN_DASHBOARD_REFRESH_SECONDS = 60
DEFAULT_LOGGING_LEVEL = "INFO"

# Limite imposée par le cahier des charges pour la liste des stations favorites
MAX_FAVORITES = 10


def get_config_path() -> Path:
    """Retourne le chemin vers le fichier ``config.yaml`` de l'utilisateur."""
    # La variable d'environnement VELO_CONFIG permet de surcharger l'emplacement (tests)
    env_path = os.environ.get("VELO_CONFIG")
    if env_path:
        return Path(env_path).expanduser()
    # Emplacement standard multiplateforme (~/.config/velo/config.yaml)
    return Path.home() / ".config" / "velo" / "config.yaml"


def get_default_data_folder() -> Path:
    """Retourne le dossier de données par défaut de l'utilisateur."""
    # Permet également une surcharge par variable d'environnement
    env_dir = os.environ.get("VELO_DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    # Emplacement standard (~/.local/share/velo) conforme au cahier des charges
    return Path.home() / ".local" / "share" / "velo"


def slugify_network_name(name: str) -> str:
    """Convertit un nom de réseau (ex: ``V'Lille``) en nom de dossier sûr (``vlille``)."""
    # Décompose les caractères accentués puis supprime les accents
    normalized = unicodedata.normalize("NFD", name)
    without_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    # Supprime les apostrophes pour que "V'Lille" devienne bien "vlille" et non "v_lille"
    without_apostrophes = without_accents.replace("'", "").replace("’", "")
    # Remplace toute séquence non alphanumérique par un tiret bas puis nettoie les bords
    slug = re.sub(r"[^a-z0-9]+", "_", without_apostrophes.lower()).strip("_")
    return slug or "network"


@dataclass(frozen=True)
class NetworkConfig:
    """Configuration du réseau GBFS cible."""

    name: str
    gbfs_url: str


@dataclass(frozen=True)
class DataConfig:
    """Configuration du dossier racine de stockage des données."""

    folder: Path


@dataclass(frozen=True)
class RefreshConfig:
    """Configuration de l'ancienneté maximale des données statiques."""

    max_age_days: int


@dataclass(frozen=True)
class CollectConfig:
    """Configuration de la fréquence de collecte historique."""

    interval_seconds: int


@dataclass(frozen=True)
class AlertsConfig:
    """Seuils de déclenchement des alertes sur les stations."""

    low_bikes: int
    low_docks: int


@dataclass(frozen=True)
class DashboardConfig:
    """Configuration du rafraîchissement du tableau de bord temps réel."""

    refresh_seconds: int


@dataclass(frozen=True)
class LoggingConfig:
    """Configuration du niveau de journalisation."""

    level: str


@dataclass(frozen=True)
class VeloConfig:
    """Configuration complète et validée de l'application Vélo."""

    network: NetworkConfig
    data: DataConfig
    refresh: RefreshConfig
    collect: CollectConfig
    alerts: AlertsConfig
    dashboard: DashboardConfig
    logging: LoggingConfig

    @property
    def network_slug(self) -> str:
        """Nom normalisé du dossier propre au réseau configuré."""
        return slugify_network_name(self.network.name)

    @property
    def network_dir(self) -> Path:
        """Dossier contenant les fichiers JSON et l'historique du réseau."""
        return self.data.folder / self.network_slug

    @property
    def history_dir(self) -> Path:
        """Sous-dossier contenant les fichiers CSV quotidiens d'historique."""
        return self.network_dir / "history"

    @property
    def favorites_path(self) -> Path:
        """Fichier JSON géré par l'outil pour mémoriser les stations favorites."""
        return self.network_dir / "favorites.json"

    @property
    def log_file(self) -> Path:
        """Chemin du fichier de log principal dans le dossier de données."""
        return self.data.folder / "velo.log"


def build_default_config(data_folder: Path | None = None) -> VeloConfig:
    """Construit une configuration complète avec toutes les valeurs par défaut."""
    folder = data_folder if data_folder is not None else get_default_data_folder()
    return VeloConfig(
        network=NetworkConfig(name=DEFAULT_NETWORK_NAME, gbfs_url=DEFAULT_GBFS_URL),
        data=DataConfig(folder=folder),
        refresh=RefreshConfig(max_age_days=DEFAULT_MAX_AGE_DAYS),
        collect=CollectConfig(interval_seconds=DEFAULT_INTERVAL_SECONDS),
        alerts=AlertsConfig(low_bikes=DEFAULT_LOW_BIKES, low_docks=DEFAULT_LOW_DOCKS),
        dashboard=DashboardConfig(refresh_seconds=DEFAULT_DASHBOARD_REFRESH_SECONDS),
        logging=LoggingConfig(level=DEFAULT_LOGGING_LEVEL),
    )


def save_config(config: VeloConfig, path: Path) -> None:
    """Écrit la configuration au format YAML en UTF-8 dans ``path``."""
    # Crée le dossier parent (ex: ~/.config/velo) si nécessaire
    path.parent.mkdir(parents=True, exist_ok=True)

    # Structure sérialisable correspondant exactement à l'exemple du cahier des charges
    payload: dict[str, Any] = {
        "network": {
            "name": config.network.name,
            "gbfs_url": config.network.gbfs_url,
        },
        "data": {
            "folder": str(config.data.folder),
        },
        "refresh": {
            "max_age_days": config.refresh.max_age_days,
        },
        "collect": {
            "interval_seconds": config.collect.interval_seconds,
        },
        "alerts": {
            "low_bikes": config.alerts.low_bikes,
            "low_docks": config.alerts.low_docks,
        },
        "dashboard": {
            "refresh_seconds": config.dashboard.refresh_seconds,
        },
        "logging": {
            "level": config.logging.level,
        },
    }

    # sort_keys=False préserve l'ordre logique des sections pour faciliter l'édition manuelle
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)


def _require_section(raw: dict[str, Any], key: str) -> dict[str, Any]:
    """Récupère une section YAML sous forme de dictionnaire ou lève ConfigError."""
    if key not in raw or raw[key] is None:
        return {}
    section = raw[key]
    if not isinstance(section, dict):
        raise ConfigError(
            f"Configuration invalide : la section '{key}' doit être un objet YAML."
        )
    return section


def _validate_non_empty_str(value: Any, setting_name: str) -> str:
    """Vérifie qu'un réglage texte est une chaîne non vide."""
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"Configuration invalide pour '{setting_name}' : une chaîne non vide est attendue."
        )
    return value.strip()


def _validate_int(value: Any, setting_name: str, minimum: int) -> int:
    """Vérifie qu'un réglage entier respecte une borne minimale."""
    # En Python, bool hérite de int : on exclut explicitement True/False
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(
            f"Configuration invalide pour '{setting_name}' : un entier est attendu."
        )
    if value < minimum:
        raise ConfigError(
            f"Configuration invalide pour '{setting_name}' : "
            f"la valeur ({value}) doit être au moins égale à {minimum}."
        )
    return value


def _validate_url(value: Any, setting_name: str) -> str:
    """Vérifie qu'un réglage contient une URL HTTP/HTTPS syntaxiquement valide."""
    text = _validate_non_empty_str(value, setting_name)
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ConfigError(
            f"Configuration invalide pour '{setting_name}' : URL HTTP(S) valide attendue."
        )
    return text


def load_config(path: Path | None = None) -> VeloConfig:
    """Charge et valide ``config.yaml`` depuis ``path`` (ou le chemin par défaut).

    Args:
        path: Chemin explicite vers le fichier YAML, ou None pour le chemin standard.

    Returns:
        Un objet ``VeloConfig`` entièrement validé.

    Raises:
        ConfigError: Si le fichier est absent, malformé ou contient un réglage invalide.
    """
    config_path = path if path is not None else get_config_path()

    if not config_path.exists():
        raise ConfigError(
            f"Fichier de configuration introuvable ({config_path}). "
            "Lancez d'abord la commande 'velo init'."
        )

    # Lecture UTF-8 du fichier YAML et capture de toute erreur de syntaxe YAML
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ConfigError(
            f"Erreur de syntaxe YAML dans '{config_path}' : {exc}"
        ) from exc
    except OSError as exc:
        raise ConfigError(
            f"Impossible de lire le fichier de configuration '{config_path}' : {exc}"
        ) from exc

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(
            f"Configuration invalide dans '{config_path}' : "
            "un mapping YAML est attendu à la racine."
        )

    # Extraction de chaque section (si une clé manque, la valeur par défaut du code s'applique)
    net_sec = _require_section(raw, "network")
    data_sec = _require_section(raw, "data")
    refresh_sec = _require_section(raw, "refresh")
    collect_sec = _require_section(raw, "collect")
    alerts_sec = _require_section(raw, "alerts")
    dashboard_sec = _require_section(raw, "dashboard")
    logging_sec = _require_section(raw, "logging")

    # Validation réglage par réglage en nommant toujours la clé exacte en cas d'erreur
    net_name = _validate_non_empty_str(
        net_sec.get("name", DEFAULT_NETWORK_NAME),
        "network.name",
    )
    gbfs_url = _validate_url(
        net_sec.get("gbfs_url", DEFAULT_GBFS_URL),
        "network.gbfs_url",
    )

    raw_folder = data_sec.get("folder", str(get_default_data_folder()))
    folder_str = _validate_non_empty_str(raw_folder, "data.folder")
    data_folder = Path(folder_str).expanduser()

    max_age_days = _validate_int(
        refresh_sec.get("max_age_days", DEFAULT_MAX_AGE_DAYS),
        "refresh.max_age_days",
        minimum=1,
    )
    interval_seconds = _validate_int(
        collect_sec.get("interval_seconds", DEFAULT_INTERVAL_SECONDS),
        "collect.interval_seconds",
        minimum=MIN_INTERVAL_SECONDS,
    )
    low_bikes = _validate_int(
        alerts_sec.get("low_bikes", DEFAULT_LOW_BIKES),
        "alerts.low_bikes",
        minimum=0,
    )
    low_docks = _validate_int(
        alerts_sec.get("low_docks", DEFAULT_LOW_DOCKS),
        "alerts.low_docks",
        minimum=0,
    )
    refresh_seconds = _validate_int(
        dashboard_sec.get("refresh_seconds", DEFAULT_DASHBOARD_REFRESH_SECONDS),
        "dashboard.refresh_seconds",
        minimum=MIN_DASHBOARD_REFRESH_SECONDS,
    )

    log_level_raw = _validate_non_empty_str(
        logging_sec.get("level", DEFAULT_LOGGING_LEVEL),
        "logging.level",
    ).upper()
    if log_level_raw not in VALID_LOG_LEVELS:
        allowed = ", ".join(VALID_LOG_LEVELS)
        raise ConfigError(
            f"Configuration invalide pour 'logging.level' : '{log_level_raw}'. "
            f"Valeurs acceptées : {allowed}."
        )

    return VeloConfig(
        network=NetworkConfig(name=net_name, gbfs_url=gbfs_url),
        data=DataConfig(folder=data_folder),
        refresh=RefreshConfig(max_age_days=max_age_days),
        collect=CollectConfig(interval_seconds=interval_seconds),
        alerts=AlertsConfig(low_bikes=low_bikes, low_docks=low_docks),
        dashboard=DashboardConfig(refresh_seconds=refresh_seconds),
        logging=LoggingConfig(level=log_level_raw),
    )


def resolve_option[T](cli_value: T | None, config_value: T, default_value: T) -> T:
    """Applique la hiérarchie : option CLI > valeur de config.yaml > défaut du code."""
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return config_value
    return default_value
