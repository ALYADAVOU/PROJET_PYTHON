"""Filtrage, regroupement et classement des relevés historiques pour ``velo query``."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from velo.analysis.metrics import compute_metrics, validate_metrics
from velo.models import (
    CollectionPeriod,
    ConfigError,
    DataError,
    StationInfo,
    StationSnapshot,
)
from velo.station_state import natural_station_sort_key

VALID_GROUP_BY = ("station", "hour", "weekday", "day")

# Correspondance entre noms de jours (français/anglais, complets ou abrégés) et weekday() 0..6
_DAY_ALIASES: dict[str, int] = {
    "lun": 0,
    "lundi": 0,
    "mon": 0,
    "monday": 0,
    "mar": 1,
    "mardi": 1,
    "tue": 1,
    "tuesday": 1,
    "mer": 2,
    "mercredi": 2,
    "wed": 2,
    "wednesday": 2,
    "jeu": 3,
    "jeudi": 3,
    "thu": 3,
    "thursday": 3,
    "ven": 4,
    "vendredi": 4,
    "fri": 4,
    "friday": 4,
    "sam": 5,
    "samedi": 5,
    "sat": 5,
    "saturday": 5,
    "dim": 6,
    "dimanche": 6,
    "sun": 6,
    "sunday": 6,
}

_WEEKDAY_LABELS = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")


class NoQueryDataError(DataError):
    """Erreur spécifique lorsqu'aucun relevé ne correspond aux filtres de ``velo query``."""

    def __init__(self, message: str, available_periods: list[CollectionPeriod]) -> None:
        super().__init__(message)
        self.available_periods = available_periods


@dataclass(frozen=True)
class QueryFilters:
    """Ensemble des critères de sélection des relevés pour une requête."""

    date_only: date | None = None
    dt_from: datetime | None = None
    dt_to: datetime | None = None
    period_ids: list[int] | None = None
    weekdays: set[int] | None = None
    hours_range: tuple[int, int] | None = None
    station_id: str | None = None


@dataclass(frozen=True)
class QueryRow:
    """Ligne de résultat agrégée par groupe pour une requête."""

    label: str
    metrics: dict[str, float]
    snapshot_count: int
    sort_key: object


@dataclass(frozen=True)
class QueryResult:
    """Résultat complet d'une requête analytique sur l'historique."""

    rows: list[QueryRow]
    used_periods: list[int]
    snapshot_count: int
    has_interruptions: bool
    metrics: list[str]
    group_by: str | None


def parse_date_only(raw: str) -> date:
    """Parse une date au format ``AAAA-MM-JJ``."""
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ConfigError(
            f"Format de date invalide pour --date : {raw!r}. Format attendu : AAAA-MM-JJ."
        ) from exc


def parse_datetime_bound(raw: str, option_name: str, is_end: bool = False) -> datetime:
    """Parse une borne de date/heure (``AAAA-MM-JJ`` ou ``AAAA-MM-JJ HH:MM``)."""
    text = raw.strip()
    # Si seule la date est fournie, on couvre toute la journée concernée
    try:
        d = date.fromisoformat(text)
        if is_end:
            return datetime(d.year, d.month, d.day, 23, 59, 59).astimezone()
        return datetime(d.year, d.month, d.day, 0, 0, 0).astimezone()
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt).astimezone()
        except ValueError:
            continue

    raise ConfigError(
        f"Format invalide pour {option_name} : {raw!r}. "
        "Formats acceptés : 'AAAA-MM-JJ' ou 'AAAA-MM-JJ HH:MM'."
    )


def parse_days_filter(raw: str) -> set[int]:
    """Parse ``--days`` (``weekdays``, ``weekend`` ou liste séparée par des virgules)."""
    cleaned = raw.strip().lower()
    if cleaned == "weekdays":
        return {0, 1, 2, 3, 4}
    if cleaned == "weekend":
        return {5, 6}

    days: set[int] = set()
    for token in cleaned.split(","):
        part = token.strip()
        if not part:
            continue
        if part not in _DAY_ALIASES:
            raise ConfigError(
                f"Jour invalide dans --days : {part!r}. "
                "Utilisez 'weekdays', 'weekend' ou des noms de jours (lundi, mardi, ...)."
            )
        days.add(_DAY_ALIASES[part])

    if not days:
        raise ConfigError("L'option --days ne peut pas être vide.")
    return days


def parse_hours_range(raw: str) -> tuple[int, int]:
    """Parse une plage horaire comme ``7-9`` (heures entières 0..23)."""
    text = raw.strip()
    parts = text.split("-")
    if len(parts) != 2:
        raise ConfigError(
            f"Format invalide pour --hours : {raw!r}. Format attendu : DEBUT-FIN (ex: 7-9)."
        )
    try:
        start_h = int(parts[0].strip())
        end_h = int(parts[1].strip())
    except ValueError as exc:
        raise ConfigError(f"Heures invalides dans --hours : {raw!r}.") from exc

    if not (0 <= start_h <= 23 and 0 <= end_h <= 24) or start_h > end_h:
        raise ConfigError(
            f"Plage horaire invalide pour --hours : {raw!r} (attendu 0 <= début <= fin <= 24)."
        )
    return start_h, end_h


def _matches_hours(dt: datetime, hours_range: tuple[int, int]) -> bool:
    """Vérifie si l'heure locale de ``dt`` appartient à la plage demandée.

    Convention documentée : ``7-9`` sélectionne les heures ``7 <= hour < 9``
    (c'est-à-dire la tranche 07:00 à 08:59). Si début == fin (ex: ``8-8``),
    seule l'heure ``8`` (08:00 à 08:59) est sélectionnée.
    """
    hour = dt.astimezone().hour
    start_h, end_h = hours_range
    if start_h == end_h:
        return hour == start_h
    return start_h <= hour < end_h


def run_query_analysis(
    snapshots: list[StationSnapshot],
    periods: list[CollectionPeriod],
    stations_by_id: dict[str, StationInfo],
    filters: QueryFilters,
    metrics: list[str],
    group_by: str | None = None,
    top_n: int | None = None,
    max_gap_seconds: int = 360,
) -> QueryResult:
    """Filtre les relevés, détecte les interruptions et calcule les métriques par groupe."""
    validated_metrics = validate_metrics(metrics)

    if group_by is not None and group_by not in VALID_GROUP_BY:
        allowed = ", ".join(VALID_GROUP_BY)
        raise ConfigError(f"Regroupement invalide pour --by : '{group_by}'. Choix : {allowed}.")

    if top_n is not None and top_n <= 0:
        raise ConfigError("L'option --top doit être un entier strictement positif.")

    if not snapshots:
        raise NoQueryDataError(
            "Aucun historique n'a encore été collecté. Lancez d'abord 'velo collect'.",
            available_periods=[],
        )

    # Associe chaque horodatage à son numéro de période dans velo history
    ts_to_period: dict[datetime, int] = {}
    for period in periods:
        for ts in period.timestamps:
            ts_to_period[ts] = period.index

    selected_period_set = set(filters.period_ids) if filters.period_ids else None
    if selected_period_set is not None:
        known_period_ids = {p.index for p in periods}
        unknown = sorted(selected_period_set - known_period_ids)
        if unknown:
            unknown_str = ", ".join(str(x) for x in unknown)
            raise NoQueryDataError(
                f"Période(s) introuvable(s) : {unknown_str}.",
                available_periods=periods,
            )

    # Filtrage des relevés selon tous les critères fournis
    filtered: list[StationSnapshot] = []
    for snap in snapshots:
        local_dt = snap.timestamp.astimezone()

        if filters.date_only is not None and local_dt.date() != filters.date_only:
            continue
        if filters.dt_from is not None and local_dt < filters.dt_from:
            continue
        if filters.dt_to is not None and local_dt > filters.dt_to:
            continue
        if (
            selected_period_set is not None
            and ts_to_period.get(snap.timestamp) not in selected_period_set
        ):
            continue
        if filters.weekdays is not None and local_dt.weekday() not in filters.weekdays:
            continue
        if filters.hours_range is not None and not _matches_hours(local_dt, filters.hours_range):
            continue
        if filters.station_id is not None and snap.station_id != filters.station_id:
            continue

        filtered.append(snap)

    if not filtered:
        raise NoQueryDataError(
            "Aucune donnée disponible pour la sélection demandée.",
            available_periods=periods,
        )

    # Analyse de la continuité sur les relevés réellement retenus
    unique_ts = sorted({snap.timestamp for snap in filtered})
    used_periods = sorted({ts_to_period[ts] for ts in unique_ts if ts in ts_to_period})

    has_gap = any(
        (unique_ts[i] - unique_ts[i - 1]).total_seconds() > max_gap_seconds
        for i in range(1, len(unique_ts))
    )
    has_interruptions = len(used_periods) > 1 or has_gap

    # Regroupement des relevés selon l'axe demandé
    grouped: dict[object, list[StationSnapshot]] = defaultdict(list)
    for snap in filtered:
        local_dt = snap.timestamp.astimezone()
        if group_by == "station":
            key: object = snap.station_id
        elif group_by == "hour":
            key = local_dt.hour
        elif group_by == "weekday":
            key = local_dt.weekday()
        elif group_by == "day":
            key = local_dt.date()
        else:
            key = "__all__"
        grouped[key].append(snap)

    rows: list[QueryRow] = []
    for key, group_snaps in grouped.items():
        computed = compute_metrics(group_snaps, validated_metrics)
        # Nombre de relevés distincts (timestamps) utilisés pour ce groupe
        group_snapshot_count = len({s.timestamp for s in group_snaps})

        if group_by == "station":
            sid = str(key)
            info = stations_by_id.get(sid)
            label = f"{sid} {info.name}" if info is not None else sid
            sort_key: object = (
                -computed[validated_metrics[0]],
                natural_station_sort_key(sid),
            )
        elif group_by == "hour":
            hour_int = int(key)  # type: ignore[arg-type]
            label = f"{hour_int:02d}h"
            sort_key = hour_int
        elif group_by == "weekday":
            wd = int(key)  # type: ignore[arg-type]
            label = _WEEKDAY_LABELS[wd]
            sort_key = wd
        elif group_by == "day":
            day_obj = key
            assert isinstance(day_obj, date)
            label = day_obj.strftime("%d/%m/%Y")
            sort_key = day_obj
        else:
            if filters.station_id is not None:
                info = stations_by_id.get(filters.station_id)
                label = (
                    f"{filters.station_id} {info.name}"
                    if info is not None
                    else filters.station_id
                )
            else:
                label = "Réseau"
            sort_key = 0

        rows.append(
            QueryRow(
                label=label,
                metrics=computed,
                snapshot_count=group_snapshot_count,
                sort_key=sort_key,
            )
        )

    # Avec --top N, on classe toujours par la première métrique décroissante
    primary_metric = validated_metrics[0]
    if top_n is not None:
        rows.sort(key=lambda r: r.metrics[primary_metric], reverse=True)
        rows = rows[:top_n]
    else:
        rows.sort(key=lambda r: r.sort_key)  # type: ignore[arg-type, return-value]

    return QueryResult(
        rows=rows,
        used_periods=used_periods,
        snapshot_count=len(unique_ts),
        has_interruptions=has_interruptions,
        metrics=validated_metrics,
        group_by=group_by,
    )
