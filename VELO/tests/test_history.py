"""Tests unitaires pour la commande ``velo history``."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from velo.collection.storage import append_snapshot
from velo.commands.history import run_history
from velo.config import build_default_config
from velo.models import ConfigError, NetworkSnapshot, StationStatus


def test_history_empty_and_with_periods(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Affiche un message d'aide si vide, sinon liste les périodes détectées."""
    config = build_default_config(data_folder=tmp_path)

    assert run_history(config) == 0
    assert "velo collect" in capsys.readouterr().out

    tz = timezone(timedelta(hours=1))
    base = datetime(2026, 11, 18, 7, 15, 0, tzinfo=tz)
    for offset in (0, 2, 4):
        ts = base + timedelta(minutes=offset)
        append_snapshot(
            config.history_dir,
            NetworkSnapshot("V'Lille", ts, [StationStatus("1", 5, 5, True, True, True)]),
        )

    assert run_history(config, from_str="2026-11-18", to_str="2026-11-18") == 0
    out = capsys.readouterr().out
    assert "1 période, 3 relevés" in out


def test_history_rejects_inverted_dates(tmp_path: Path) -> None:
    """--from postérieur à --to doit lever ConfigError."""
    config = build_default_config(data_folder=tmp_path)
    with pytest.raises(ConfigError):
        run_history(config, from_str="2026-11-20", to_str="2026-11-18")

