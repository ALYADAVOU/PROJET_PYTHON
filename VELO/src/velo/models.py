"""Modèles de données métier et exceptions personnalisées de l'outil Vélo.

Ce module définit les objets internes manipulés par toute l'application
(stations, états temps réel, relevés historiques, périodes, etc.),
indépendamment du format brut de l'API GBFS.
"""

from dataclasses import dataclass
from datetime import datetime


class VeloError(Exception):
    """Exception de base pour toutes les erreurs attendues de l'outil Vélo.

    Elle permet à l'interface CLI d'afficher un message clair à l'utilisateur
    et de quitter avec un code de sortie non nul sans afficher de traceback.
    """


class ConfigError(VeloError):
    """Erreur levée lorsque le fichier config.yaml est absent, illisible ou invalide."""


class NetworkError(VeloError):
    """Erreur levée lors d'un problème réseau ou HTTP pendant la récupération de données."""


class GBFSError(VeloError):
    """Erreur levée lorsque les données reçues d'un flux GBFS sont invalides ou incomplètes."""


class DataError(VeloError):
    """Erreur levée lors d'un problème sur les données locales (CSV, favoris, station inconnue)."""


@dataclass(frozen=True)
class SystemInfo:
    """Informations générales sur le réseau de vélos (issu de system_information)."""

    system_id: str
    name: str
    language: str | None = None
    timezone: str | None = None
    url: str | None = None
    last_updated: datetime | None = None


@dataclass(frozen=True)
class VehicleType:
    """Description d'un type de vélo disponible sur le réseau (issu de vehicle_types)."""

    vehicle_type_id: str
    form_factor: str
    propulsion_type: str
    name: str | None = None


@dataclass(frozen=True)
class StationInfo:
    """Métadonnées statiques d'une station (issu de station_information)."""

    station_id: str
    name: str
    lat: float
    lon: float
    capacity: int | None = None
    address: str | None = None


@dataclass(frozen=True)
class StationStatus:
    """État instantané d'une station à un moment donné (issu de station_status)."""

    station_id: str
    bikes_available: int
    docks_available: int
    is_installed: bool
    is_renting: bool
    is_returning: bool
    last_reported: datetime | None = None


@dataclass(frozen=True)
class NetworkSnapshot:
    """Relevé complet de toutes les stations du réseau à un instant donné."""

    network_name: str
    last_updated: datetime
    statuses: list[StationStatus]


@dataclass(frozen=True)
class StationSnapshot:
    """Ligne d'historique d'une station enregistrée dans un fichier CSV quotidien."""

    timestamp: datetime
    station_id: str
    bikes: int
    docks: int
    is_installed: bool
    is_renting: bool
    is_returning: bool
    last_reported: datetime | None = None


@dataclass(frozen=True)
class CollectionPeriod:
    """Période continue de collecte (suite de relevés sans interruption majeure)."""

    index: int
    start: datetime
    end: datetime
    duration_seconds: int
    snapshot_count: int
    timestamps: list[datetime]

