"""Tests unitaires pour le collecteur et la commande ``velo collect``."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from velo.collection.collector import collect_loop, parse_duration, parse_until_datetime
from velo.collection.storage import load_history_snapshots
from velo.commands.collect import run_collect
from velo.config import build_default_config
from velo.models import ConfigError, NetworkError, NetworkSnapshot, StationStatus


def test_parse_duration_and_until() -> None:
    """Vérifie le parsing des durées et dates cibles."""
    assert parse_duration("3h") == timedelta(hours=3)
    assert parse_duration("1h30m") == timedelta(hours=1, minutes=30)
    assert parse_until_datetime("2026-11-18 09:30").hour == 9

    with pytest.raises(ConfigError):
        parse_duration("0m")
    with pytest.raises(ConfigError):
        parse_until_datetime("18/11/2026")


def test_collect_deduplicates_last_updated_and_survives_network_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deux relevés avec même last_updated ne sont écrits qu'une fois ; les erreurs continuent."""
    config = build_default_config(data_folder=tmp_path)
    tz = timezone(timedelta(hours=1))
    t1 = datetime(2026, 11, 18, 8, 0, 0, tzinfo=tz)
    t2 = datetime(2026, 11, 18, 8, 2, 0, tzinfo=tz)

    events = [
        NetworkSnapshot("V'Lille", t1, [StationStatus("1", 5, 10, True, True, True)]),
        NetworkSnapshot("V'Lille", t1, [StationStatus("1", 5, 10, True, True, True)]),  # doublon
        NetworkError("Timeout temporaire"),
        NetworkSnapshot("V'Lille", t2, [StationStatus("1", 4, 11, True, True, True)]),
    ]
    idx = {"i": 0}
    clock = {"now": t1}

    def fake_fetch(url: str, name: str) -> NetworkSnapshot:
        item = events[idx["i"]]
        idx["i"] += 1
        if isinstance(item, Exception):
            raise item
        return item

    def fake_sleep(seconds: float) -> None:
        clock["now"] = clock["now"] + timedelta(seconds=seconds)
        if idx["i"] >= len(events):
            raise KeyboardInterrupt

    monkeypatch.setattr("velo.collection.collector.fetch_live_status", fake_fetch)

    summary = collect_loop(
        config=config,
        interval_seconds=120,
        sleep_fn=fake_sleep,
        now_fn=lambda: clock["now"],
    )

    assert summary.saved_snapshots == 2
    assert summary.skipped_duplicates == 1
    assert summary.errors == 1
    assert len(load_history_snapshots(config.history_dir)) == 2


def test_run_collect_once_and_min_interval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--once enregistre un seul relevé et affiche le bilan ; intervalle < 60 refusé."""
    config = build_default_config(data_folder=tmp_path)
    t1 = datetime(2026, 11, 18, 8, 0, 0, tzinfo=UTC)

    monkeypatch.setattr(
        "velo.collection.collector.fetch_live_status",
        lambda url, name: NetworkSnapshot(
            "V'Lille",
            t1,
            [StationStatus("1", 3, 7, True, True, True)],
        ),
    )

    assert run_collect(config, once=True) == 0
    out = capsys.readouterr().out
    assert "Relevés enregistrés : 1" in out

    with pytest.raises(ConfigError, match="60"):
        run_collect(config, interval_opt=10, once=True)
