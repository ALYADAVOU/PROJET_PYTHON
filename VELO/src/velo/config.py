"""Lecture, création et vérification du fichier de configuration ``config.yaml``.

Ce module garantit que chaque réglage respecte la priorité :
1. option passée dans la commande (ex: ``--interval 300``) ;
2. valeur écrite dans ``config.yaml`` ;
3. valeur par défaut définie dans ce fichier.
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

# Valeurs par défaut utilisées à la création de config.yaml ou si une clé manque
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

# Nombre maximal de stations favorites autorisé par le cahier des charges
MAX_FAVORITES = 10


def get_config_path() -> Path:
    """Retourne le chemin vers ``config.yaml`` (~/.config/velo/config.yaml par défaut)."""
    # VELO_CONFIG permet de changer ce chemin facilement pendant les tests
    env_path = os.environ.get("VELO_CONFIG")
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".config" / "velo" / "config.yaml"


def get_default_data_folder() -> Path:
    """Retourne le dossier racine où sont stockés les fichiers du réseau."""
    env_dir = os.environ.get("VELO_DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    return Path.home() / ".local" / "share" / "velo"


def slugify_network_name(name: str) -> str:
    """Transforme un nom de réseau (ex: ``V'Lille``) en nom de dossier simple (``vlille``)."""
    # Supprime les accents (é -> e) puis enlève les apostrophes
    sans_accent = "".join(
        c for c in unicodedata.normalize("NFD", name) if unicodedata.category(c) != "Mn"
    )
    propre = sans_accent.replace("'", "").replace("’", "")
    # Garde uniquement lettres minuscules et chiffres séparés par "_"
    slug = re.sub(r"[^a-z0-9]+", "_", propre.lower()).strip("_")
    return slug or "network"


@dataclass(frozen=True)
class NetworkConfig:
    """Nom et URL principale du flux GBFS."""

    name: str
    gbfs_url: str


@dataclass(frozen=True)
class DataConfig:
    """Dossier où l'outil sauvegarde les données et l'historique."""

    folder: Path


@dataclass(frozen=True)
class RefreshConfig:
    """Durée avant d'avertir que les fichiers statiques doivent être actualisés."""

    max_age_days: int


@dataclass(frozen=True)
class CollectConfig:
    """Intervalle d'attente entre deux relevés lors de ``velo collect``."""

    interval_seconds: int


@dataclass(frozen=True)
class AlertsConfig:
    """Seuils utilisés par ``velo alerts`` pour détecter presque vide / presque pleine."""

    low_bikes: int
    low_docks: int


@dataclass(frozen=True)
class DashboardConfig:
    """Fréquence de mise à jour du tableau de bord ``velo dashboard``."""

    refresh_seconds: int


@dataclass(frozen=True)
class LoggingConfig:
    """Niveau de détail des logs (INFO, DEBUG, WARNING...)."""

    level: str


@dataclass(frozen=True)
class VeloConfig:
    """Regroupe toute la configuration validée de l'application."""

    network: NetworkConfig
    data: DataConfig
    refresh: RefreshConfig
    collect: CollectConfig
    alerts: AlertsConfig
    dashboard: DashboardConfig
    logging: LoggingConfig

    @property
    def network_slug(self) -> str:
        """Nom du sous-dossier du réseau (ex: ``vlille``)."""
        return slugify_network_name(self.network.name)

    @property
    def network_dir(self) -> Path:
        """Dossier du réseau contenant les JSON statiques et l'historique."""
        return self.data.folder / self.network_slug

    @property
    def history_dir(self) -> Path:
        """Sous-dossier contenant les fichiers CSV journaliers."""
        return self.network_dir / "history"

    @property
    def favorites_path(self) -> Path:
        """Fichier JSON où sont mémorisés les identifiants favoris."""
        return self.network_dir / "favorites.json"

    @property
    def log_file(self) -> Path:
        """Chemin du fichier journal principal ``velo.log``."""
        return self.data.folder / "velo.log"


def build_default_config(data_folder: Path | None = None) -> VeloConfig:
    """Crée une configuration prête à l'emploi avec toutes les valeurs par défaut."""
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
    """Enregistre ``config`` dans ``path`` au format YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    contenu = {
        "network": {"name": config.network.name, "gbfs_url": config.network.gbfs_url},
        "data": {"folder": str(config.data.folder)},
        "refresh": {"max_age_days": config.refresh.max_age_days},
        "collect": {"interval_seconds": config.collect.interval_seconds},
        "alerts": {"low_bikes": config.alerts.low_bikes, "low_docks": config.alerts.low_docks},
        "dashboard": {"refresh_seconds": config.dashboard.refresh_seconds},
        "logging": {"level": config.logging.level},
    }
    with path.open("w", encoding="utf-8") as fichier:
        yaml.safe_dump(contenu, fichier, allow_unicode=True, sort_keys=False)


def _get_section(data: dict[str, Any], name: str) -> dict[str, Any]:
    """Récupère une section YAML (ou un dict vide si elle est absente)."""
    section = data.get(name)
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ConfigError(f"Configuration invalide : la section '{name}' doit être un objet YAML.")
    return section


def _check_text(value: Any, setting_name: str) -> str:
    """Vérifie qu'un réglage est un texte non vide."""
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Configuration invalide pour '{setting_name}' : texte non vide attendu.")
    return value.strip()


def _check_int(value: Any, setting_name: str, minimum: int) -> int:
    """Vérifie qu'un réglage est un entier >= ``minimum`` (sans accepter True/False)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"Configuration invalide pour '{setting_name}' : entier attendu.")
    if value < minimum:
        raise ConfigError(
            f"Configuration invalide pour '{setting_name}' : "
            f"la valeur ({value}) doit être >= {minimum}."
        )
    return value


def load_config(path: Path | None = None) -> VeloConfig:
    """Lit ``config.yaml`` et vérifie que chaque valeur est valide."""
    config_path = path if path is not None else get_config_path()
    if not config_path.exists():
        raise ConfigError(
            f"Fichier de configuration introuvable ({config_path}). Lancez d'abord 'velo init'."
        )

    try:
        with config_path.open("r", encoding="utf-8") as fichier:
            raw = yaml.safe_load(fichier) or {}
    except (yaml.YAMLError, OSError) as exc:
        raise ConfigError(f"Impossible de lire '{config_path}' : {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Configuration invalide dans '{config_path}' : format YAML attendu.")

    # Récupère chaque bloc du fichier YAML
    net = _get_section(raw, "network")
    data = _get_section(raw, "data")
    refresh = _get_section(raw, "refresh")
    collect = _get_section(raw, "collect")
    alerts = _get_section(raw, "alerts")
    dashboard = _get_section(raw, "dashboard")
    log = _get_section(raw, "logging")

    # Vérifie chaque réglage en nommant précisément la clé si une erreur survient
    net_name = _check_text(net.get("name", DEFAULT_NETWORK_NAME), "network.name")
    gbfs_url = _check_text(net.get("gbfs_url", DEFAULT_GBFS_URL), "network.gbfs_url")
    parsed_url = urlparse(gbfs_url)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        raise ConfigError("Configuration invalide pour 'network.gbfs_url' : URL HTTP(S) attendue.")

    folder_text = _check_text(data.get("folder", str(get_default_data_folder())), "data.folder")
    max_age_days = _check_int(
        refresh.get("max_age_days", DEFAULT_MAX_AGE_DAYS), "refresh.max_age_days", 1
    )
    interval_seconds = _check_int(
        collect.get("interval_seconds", DEFAULT_INTERVAL_SECONDS),
        "collect.interval_seconds",
        MIN_INTERVAL_SECONDS,
    )
    low_bikes = _check_int(alerts.get("low_bikes", DEFAULT_LOW_BIKES), "alerts.low_bikes", 0)
    low_docks = _check_int(alerts.get("low_docks", DEFAULT_LOW_DOCKS), "alerts.low_docks", 0)
    refresh_seconds = _check_int(
        dashboard.get("refresh_seconds", DEFAULT_DASHBOARD_REFRESH_SECONDS),
        "dashboard.refresh_seconds",
        MIN_DASHBOARD_REFRESH_SECONDS,
    )

    log_level = _check_text(log.get("level", DEFAULT_LOGGING_LEVEL), "logging.level").upper()
    if log_level not in VALID_LOG_LEVELS:
        raise ConfigError(
            f"Configuration invalide pour 'logging.level' : '{log_level}'. "
            f"Valeurs possibles : {', '.join(VALID_LOG_LEVELS)}."
        )

    return VeloConfig(
        network=NetworkConfig(name=net_name, gbfs_url=gbfs_url),
        data=DataConfig(folder=Path(folder_text).expanduser()),
        refresh=RefreshConfig(max_age_days=max_age_days),
        collect=CollectConfig(interval_seconds=interval_seconds),
        alerts=AlertsConfig(low_bikes=low_bikes, low_docks=low_docks),
        dashboard=DashboardConfig(refresh_seconds=refresh_seconds),
        logging=LoggingConfig(level=log_level),
    )


def resolve_option(cli_value: Any, config_value: Any, default_value: Any) -> Any:
    """Choisit la valeur selon l'ordre : option CLI -> config.yaml -> défaut."""
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return config_value
    return default_value
