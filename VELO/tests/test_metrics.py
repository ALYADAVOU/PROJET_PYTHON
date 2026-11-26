"""Tests unitaires pour le calcul des métriques historiques."""

from datetime import UTC, datetime

import pytest

from velo.analysis.metrics import compute_metrics, format_metric_value
from velo.models import ConfigError, StationSnapshot


def test_compute_all_four_metrics() -> None:
    """Vérifie avg_bikes, avg_docks, empty_rate et full_rate."""
    ts = datetime(2026, 11, 18, 8, 0, tzinfo=UTC)
    snaps = [
        StationSnapshot(ts, "1", 0, 20, True, True, True),
        StationSnapshot(ts, "1", 20, 0, True, True, True),
        StationSnapshot(ts, "1", 10, 10, True, True, True),
        # Hors service : ne doit pas compter comme vide ni comme pleine
        StationSnapshot(ts, "1", 0, 0, False, False, False),
    ]

    res = compute_metrics(snaps, ["avg_bikes", "avg_docks", "empty_rate", "full_rate"])
    assert res["avg_bikes"] == pytest.approx(7.5)
    assert res["avg_docks"] == pytest.approx(7.5)
    assert res["empty_rate"] == pytest.approx(25.0)
    assert res["full_rate"] == pytest.approx(25.0)

    assert format_metric_value("empty_rate", res["empty_rate"]) == "25 %"
    assert format_metric_value("avg_bikes", res["avg_bikes"]) == "7.5"


def test_unknown_metric_raises_config_error() -> None:
    """Une métrique inconnue doit lever ConfigError."""
    with pytest.raises(ConfigError, match="Métrique inconnue"):
        compute_metrics([], ["invalid_metric"])
