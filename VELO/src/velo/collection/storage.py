"""Stockage et lecture des relevés historiques au format CSV quotidien.

Respecte strictement le format imposé par le cahier des charges (section 4.2) :
- un fichier par jour : ``AAAA-MM-JJ.csv`` ;
- colonnes :
  ``timestamp,station_id,bikes,docks,is_installed,is_renting,is_returning,last_reported`` ;
- dates écrites au format ISO 8601 en heure locale avec décalage horaire ;
- ouverture avec ``encoding="utf-8"`` et ``newline=""`` ;
- tolérance aux lignes CSV corrompues (journalisées puis ignorées sans plantage).
"""

import csv
import logging
from datetime import date, datetime
from pathlib import Path

from velo.models import CollectionPeriod, NetworkSnapshot, StationSnapshot

logger = logging.getLogger(__name__)

# En-têtes exacts exigés par le cahier des charges
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
    """Formate un ``datetime`` en ISO 8601 heure locale avec décalage horaire."""
    local_dt = dt.astimezone()
    return local_dt.replace(microsecond=0).isoformat()


def csv_path_for_timestamp(history_dir: Path, ts: datetime) -> Path:
    """Détermine le fichier CSV quotidien correspondant à la date locale de ``ts``."""
    local_date = ts.astimezone().strftime("%Y-%m-%d")
    return history_dir / f"{local_date}.csv"


def _format_bool(value: bool) -> str:
    """Convertit un booléen Python en ``true`` / ``false`` minuscules."""
    return "true" if value else "false"


def _parse_csv_bool(raw: str) -> bool:
    """Parse ``true`` / ``false`` (ou ``1`` / ``0``) depuis une cellule CSV."""
    cleaned = raw.strip().lower()
    if cleaned in ("true", "1"):
        return True
    if cleaned in ("false", "0"):
        return False
    raise ValueError(f"Booléen CSV invalide : {raw!r}")


def _parse_iso_datetime(raw: str) -> datetime:
    """Parse une date ISO 8601 avec gestion du suffixe ``Z`` éventuel."""
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def append_snapshot(
    history_dir: Path,
    snapshot: NetworkSnapshot,
    recorded_at: datetime | None = None,
) -> tuple[Path, int]:
    """Ajoute toutes les stations d'un ``NetworkSnapshot`` dans le CSV du jour.

    Args:
        history_dir: Dossier contenant les fichiers ``AAAA-MM-JJ.csv``.
        snapshot: Relevé complet du réseau à enregistrer.
        recorded_at: Horodatage explicite du relevé (par défaut ``snapshot.last_updated``).

    Returns:
        Un couple ``(chemin_csv, nombre_lignes_ecrites)``.
    """
    history_dir.mkdir(parents=True, exist_ok=True)
    ts = recorded_at if recorded_at is not None else snapshot.last_updated
    ts_iso = format_iso_local(ts)
    csv_path = csv_path_for_timestamp(history_dir, ts)

    # N'écrit l'en-tête que si le fichier n'existe pas encore ou est vide
    needs_header = not csv_path.exists() or csv_path.stat().st_size == 0

    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if needs_header:
            writer.writerow(CSV_HEADERS)

        for status in snapshot.statuses:
            last_rep_iso = (
                format_iso_local(status.last_reported)
                if status.last_reported is not None
                else ""
            )
            writer.writerow(
                [
                    ts_iso,
                    status.station_id,
                    status.bikes_available,
                    status.docks_available,
                    _format_bool(status.is_installed),
                    _format_bool(status.is_renting),
                    _format_bool(status.is_returning),
                    last_rep_iso,
                ]
            )

    return csv_path, len(snapshot.statuses)


def read_csv_file(csv_path: Path) -> list[StationSnapshot]:
    """Lit un fichier CSV quotidien et ignore les lignes invalides en les journalisant."""
    snapshots: list[StationSnapshot] = []

    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                return []

            # Vérifie que les colonnes essentielles sont bien présentes
            required = {
                "timestamp",
                "station_id",
                "bikes",
                "docks",
                "is_installed",
                "is_renting",
                "is_returning",
            }
            if not required.issubset(set(reader.fieldnames)):
                logger.warning(
                    "En-tête CSV invalide dans '%s' : colonnes manquantes.",
                    csv_path,
                )
                return []

            for line_num, row in enumerate(reader, start=2):
                try:
                    ts = _parse_iso_datetime(row["timestamp"])
                    station_id = (row["station_id"] or "").strip()
                    if not station_id:
                        raise ValueError("station_id vide")

                    bikes = int(row["bikes"])
                    docks = int(row["docks"])
                    if bikes < 0 or docks < 0:
                        raise ValueError("bikes/docks négatifs")

                    is_installed = _parse_csv_bool(row["is_installed"])
                    is_renting = _parse_csv_bool(row["is_renting"])
                    is_returning = _parse_csv_bool(row["is_returning"])

                    raw_last_rep = (row.get("last_reported") or "").strip()
                    last_reported = _parse_iso_datetime(raw_last_rep) if raw_last_rep else None

                    snapshots.append(
                        StationSnapshot(
                            timestamp=ts,
                            station_id=station_id,
                            bikes=bikes,
                            docks=docks,
                            is_installed=is_installed,
                            is_renting=is_renting,
                            is_returning=is_returning,
                            last_reported=last_reported,
                        )
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    # Une ligne invalide ne doit jamais bloquer l'analyse des autres lignes
                    logger.warning(
                        "Ligne invalide ignorée dans %s (ligne %d) : %s",
                        csv_path.name,
                        line_num,
                        exc,
                    )
    except OSError as exc:
        logger.warning("Impossible de lire le fichier CSV '%s' : %s", csv_path, exc)

    return snapshots


def load_history_snapshots(
    history_dir: Path,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[StationSnapshot]:
    """Charge tous les relevés historiques disponibles (filtrés optionnellement par date)."""
    if not history_dir.exists():
        return []

    csv_files = sorted(history_dir.glob("*.csv"))
    all_snapshots: list[StationSnapshot] = []

    for csv_file in csv_files:
        # Filtre rapide sur le nom AAAA-MM-JJ.csv si le nom respecte le format standard
        stem = csv_file.stem
        try:
            file_date = date.fromisoformat(stem)
        except ValueError:
            file_date = None

        if file_date is not None:
            if date_from is not None and file_date < date_from:
                continue
            if date_to is not None and file_date > date_to:
                continue

        rows = read_csv_file(csv_file)
        for snap in rows:
            snap_date = snap.timestamp.astimezone().date()
            if date_from is not None and snap_date < date_from:
                continue
            if date_to is not None and snap_date > date_to:
                continue
            all_snapshots.append(snap)

    all_snapshots.sort(key=lambda s: (s.timestamp, s.station_id))
    return all_snapshots


def detect_periods(
    snapshots: list[StationSnapshot],
    max_gap_seconds: int,
) -> list[CollectionPeriod]:
    """Regroupe les relevés en périodes continues selon ``max_gap_seconds``.

    Deux relevés consécutifs appartiennent à la même période si l'écart entre
    leurs horodatages est inférieur ou égal à ``max_gap_seconds``
    (par exemple ``3 * interval_seconds``).
    """
    if not snapshots:
        return []

    unique_timestamps = sorted({snap.timestamp for snap in snapshots})
    groups: list[list[datetime]] = [[unique_timestamps[0]]]

    for ts in unique_timestamps[1:]:
        prev_ts = groups[-1][-1]
        gap = (ts - prev_ts).total_seconds()
        if gap <= max_gap_seconds:
            groups[-1].append(ts)
        else:
            groups.append([ts])

    periods: list[CollectionPeriod] = []
    for index, group in enumerate(groups, start=1):
        start = group[0]
        end = group[-1]
        duration_seconds = max(0, int((end - start).total_seconds()))
        periods.append(
            CollectionPeriod(
                index=index,
                start=start,
                end=end,
                duration_seconds=duration_seconds,
                snapshot_count=len(group),
                timestamps=group,
            )
        )

    return periods
