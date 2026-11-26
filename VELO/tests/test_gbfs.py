"""Tests unitaires pour le module d'isolation GBFS (v2 et v3)."""

from pathlib import Path

import pytest

from velo.gbfs import (
    discover_feeds,
    fetch_live_status,
    fetch_static_feeds,
    parse_station_information,
    parse_station_status,
)
from velo.models import GBFSError


def test_discover_feeds_v2_and_v3() -> None:
    """Le découvreur supporte gbfs.json en format v2 (par langue) et v3 (direct)."""
    v2_payload = {
        "data": {
            "fr": {
                "feeds": [
                    {"name": "system_information", "url": "https://ex/sys.json"},
                    {"name": "station_information", "url": "https://ex/info.json"},
                    {"name": "station_status", "url": "https://ex/status.json"},
                ]
            }
        }
    }
    v3_payload = {
        "data": {
            "feeds": [
                {"name": "station_status", "url": "https://ex/v3/status.json"},
            ]
        }
    }

    feeds_v2 = discover_feeds(v2_payload)
    assert feeds_v2["station_status"] == "https://ex/status.json"

    feeds_v3 = discover_feeds(v3_payload)
    assert feeds_v3["station_status"] == "https://ex/v3/status.json"


def test_parse_station_information_and_status() -> None:
    """Les données GBFS valides sont transformées en objets StationInfo et StationStatus."""
    info_payload = {
        "data": {
            "stations": [
                {
                    "station_id": "43",
                    "name": "Gare Lille Flandres",
                    "lat": 50.6365,
                    "lon": 3.0698,
                    "capacity": 40,
                }
            ]
        }
    }
    status_payload = {
        "last_updated": 1763450040,
        "data": {
            "stations": [
                {
                    "station_id": "43",
                    "num_bikes_available": 12,
                    "num_docks_available": 28,
                    "is_installed": 1,
                    "is_renting": 1,
                    "is_returning": 1,
                    "last_reported": 1763450000,
                }
            ]
        },
    }

    stations = parse_station_information(info_payload)
    assert len(stations) == 1
    assert stations[0].station_id == "43"
    assert stations[0].name == "Gare Lille Flandres"

    snapshot = parse_station_status(status_payload, network_name="V'Lille")
    assert snapshot.network_name == "V'Lille"
    assert len(snapshot.statuses) == 1
    assert snapshot.statuses[0].bikes_available == 12
    assert snapshot.statuses[0].is_renting is True


def test_parse_invalid_status_raises_gbfs_error() -> None:
    """Un flux GBFS invalide (ex: vélos négatifs) doit lever GBFSError."""
    bad_payload = {
        "last_updated": 1763450040,
        "data": {
            "stations": [
                {
                    "station_id": "1",
                    "num_bikes_available": -5,
                    "num_docks_available": 10,
                }
            ]
        },
    }
    with pytest.raises(GBFSError):
        parse_station_status(bad_payload, network_name="V'Lille")


def test_fetch_static_and_live_with_mocked_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vérifie le téléchargement et la sauvegarde locale avec appels réseau simulés."""
    responses = {
        "https://mock/gbfs.json": {
            "data": {
                "fr": {
                    "feeds": [
                        {"name": "system_information", "url": "https://mock/sys.json"},
                        {"name": "station_information", "url": "https://mock/info.json"},
                        {"name": "vehicle_types", "url": "https://mock/vt.json"},
                        {"name": "station_status", "url": "https://mock/status.json"},
                    ]
                }
            }
        },
        "https://mock/sys.json": {
            "last_updated": 1763450000,
            "data": {"system_id": "vlille", "name": "V'Lille"},
        },
        "https://mock/info.json": {
            "data": {
                "stations": [
                    {"station_id": "42", "name": "Vauban", "lat": 50.63, "lon": 3.04}
                ]
            }
        },
        "https://mock/vt.json": {
            "data": {
                "vehicle_types": [
                    {
                        "vehicle_type_id": "bike",
                        "form_factor": "bicycle",
                        "propulsion_type": "human",
                    }
                ]
            }
        },
        "https://mock/status.json": {
            "last_updated": "2026-11-18T08:14:00+01:00",
            "data": {
                "stations": [
                    {
                        "station_id": "42",
                        "num_vehicles_available": 3,
                        "num_docks_available": 17,
                        "is_installed": True,
                        "is_renting": True,
                        "is_returning": True,
                    }
                ]
            },
        },
    }

    monkeypatch.setattr("velo.gbfs.fetch_json", lambda url: responses[url])

    sys_info, stations, vtypes = fetch_static_feeds("https://mock/gbfs.json", tmp_path)
    assert sys_info.name == "V'Lille"
    assert len(stations) == 1
    assert len(vtypes) == 1
    assert (tmp_path / "station_information.json").exists()

    live = fetch_live_status("https://mock/gbfs.json", "V'Lille")
    assert live.statuses[0].bikes_available == 3
