"""Tests unitaires pour la logique d'analyse et de filtrage (``analysis.py``)."""

from datetime import datetime, timedelta, timezone

import pytest

from velo.analysis.analysis import (
    NoQueryDataError,
    QueryFilters,
    parse_days_filter,
    parse_hours_range,
    run_query_analysis,
)
from velo.collection.storage import detect_periods
from velo.models import ConfigError, StationInfo, StationSnapshot


def _build_dataset() -> list[StationSnapshot]:
    tz = timezone(timedelta(hours=1))
    # 2026-11-18 est un mercredi (weekday=2), 2026-11-21 est un samedi (weekday=5)
    t_wed_7 = datetime(2026, 11, 18, 7, 30, tzinfo=tz)
    t_wed_8 = datetime(2026, 11, 18, 8, 30, tzinfo=tz)
    t_sat_8 = datetime(2026, 11, 21, 8, 30, tzinfo=tz)

    return [
        StationSnapshot(t_wed_7, "61", 0, 20, True, True, True),
        StationSnapshot(t_wed_8, "61", 0, 20, True, True, True),
        StationSnapshot(t_sat_8, "61", 10, 10, True, True, True),
        StationSnapshot(t_wed_7, "43", 5, 15, True, True, True),
        StationSnapshot(t_wed_8, "43", 0, 20, True, True, True),
        StationSnapshot(t_sat_8, "43", 12, 8, True, True, True),
    ]


def test_parse_days_and_hours_filters() -> None:
    """Vérifie le parsing de --days et --hours."""
    assert parse_days_filter("weekdays") == {0, 1, 2, 3, 4}
    assert parse_days_filter("weekend") == {5, 6}
    assert parse_days_filter("lundi,mercredi") == {0, 2}
    assert parse_hours_range("7-9") == (7, 9)

    with pytest.raises(ConfigError):
        parse_days_filter("jour_inconnu")
    with pytest.raises(ConfigError):
        parse_hours_range("12-7")


def test_run_query_analysis_filters_grouping_and_interruptions() -> None:
    """Vérifie le filtrage, le regroupement par station, --top et la détection d'interruptions."""
    snaps = _build_dataset()
    periods = detect_periods(snaps, max_gap_seconds=360)
    stations = {
        "61": StationInfo("61", "Gambetta", 50.62, 3.05),
        "43": StationInfo("43", "Gare Lille Flandres", 50.63, 3.07),
    }

    result = run_query_analysis(
        snapshots=snaps,
        periods=periods,
        stations_by_id=stations,
        filters=QueryFilters(weekdays={0, 1, 2, 3, 4}, hours_range=(7, 9)),
        metrics=["empty_rate"],
        group_by="station",
        top_n=1,
        max_gap_seconds=360,
    )

    assert result.has_interruptions is True
    assert result.snapshot_count == 2
    assert len(result.rows) == 1
    assert result.rows[0].label == "61 Gambetta"
    assert result.rows[0].metrics["empty_rate"] == pytest.approx(100.0)


def test_run_query_analysis_raises_with_available_periods_when_empty() -> None:
    """Sans donnée correspondante, NoQueryDataError transporte les périodes existantes."""
    snaps = _build_dataset()
    periods = detect_periods(snaps, max_gap_seconds=360)

    with pytest.raises(NoQueryDataError) as exc_info:
        run_query_analysis(
            snapshots=snaps,
            periods=periods,
            stations_by_id={},
            filters=QueryFilters(station_id="999"),
            metrics=["avg_bikes"],
        )

    assert len(exc_info.value.available_periods) == len(periods)

