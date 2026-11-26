"""Tests unitaires pour la commande ``velo alerts``."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from velo.commands.alerts import run_alerts
from velo.config import build_default_config
from velo.models import ConfigError, NetworkSnapshot, StationStatus


def _seed_stations(network_dir: Path) -> None:
    network_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "data": {
            "stations": [
                {"station_id": "27", "name": "Cormontaigne", "lat": 50.62, "lon": 3.04},
                {"station_id": "43", "name": "Gare Lille Flandres", "lat": 50.63, "lon": 3.07},
                {"station_id": "18", "name": "Rihour", "lat": 50.63, "lon": 3.06},
            ]
        }
    }
    (network_dir / "station_information.json").write_text(json.dumps(payload), encoding="utf-8")


def test_alerts_groups_and_cli_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Vérifie le classement des alertes et le remplacement des seuils via options CLI."""
    config = build_default_config(data_folder=tmp_path)
    _seed_stations(config.network_dir)

    snapshot = NetworkSnapshot(
        network_name="V'Lille",
        last_updated=datetime(2026, 11, 16, 12, 5, tzinfo=UTC),
        statuses=[
            StationStatus("27", 0, 0, True, False, True),
            StationStatus("43", 4, 10, True, True, True),
            StationStatus("18", 20, 0, True, True, True),
        ],
    )
    monkeypatch.setattr("velo.commands.alerts.fetch_live_status", lambda url, name: snapshot)

    # Avec --low-bikes 5, la station 43 (4 vélos) passe en alerte
    assert run_alerts(config, low_bikes_opt=5, low_docks_opt=0) == 0
    out = capsys.readouterr().out

    assert "Hors service (1)" in out
    assert "27 Cormontaigne" in out
    assert "Vide ou presque (1)" in out
    assert "43 Gare Lille Flandres (4)" in out
    assert "Pleine ou presque (1)" in out
    assert "18 Rihour (0 place)" in out


def test_alerts_none_message_and_negative_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sans alerte un message clair est affiché ; un seuil négatif est rejeté."""
    config = build_default_config(data_folder=tmp_path)
    _seed_stations(config.network_dir)

    snapshot = NetworkSnapshot(
        network_name="V'Lille",
        last_updated=datetime(2026, 11, 16, 12, 5, tzinfo=UTC),
        statuses=[StationStatus("43", 10, 10, True, True, True)],
    )
    monkeypatch.setattr("velo.commands.alerts.fetch_live_status", lambda url, name: snapshot)

    assert run_alerts(config) == 0
    assert "Aucune alerte" in capsys.readouterr().out

    with pytest.raises(ConfigError):
        run_alerts(config, low_bikes_opt=-1)
