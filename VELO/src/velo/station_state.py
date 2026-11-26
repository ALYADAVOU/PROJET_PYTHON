"""Calcul des états de stations, statistiques réseau, alertes et recherche par regex.

Ce module regroupe toute la logique métier liée aux stations afin qu'elle soit
partagée à l'identique entre ``status``, ``favorites``, ``alerts`` et ``dashboard``.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from velo.config import VeloConfig
from velo.gbfs import get_static_files_age_days
from velo.models import DataError, NetworkSnapshot, StationInfo, StationStatus


@dataclass(frozen=True)
class NetworkStats:
    """Statistiques agrégées sur l'état instantané du réseau."""

    network_name: str
    last_updated_str: str
    total_stations: int
    in_service_count: int
    out_of_service_count: int
    empty_count: int
    full_count: int
    total_bikes: int
    total_docks: int
    fill_rate_pct: int


@dataclass(frozen=True)
class AlertEntry:
    """Élément d'alerte associé à une station."""

    station_id: str
    name: str
    bikes: int
    docks: int


@dataclass(frozen=True)
class AlertsSummary:
    """Alertes classées par catégorie sans doublon avec les stations hors service."""

    network_name: str
    last_updated_str: str
    out_of_service: list[AlertEntry]
    low_bikes_alerts: list[AlertEntry]
    low_docks_alerts: list[AlertEntry]


def is_out_of_service(status: StationStatus) -> bool:
    """Détermine si une station est hors service.

    Règle choisie : une station est hors service dès qu'elle n'est plus installée,
    qu'elle ne permet plus la location (``is_renting``) ou qu'elle n'accepte plus
    les retours (``is_returning``).
    """
    return not (status.is_installed and status.is_renting and status.is_returning)


def classify_station_state(status: StationStatus, low_bikes: int, low_docks: int) -> str:
    """Retourne un libellé court décrivant l'état courant d'une station."""
    if is_out_of_service(status):
        return "hors service"
    if status.bikes_available == 0:
        return "vide"
    if status.bikes_available <= low_bikes:
        return "presque vide"
    if status.docks_available == 0:
        return "pleine"
    if status.docks_available <= low_docks:
        return "presque pleine"
    return "disponible"


def natural_station_sort_key(station_id: str) -> tuple[int, int | str]:
    """Clé de tri naturelle pour classer les identifiants numériques avant les textes."""
    if station_id.isdigit():
        return (0, int(station_id))
    return (1, station_id)


def compute_network_stats(snapshot: NetworkSnapshot) -> NetworkStats:
    """Calcule les statistiques globales du réseau à partir d'un relevé instantané."""
    total_stations = len(snapshot.statuses)
    out_of_service_count = 0
    empty_count = 0
    full_count = 0
    total_bikes = 0
    total_docks = 0

    for st in snapshot.statuses:
        if is_out_of_service(st):
            out_of_service_count += 1
            # Une station hors service n'est pas comptée dans les vides/pleines ni la capacité utile
            continue

        total_bikes += st.bikes_available
        total_docks += st.docks_available

        if st.bikes_available == 0:
            empty_count += 1
        if st.docks_available == 0:
            full_count += 1

    in_service_count = total_stations - out_of_service_count
    capacity_sum = total_bikes + total_docks
    fill_rate_pct = round((total_bikes / capacity_sum) * 100) if capacity_sum > 0 else 0

    return NetworkStats(
        network_name=snapshot.network_name,
        last_updated_str=snapshot.last_updated.strftime("%d/%m/%Y à %H:%M"),
        total_stations=total_stations,
        in_service_count=in_service_count,
        out_of_service_count=out_of_service_count,
        empty_count=empty_count,
        full_count=full_count,
        total_bikes=total_bikes,
        total_docks=total_docks,
        fill_rate_pct=fill_rate_pct,
    )


def compute_alerts(
    snapshot: NetworkSnapshot,
    stations_by_id: dict[str, StationInfo],
    low_bikes: int,
    low_docks: int,
) -> AlertsSummary:
    """Classe les stations en alerte (hors service, vides/presque, pleines/presque)."""
    out_of_service: list[AlertEntry] = []
    low_bikes_alerts: list[AlertEntry] = []
    low_docks_alerts: list[AlertEntry] = []

    for st in snapshot.statuses:
        info = stations_by_id.get(st.station_id)
        station_name = info.name if info is not None else f"Station {st.station_id}"
        entry = AlertEntry(
            station_id=st.station_id,
            name=station_name,
            bikes=st.bikes_available,
            docks=st.docks_available,
        )

        # Priorité absolue à "hors service" : on ne signale pas la station une seconde fois
        if is_out_of_service(st):
            out_of_service.append(entry)
            continue

        if st.bikes_available <= low_bikes:
            low_bikes_alerts.append(entry)
        if st.docks_available <= low_docks:
            low_docks_alerts.append(entry)

    # Tri déterministe pour un affichage lisible et stable
    out_of_service.sort(key=lambda item: natural_station_sort_key(item.station_id))
    low_bikes_alerts.sort(key=lambda item: (item.bikes, natural_station_sort_key(item.station_id)))
    low_docks_alerts.sort(key=lambda item: (item.docks, natural_station_sort_key(item.station_id)))

    return AlertsSummary(
        network_name=snapshot.network_name,
        last_updated_str=snapshot.last_updated.strftime("%d/%m/%Y à %H:%M"),
        out_of_service=out_of_service,
        low_bikes_alerts=low_bikes_alerts,
        low_docks_alerts=low_docks_alerts,
    )


def strip_accents(text: str) -> str:
    """Supprime les accents d'une chaîne pour faciliter les recherches tolérantes."""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def search_stations(stations: Iterable[StationInfo], pattern: str) -> list[StationInfo]:
    """Recherche des stations par expression régulière sur leur nom.

    Choix documentés :
    - recherche partielle (``re.search``) ;
    - insensible à la casse (``re.IGNORECASE``) ;
    - insensible aux accents (normalisation NFD sur le motif et sur le nom).
    """
    if not pattern.strip():
        raise DataError("Le motif de recherche ne peut pas être vide.")

    cleaned_pattern = strip_accents(pattern)
    try:
        regex = re.compile(cleaned_pattern, re.IGNORECASE)
    except re.error as exc:
        raise DataError(f"Expression régulière invalide ({pattern!r}) : {exc}") from exc

    matches = [
        station
        for station in stations
        if regex.search(strip_accents(station.name)) is not None
    ]
    matches.sort(key=lambda st: natural_station_sort_key(st.station_id))
    return matches


def check_static_staleness(config: VeloConfig) -> str | None:
    """Vérifie si les fichiers statiques locaux sont absents ou trop anciens.

    Retourne un message d'avertissement à afficher à l'utilisateur, ou ``None`` si tout est à jour.
    """
    age_days = get_static_files_age_days(config.network_dir)
    if age_days is None:
        return (
            "Les données statiques locales sont incomplètes ou absentes. "
            "Lancez 'velo refresh' pour les mettre à jour."
        )
    if age_days > config.refresh.max_age_days:
        return (
            f"Les données des stations datent de {age_days:.1f} jours "
            f"(seuil : {config.refresh.max_age_days} jours). "
            "Lancez 'velo refresh' pour les actualiser."
        )
    return None
