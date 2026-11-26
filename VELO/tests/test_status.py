"""Tests unitaires pour la commande ``velo status``."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from velo.commands.status import run_status
from velo.config import build_default_config
from velo.models import NetworkSnapshot, StationStatus


def test_status_displays_summary_and_warns_when_static_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """velo status affiche les compteurs réseau et avertit si les fichiers statiques manquent."""
    config = build_default_config(data_folder=tmp_path)
    snapshot = NetworkSnapshot(
        network_name="V'Lille",
        last_updated=datetime(2026, 11, 16, 12, 5, tzinfo=UTC),
        statuses=[
            StationStatus("1", 10, 10, True, True, True),
            StationStatus("2", 0, 20, True, True, True),
        ],
    )

    monkeypatch.setattr("velo.commands.status.fetch_live_status", lambda url, name: snapshot)

    code = run_status(config)
    out = capsys.readouterr().out

    assert code == 0
    assert "Avertissement" in out
    assert "en service 2 / 2" in out
    assert "disponibles 10" in out
    assert "taux de remplissage 25 %" in out
