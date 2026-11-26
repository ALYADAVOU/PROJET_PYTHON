"""Tests unitaires pour le tableau de bord temps réel (``velo dashboard``)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from velo.commands.dashboard import run_dashboard
from velo.config import build_default_config
from velo.models import ConfigError, NetworkError, NetworkSnapshot, StationStatus


def _seed_station(network_dir: Path) -> None:
    network_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "data": {
            "stations": [
                {"station_id": "42", "name": "Vauban", "lat": 50.63, "lon": 3.04},
            ]
        }
    }
    (network_dir / "station_information.json").write_text(json.dumps(payload), encoding="utf-8")


def test_dashboard_rejects_refresh_below_minimum(tmp_path: Path) -> None:
    """Le rafraîchissement du dashboard ne peut pas descendre sous 60 secondes."""
    config = build_default_config(data_folder=tmp_path)
    with pytest.raises(ConfigError, match="60"):
        run_dashboard(config, refresh_opt=15)


def test_dashboard_keeps_last_data_on_network_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """En cas d'erreur réseau au 2e cycle, les dernières données restent affichées."""
    config = build_default_config(data_folder=tmp_path)
    _seed_station(config.network_dir)

    calls = {"n": 0}
    snapshot = NetworkSnapshot(
        network_name="V'Lille",
        last_updated=datetime(2026, 11, 16, 12, 5, tzinfo=UTC),
        statuses=[StationStatus("42", 8, 12, True, True, True)],
    )

    def fake_fetch(url: str, name: str) -> NetworkSnapshot:
        calls["n"] += 1
        if calls["n"] == 1:
            return snapshot
        raise NetworkError("Connexion perdue")

    monkeypatch.setattr("velo.commands.dashboard.fetch_live_status", fake_fetch)

    code = run_dashboard(config, refresh_opt=60, max_cycles=2, sleep_fn=lambda _: None)
    out = capsys.readouterr().out

    assert code == 0
    assert "Erreur réseau" in out
    assert "Connexion perdue" in out
    assert "V'Lille" in out
