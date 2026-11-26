"""Tests unitaires pour la commande ``velo refresh``."""

from pathlib import Path

import pytest

from velo.commands.refresh import run_refresh
from velo.config import build_default_config
from velo.models import StationInfo, SystemInfo, VehicleType


def test_refresh_updates_static_files_and_prints_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """velo refresh télécharge les données statiques et affiche le nombre de stations."""
    config = build_default_config(data_folder=tmp_path)

    monkeypatch.setattr(
        "velo.commands.refresh.fetch_static_feeds",
        lambda url, d: (
            SystemInfo("vlille", "V'Lille"),
            [
                StationInfo("1", "Rihour", 50.63, 3.06),
                StationInfo("2", "Vauban", 50.63, 3.04),
            ],
            [VehicleType("v1", "bicycle", "human")],
        ),
    )

    code = run_refresh(config)
    out = capsys.readouterr().out

    assert code == 0
    assert "V'Lille" in out
    assert "2 stations" in out

