"""Lecture et écriture des fichiers CSV quotidiens d'historique.

Format imposé par le cahier des charges :
- un fichier par jour : ``AAAA-MM-JJ.csv`` ;
- colonnes :
  ``timestamp,station_id,bikes,docks,is_installed,is_renting,is_returning,last_reported`` ;
- dates au format ISO 8601 avec décalage horaire local ;
- ouverture avec ``encoding="utf-8"`` et ``newline=""``.
"""

import csv
import logging
from datetime import date, datetime
from pathlib import Path

from velo.models import CollectionPeriod, NetworkSnapshot, StationSnapshot

logger = logging.getLogger(__name__)

CSV_HEADERS = [
    "timestamp",
    "station_id",
    "bikes",
    "docks",
    "is_installed",
    "is_renting",
    "is_returning",
    "last_reported",
]


def format_iso_local(dt: datetime) -> str:
    """Formate une date en ISO 8601 avec l'heure locale et son décalage horaire."""
    return dt.astimezone().replace(microsecond=0).isoformat()


def csv_path_for_timestamp(history_dir: Path, ts: datetime) -> Path:
    """Retourne le fichier CSV du jour correspondant à la date ``ts``."""
    return history_dir / f"{ts.astimezone().strftime('%Y-%m-%d')}.csv"


def _parse_bool_cell(raw: str) -> bool:
    """Lit ``true``/``false`` (ou ``1``/``0``) depuis une cellule CSV."""
    text = raw.strip().lower()
    if text in ("true", "1"):
        return True
    if text in ("false", "0"):
        return False
    raise ValueError(f"Booléen CSV invalide : {raw!r}")


def _parse_iso_cell(raw: str) -> datetime:
    """Lit une date ISO 8601 depuis une cellule CSV."""
    dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo is not None else dt.astimezone()


def append_snapshot(
    history_dir: Path,
    snapshot: NetworkSnapshot,
    recorded_at: datetime | None = None,
) -> tuple[Path, int]:
    """Ajoute toutes les stations d'un relevé dans le fichier CSV du jour."""
    history_dir.mkdir(parents=True, exist_ok=True)
    ts = recorded_at if recorded_at is not None else snapshot.last_updated
    ts_iso = format_iso_local(ts)
    csv_path = csv_path_for_timestamp(history_dir, ts)

    # Écrit la ligne d'en-tête uniquement si le fichier est nouveau ou vide
    needs_header = not csv_path.exists() or csv_path.stat().st_size == 0

    with csv_path.open("a", encoding="utf-8", newline="") as fichier:
        writer = csv.writer(fichier)
        if needs_header:
            writer.writerow(CSV_HEADERS)

        for st in snapshot.statuses:
            last_rep = format_iso_local(st.last_reported) if st.last_reported else ""
            writer.writerow(
                [
                    ts_iso,
                    st.station_id,
                    st.bikes_available,
                    st.docks_available,
                    "true" if st.is_installed else "false",
                    "true" if st.is_renting else "false",
                    "true" if st.is_returning else "false",
                    last_rep,
                ]
            )

    return csv_path, len(snapshot.statuses)


def read_csv_file(csv_path: Path) -> list[StationSnapshot]:
    """Lit un fichier CSV quotidien ; les lignes invalides sont ignorées avec un log."""
    snapshots: list[StationSnapshot] = []

    try:
        with csv_path.open("r", encoding="utf-8", newline="") as fichier:
            reader = csv.DictReader(fichier)
            if reader.fieldnames is None or not set(CSV_HEADERS[:7]).issubset(reader.fieldnames):
                logger.warning("En-tête CSV invalide dans '%s'.", csv_path)
                return []

            for line_num, row in enumerate(reader, start=2):
                try:
                    sid = (row["station_id"] or "").strip()
                    bikes, docks = int(row["bikes"]), int(row["docks"])
                    if not sid or bikes < 0 or docks < 0:
                        raise ValueError("station_id ou compteurs invalides")

                    raw_rep = (row.get("last_reported") or "").strip()
                    snapshots.append(
                        StationSnapshot(
                            timestamp=_parse_iso_cell(row["timestamp"]),
                            station_id=sid,
                            bikes=bikes,
                            docks=docks,
                            is_installed=_parse_bool_cell(row["is_installed"]),
                            is_renting=_parse_bool_cell(row["is_renting"]),
                            is_returning=_parse_bool_cell(row["is_returning"]),
                            last_reported=_parse_iso_cell(raw_rep) if raw_rep else None,
                        )
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    # On ignore la ligne corrompue sans faire planter le programme
                    logger.warning("Ligne %d ignorée dans %s : %s", line_num, csv_path.name, exc)
    except OSError as exc:
        logger.warning("Impossible de lire '%s' : %s", csv_path, exc)

    return snapshots


def load_history_snapshots(
    history_dir: Path,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[StationSnapshot]:
    """Charge tous les relevés CSV du dossier ``history`` (filtrés optionnellement par date)."""
    if not history_dir.exists():
        return []

    snapshots: list[StationSnapshot] = []
    for csv_file in sorted(history_dir.glob("*.csv")):
        try:
            file_date = date.fromisoformat(csv_file.stem)
            if date_from is not None and file_date < date_from:
                continue
            if date_to is not None and file_date > date_to:
                continue
        except ValueError:
            pass

        for snap in read_csv_file(csv_file):
            snap_date = snap.timestamp.astimezone().date()
            if date_from is not None and snap_date < date_from:
                continue
            if date_to is not None and snap_date > date_to:
                continue
            snapshots.append(snap)

    snapshots.sort(key=lambda s: (s.timestamp, s.station_id))
    return snapshots


def detect_periods(
    snapshots: list[StationSnapshot],
    max_gap_seconds: int,
) -> list[CollectionPeriod]:
    """Regroupe les relevés en périodes continues selon l'écart maximal toléré."""
    if not snapshots:
        return []

    timestamps = sorted({snap.timestamp for snap in snapshots})
    groups: list[list[datetime]] = [[timestamps[0]]]

    # Si l'écart entre deux relevés dépasse max_gap_seconds, on démarre une nouvelle période
    for ts in timestamps[1:]:
        if (ts - groups[-1][-1]).total_seconds() <= max_gap_seconds:
            groups[-1].append(ts)
        else:
            groups.append([ts])

    periods: list[CollectionPeriod] = []
    for index, group in enumerate(groups, start=1):
        duration = max(0, int((group[-1] - group[0]).total_seconds()))
        periods.append(
            CollectionPeriod(
                index=index,
                start=group[0],
                end=group[-1],
                duration_seconds=duration,
                snapshot_count=len(group),
                timestamps=group,
            )
        )
    return periods
