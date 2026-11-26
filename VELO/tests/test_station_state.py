"""Tests unitaires pour les règles d'état des stations, stats, alertes et regex."""

from datetime import UTC, datetime

import pytest

from velo.models import DataError, NetworkSnapshot, StationInfo, StationStatus
from velo.station_state import (
    classify_station_state,
    compute_alerts,
    compute_network_stats,
    is_out_of_service,
    search_stations,
)


def _sample_snapshot() -> NetworkSnapshot:
    ts = datetime(2026, 11, 16, 12, 5, tzinfo=UTC)
    return NetworkSnapshot(
        network_name="V'Lille",
        last_updated=ts,
        statuses=[
            # Station normale
            StationStatus("1", 10, 10, True, True, True),
            # Station vide
            StationStatus("2", 0, 20, True, True, True),
            # Station presque vide (seuil 2)
            StationStatus("3", 2, 18, True, True, True),
            # Station pleine
            StationStatus("4", 15, 0, True, True, True),
            # Station hors service avec 0 vélos/places : ne doit PAS être classée vide/pleine
            StationStatus("5", 0, 0, True, False, True),
        ],
    )


def test_is_out_of_service_and_classification() -> None:
    """Vérifie la priorité hors service -> vide -> presque vide -> pleine."""
    snap = _sample_snapshot()
    assert is_out_of_service(snap.statuses[4]) is True
    assert classify_station_state(snap.statuses[4], low_bikes=2, low_docks=2) == "hors service"
    assert classify_station_state(snap.statuses[1], low_bikes=2, low_docks=2) == "vide"
    assert classify_station_state(snap.statuses[2], low_bikes=2, low_docks=2) == "presque vide"
    assert classify_station_state(snap.statuses[3], low_bikes=2, low_docks=2) == "pleine"
    assert classify_station_state(snap.statuses[0], low_bikes=2, low_docks=2) == "disponible"


def test_compute_network_stats_and_alerts_exclude_out_of_service_from_empty_full() -> None:
    """Une station hors service ne doit pas être signalée en double comme vide ou pleine."""
    snap = _sample_snapshot()
    stats = compute_network_stats(snap)
    assert stats.total_stations == 5
    assert stats.in_service_count == 4
    assert stats.out_of_service_count == 1
    assert stats.empty_count == 1
    assert stats.full_count == 1
    assert stats.total_bikes == 27
    assert stats.total_docks == 48

    stations_by_id = {
        str(i): StationInfo(str(i), f"Station {i}", 50.6, 3.0)
        for i in range(1, 6)
    }
    alerts = compute_alerts(snap, stations_by_id, low_bikes=2, low_docks=2)
    assert [a.station_id for a in alerts.out_of_service] == ["5"]
    assert [a.station_id for a in alerts.low_bikes_alerts] == ["2", "3"]
    assert [a.station_id for a in alerts.low_docks_alerts] == ["4"]


def test_search_stations_is_case_and_accent_insensitive() -> None:
    """La recherche regex tolère la casse, les accents et les motifs partiels."""
    stations = [
        StationInfo("10", "Château d'Ascq", 50.6, 3.1),
        StationInfo("43", "Gare Lille Flandres", 50.6, 3.0),
        StationInfo("44", "Gare Lille Europe", 50.6, 3.0),
    ]
    assert [s.station_id for s in search_stations(stations, "chateau")] == ["10"]
    assert [s.station_id for s in search_stations(stations, "^gare.*europe$")] == ["44"]

    with pytest.raises(DataError, match="Expression régulière invalide"):
        search_stations(stations, "[unclosed")
