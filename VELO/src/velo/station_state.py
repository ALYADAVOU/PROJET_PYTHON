"""Règles d'état des stations, statistiques réseau, alertes et recherche par regex.

Ce module contient uniquement des calculs simples sur nos objets ``StationInfo``
et ``NetworkSnapshot``. Il est partagé par ``status``, ``favorites``, ``alerts``
et ``dashboard``.
"""

import re
import unicodedata
from dataclasses import dataclass

from velo.config import VeloConfig
from velo.gbfs import get_static_files_age_days
from velo.models import DataError, NetworkSnapshot, StationInfo, StationStatus


@dataclass(frozen=True)
class NetworkStats:
    """Résumé global d'un réseau à un instant donné."""

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
    """Une station en alerte (hors service, vide/presque vide ou pleine/presque pleine)."""

    station_id: str
    name: str
    bikes: int
    docks: int


@dataclass(frozen=True)
class AlertsSummary:
    """Les trois listes d'alertes triées d'un relevé."""

    network_name: str
    last_updated_str: str
    out_of_service: list[AlertEntry]
    low_bikes_alerts: list[AlertEntry]
    low_docks_alerts: list[AlertEntry]


def is_out_of_service(status: StationStatus) -> bool:
    """Retourne True si la station est fermée (non installée, location ou retour coupé)."""
    return not (status.is_installed and status.is_renting and status.is_returning)


def classify_station_state(status: StationStatus, low_bikes: int, low_docks: int) -> str:
    """Donne un mot-clé simple décrivant l'état actuel d'une station."""
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
    """Permet de trier ``'2'`` avant ``'10'`` (tri numérique pour les IDs chiffrés)."""
    if station_id.isdigit():
        return (0, int(station_id))
    return (1, station_id)


def compute_network_stats(snapshot: NetworkSnapshot) -> NetworkStats:
    """Calcule les totaux (stations actives, vélos, places, %) d'un relevé réseau."""
    total_stations = len(snapshot.statuses)
    out_of_service = 0
    empty_count = 0
    full_count = 0
    total_bikes = 0
    total_docks = 0

    for st in snapshot.statuses:
        if is_out_of_service(st):
            out_of_service += 1
            continue  # On exclut les stations hors service des totaux utiles

        total_bikes += st.bikes_available
        total_docks += st.docks_available
        if st.bikes_available == 0:
            empty_count += 1
        if st.docks_available == 0:
            full_count += 1

    capacity = total_bikes + total_docks
    fill_rate = round((total_bikes / capacity) * 100) if capacity > 0 else 0

    return NetworkStats(
        network_name=snapshot.network_name,
        last_updated_str=snapshot.last_updated.strftime("%d/%m/%Y à %H:%M"),
        total_stations=total_stations,
        in_service_count=total_stations - out_of_service,
        out_of_service_count=out_of_service,
        empty_count=empty_count,
        full_count=full_count,
        total_bikes=total_bikes,
        total_docks=total_docks,
        fill_rate_pct=fill_rate,
    )


def compute_alerts(
    snapshot: NetworkSnapshot,
    stations_by_id: dict[str, StationInfo],
    low_bikes: int,
    low_docks: int,
) -> AlertsSummary:
    """Trie les stations à problème en 3 catégories (sans doublon avec hors service)."""
    out_of_service: list[AlertEntry] = []
    low_bikes_list: list[AlertEntry] = []
    low_docks_list: list[AlertEntry] = []

    for st in snapshot.statuses:
        info = stations_by_id.get(st.station_id)
        name = info.name if info is not None else f"Station {st.station_id}"
        entry = AlertEntry(st.station_id, name, st.bikes_available, st.docks_available)

        if is_out_of_service(st):
            out_of_service.append(entry)
            continue  # Une station hors service n'est pas comptée comme vide ou pleine

        if st.bikes_available <= low_bikes:
            low_bikes_list.append(entry)
        if st.docks_available <= low_docks:
            low_docks_list.append(entry)

    out_of_service.sort(key=lambda e: natural_station_sort_key(e.station_id))
    low_bikes_list.sort(key=lambda e: (e.bikes, natural_station_sort_key(e.station_id)))
    low_docks_list.sort(key=lambda e: (e.docks, natural_station_sort_key(e.station_id)))

    return AlertsSummary(
        network_name=snapshot.network_name,
        last_updated_str=snapshot.last_updated.strftime("%d/%m/%Y à %H:%M"),
        out_of_service=out_of_service,
        low_bikes_alerts=low_bikes_list,
        low_docks_alerts=low_docks_list,
    )


def strip_accents(text: str) -> str:
    """Enlève les accents d'un texte (ex: ``'Château'`` -> ``'Chateau'``)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def search_stations(stations: list[StationInfo] | object, pattern: str) -> list[StationInfo]:
    """Cherche les stations dont le nom correspond à l'expression régulière ``pattern``.

    La recherche est partielle, insensible aux majuscules et insensible aux accents.
    """
    if not pattern.strip():
        raise DataError("Le motif de recherche ne peut pas être vide.")

    try:
        regex = re.compile(strip_accents(pattern), re.IGNORECASE)
    except re.error as exc:
        raise DataError(f"Expression régulière invalide ({pattern!r}) : {exc}") from exc

    matches = [
        st for st in stations  # type: ignore[attr-defined]
        if regex.search(strip_accents(st.name)) is not None
    ]
    matches.sort(key=lambda st: natural_station_sort_key(st.station_id))
    return matches


def check_static_staleness(config: VeloConfig) -> str | None:
    """Vérifie si les fichiers statiques manquent ou dépassent ``max_age_days``."""
    age_days = get_static_files_age_days(config.network_dir)
    if age_days is None:
        return (
            "Les données statiques locales sont incomplètes ou absentes. "
            "Lancez 'velo refresh' pour les mettre à jour."
        )
    if age_days > config.refresh.max_age_days:
        return (
            f"Les données des stations datent de {age_days:.1f} jours "
            f"(seuil : {config.refresh.max_age_days} jours). Lancez 'velo refresh'."
        )
    return None
