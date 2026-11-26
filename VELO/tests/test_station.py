"""Tests unitaires pour la commande ``velo station``."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from velo.commands.station import run_station_list, run_station_search, run_station_show
from velo.config import build_default_config
from velo.models import DataError, NetworkSnapshot, StationStatus


def _write_local_stations(network_dir: Path) -> None:
    network_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "data": {
            "stations": [
                {
                    "station_id": "43",
                    "name": "Gare Lille Flandres",
                    "lat": 50.636,
                    "lon": 3.070,
                    "capacity": 40,
                },
                {
                    "station_id": "44",
                    "name": "Gare Lille Europe",
                    "lat": 50.639,
                    "lon": 3.075,
                    "capacity": 30,
                },
                {"station_id": "42", "name": "Vauban", "lat": 50.632, "lon": 3.046, "capacity": 20},
            ]
        }
    }
    (network_dir / "station_information.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_station_search_list_and_show(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Vérifie search, list et show sur des données locales et un statut simulé."""
    config = build_default_config(data_folder=tmp_path)
    _write_local_stations(config.network_dir)

    assert run_station_search(config, "gare") == 0
    out_search = capsys.readouterr().out
    assert "Gare Lille Flandres" in out_search
    assert "Vauban" not in out_search

    assert run_station_list(config) == 0
    out_list = capsys.readouterr().out
    assert "Vauban" in out_list

    snapshot = NetworkSnapshot(
        network_name="V'Lille",
        last_updated=datetime(2026, 11, 16, 12, 5, tzinfo=UTC),
        statuses=[StationStatus("42", 3, 17, True, True, True)],
    )
    monkeypatch.setattr("velo.commands.station.fetch_live_status", lambda url, name: snapshot)

    assert run_station_show(config, "42") == 0
    out_show = capsys.readouterr().out
    assert "42 - Vauban" in out_show
    assert "Vélos     : 3" in out_show


def test_station_show_unknown_id_raises(tmp_path: Path) -> None:
    """Consulter une station inconnue doit lever DataError."""
    config = build_default_config(data_folder=tmp_path)
    _write_local_stations(config.network_dir)

    with pytest.raises(DataError, match="Station inconnue"):
        run_station_show(config, "9999")
