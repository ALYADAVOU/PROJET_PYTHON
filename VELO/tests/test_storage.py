"""Tests unitaires pour le stockage CSV quotidien et la détection des périodes."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from velo.collection.storage import (
    append_snapshot,
    detect_periods,
    load_history_snapshots,
    read_csv_file,
)
from velo.models import NetworkSnapshot, StationStatus


def test_append_and_read_csv_cross_midnight_and_corrupted_lines(tmp_path: Path) -> None:
    """Vérifie l'écriture par jour, le passage de minuit et la tolérance aux lignes invalides."""
    tz = timezone(timedelta(hours=1))
    t1 = datetime(2026, 11, 18, 23, 58, 0, tzinfo=tz)
    t2 = datetime(2026, 11, 19, 0, 2, 0, tzinfo=tz)

    snap1 = NetworkSnapshot(
        "V'Lille",
        t1,
        [StationStatus("42", 3, 17, True, True, True, last_reported=t1 - timedelta(seconds=20))],
    )
    snap2 = NetworkSnapshot(
        "V'Lille",
        t2,
        [StationStatus("42", 4, 16, True, True, True, last_reported=t2 - timedelta(seconds=10))],
    )

    p1, n1 = append_snapshot(tmp_path, snap1)
    p2, n2 = append_snapshot(tmp_path, snap2)

    assert n1 == 1 and n2 == 1
    assert p1.name == "2026-11-18.csv"
    assert p2.name == "2026-11-19.csv"

    # Ajoute volontairement une ligne corrompue dans le CSV du 18 novembre
    with p1.open("a", encoding="utf-8", newline="") as handle:
        handle.write("bad-date,42,abc,17,true,true,true,\n")

    rows = read_csv_file(p1)
    assert len(rows) == 1
    assert rows[0].bikes == 3

    all_rows = load_history_snapshots(tmp_path)
    assert len(all_rows) == 2

    # L'écart entre 23:58 et 00:02 est de 240s <= 360s : une seule période sur 2 fichiers !
    periods = detect_periods(all_rows, max_gap_seconds=360)
    assert len(periods) == 1
    assert periods[0].snapshot_count == 2
    assert periods[0].duration_seconds == 240


def test_detect_periods_splits_when_gap_exceeds_threshold(tmp_path: Path) -> None:
    """Un trou supérieur au seuil sépare l'historique en plusieurs périodes."""
    tz = timezone(timedelta(hours=1))
    base = datetime(2026, 11, 18, 8, 0, 0, tzinfo=tz)

    for offset_min in (0, 2, 4, 30, 32):
        ts = base + timedelta(minutes=offset_min)
        snap = NetworkSnapshot("V'Lille", ts, [StationStatus("1", 5, 5, True, True, True)])
        append_snapshot(tmp_path, snap)

    snaps = load_history_snapshots(tmp_path)
    periods = detect_periods(snaps, max_gap_seconds=360)
    assert len(periods) == 2
    assert periods[0].snapshot_count == 3
    assert periods[1].snapshot_count == 2

