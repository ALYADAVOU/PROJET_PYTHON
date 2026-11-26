"""Filtrage, regroupement et classement des données pour ``velo query``.

Étapes réalisées par ce module :
1. Convertir les options de dates, jours et heures saisies par l'utilisateur.
2. Filtrer les relevés CSV qui correspondent à la sélection demandée.
3. Regrouper les relevés (par station, heure, jour de semaine ou date).
4. Calculer les métriques et trier le résultat (avec ``--top`` si demandé).
"""

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

# Associe les noms de jours (français ou anglais) au numéro Python (0 = lundi, 6 = dimanche)
_DAY_NUMBERS: dict[str, int] = {
    "lun": 0, "lundi": 0, "mon": 0, "monday": 0,
    "mar": 1, "mardi": 1, "tue": 1, "tuesday": 1,
    "mer": 2, "mercredi": 2, "wed": 2, "wednesday": 2,
    "jeu": 3, "jeudi": 3, "thu": 3, "thursday": 3,
    "ven": 4, "vendredi": 4, "fri": 4, "friday": 4,
    "sam": 5, "samedi": 5, "sat": 5, "saturday": 5,
    "dim": 6, "dimanche": 6, "sun": 6, "sunday": 6,
}

_WEEKDAY_LABELS = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")


class NoQueryDataError(DataError):
    """Erreur levée quand aucun relevé ne correspond aux filtres de ``velo query``."""

    def __init__(self, message: str, available_periods: list[CollectionPeriod]) -> None:
        super().__init__(message)
        # On garde la liste des périodes existantes pour l'afficher à l'utilisateur
        self.available_periods = available_periods


@dataclass(frozen=True)
class QueryFilters:
    """Critères de filtrage choisis par l'utilisateur dans ``velo query``."""

    date_only: date | None = None
    dt_from: datetime | None = None
    dt_to: datetime | None = None
    period_ids: list[int] | None = None
    weekdays: set[int] | None = None
    hours_range: tuple[int, int] | None = None
    station_id: str | None = None


@dataclass(frozen=True)
class QueryRow:
    """Une ligne finale du tableau affiché par ``velo query``."""

    label: str
    metrics: dict[str, float]
    snapshot_count: int


@dataclass(frozen=True)
class QueryResult:
    """Résultat complet d'une requête sur l'historique."""

    rows: list[QueryRow]
    used_periods: list[int]
    snapshot_count: int
    has_interruptions: bool
    metrics: list[str]
    group_by: str | None


def parse_date_only(raw: str) -> date:
    """Lit une date au format ``AAAA-MM-JJ``."""
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"Date invalide pour --date : {raw!r} (attendu AAAA-MM-JJ).") from exc


def parse_datetime_bound(raw: str, option_name: str, is_end: bool = False) -> datetime:
    """Lit une borne ``AAAA-MM-JJ`` ou ``AAAA-MM-JJ HH:MM``."""
    text = raw.strip()
    try:
        d = date.fromisoformat(text)
        # Sans heure précisée : début de journée (00:00) ou fin de journée (23:59:59)
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
        f"Format invalide pour {option_name} : {raw!r} (ex: '2026-11-18' ou '2026-11-18 08:00')."
    )


def parse_days_filter(raw: str) -> set[int]:
    """Convertit ``weekdays``, ``weekend`` ou ``lundi,mardi`` en numéros de jours."""
    cleaned = raw.strip().lower()
    if cleaned == "weekdays":
        return {0, 1, 2, 3, 4}
    if cleaned == "weekend":
        return {5, 6}

    days: set[int] = set()
    for mot in cleaned.split(","):
        mot = mot.strip()
        if not mot:
            continue
        if mot not in _DAY_NUMBERS:
            raise ConfigError(
                f"Jour inconnu dans --days : {mot!r} (ex: weekdays, weekend, lundi,mardi)."
            )
        days.add(_DAY_NUMBERS[mot])

    if not days:
        raise ConfigError("L'option --days ne peut pas être vide.")
    return days


def parse_hours_range(raw: str) -> tuple[int, int]:
    """Lit une plage horaire comme ``7-9``."""
    parts = raw.strip().split("-")
    if len(parts) != 2:
        raise ConfigError(f"Format invalide pour --hours : {raw!r} (attendu DEBUT-FIN, ex: 7-9).")
    try:
        start_h, end_h = int(parts[0].strip()), int(parts[1].strip())
    except ValueError as exc:
        raise ConfigError(f"Heures invalides dans --hours : {raw!r}.") from exc

    if not (0 <= start_h <= 23 and 0 <= end_h <= 24) or start_h > end_h:
        raise ConfigError(f"Plage horaire invalide pour --hours : {raw!r}.")
    return start_h, end_h


def _matches_hours(dt: datetime, hours_range: tuple[int, int]) -> bool:
    """Vérifie si l'heure locale de ``dt`` est dans la plage (ex: ``7-9`` -> 7h et 8h)."""
    hour = dt.astimezone().hour
    start_h, end_h = hours_range
    if start_h == end_h:
        return hour == start_h
    return start_h <= hour < end_h


def _build_row_label(
    key: str | int | date,
    group_by: str | None,
    stations_by_id: dict[str, StationInfo],
    station_filter: str | None,
) -> str:
    """Fabrique le texte affiché dans la première colonne du tableau."""
    if group_by == "station":
        sid = str(key)
        info = stations_by_id.get(sid)
        return f"{sid} {info.name}" if info is not None else sid
    if group_by == "hour":
        return f"{int(key):02d}h"  # type: ignore[arg-type]
    if group_by == "weekday":
        return _WEEKDAY_LABELS[int(key)]  # type: ignore[arg-type]
    if group_by == "day" and isinstance(key, date):
        return key.strftime("%d/%m/%Y")
    if station_filter is not None:
        info = stations_by_id.get(station_filter)
        return f"{station_filter} {info.name}" if info is not None else station_filter
    return "Réseau"


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
    """Filtre les relevés, regroupe les données et calcule les métriques demandées."""
    validated_metrics = validate_metrics(metrics)
    if group_by is not None and group_by not in VALID_GROUP_BY:
        raise ConfigError(f"Option --by invalide : '{group_by}'.")
    if top_n is not None and top_n <= 0:
        raise ConfigError("L'option --top doit être un entier positif.")
    if not snapshots:
        raise NoQueryDataError("Aucun historique disponible. Lancez 'velo collect'.", [])

    # Associe chaque horodatage à son numéro de période dans velo history
    ts_to_period: dict[datetime, int] = {}
    for period in periods:
        for ts in period.timestamps:
            ts_to_period[ts] = period.index

    if filters.period_ids:
        unknown = sorted(set(filters.period_ids) - {p.index for p in periods})
        if unknown:
            raise NoQueryDataError(f"Période(s) introuvable(s) : {unknown}.", periods)

    # 1. Filtrage des relevés
    filtered: list[StationSnapshot] = []
    for snap in snapshots:
        local_dt = snap.timestamp.astimezone()
        if filters.date_only is not None and local_dt.date() != filters.date_only:
            continue
        if filters.dt_from is not None and local_dt < filters.dt_from:
            continue
        if filters.dt_to is not None and local_dt > filters.dt_to:
            continue
        if filters.period_ids and ts_to_period.get(snap.timestamp) not in filters.period_ids:
            continue
        if filters.weekdays is not None and local_dt.weekday() not in filters.weekdays:
            continue
        if filters.hours_range is not None and not _matches_hours(local_dt, filters.hours_range):
            continue
        if filters.station_id is not None and snap.station_id != filters.station_id:
            continue
        filtered.append(snap)

    if not filtered:
        raise NoQueryDataError("Aucune donnée disponible pour cette sélection.", periods)

    # 2. Vérifie si la sélection comporte des trous / plusieurs périodes
    unique_ts = sorted({s.timestamp for s in filtered})
    used_periods = sorted({ts_to_period[ts] for ts in unique_ts if ts in ts_to_period})
    has_gap = any(
        (unique_ts[i] - unique_ts[i - 1]).total_seconds() > max_gap_seconds
        for i in range(1, len(unique_ts))
    )

    # 3. Regroupement des relevés dans un dictionnaire simple
    groups: dict[str | int | date, list[StationSnapshot]] = {}
    for snap in filtered:
        local_dt = snap.timestamp.astimezone()
        if group_by == "station":
            key: str | int | date = snap.station_id
        elif group_by == "hour":
            key = local_dt.hour
        elif group_by == "weekday":
            key = local_dt.weekday()
        elif group_by == "day":
            key = local_dt.date()
        else:
            key = "all"
        groups.setdefault(key, []).append(snap)

    # 4. Calcul des métriques pour chaque groupe puis tri
    primary_metric = validated_metrics[0]
    items_with_key: list[tuple[str | int | date, QueryRow]] = []
    for key, group_snaps in groups.items():
        row = QueryRow(
            label=_build_row_label(key, group_by, stations_by_id, filters.station_id),
            metrics=compute_metrics(group_snaps, validated_metrics),
            snapshot_count=len({s.timestamp for s in group_snaps}),
        )
        items_with_key.append((key, row))

    if top_n is not None or group_by == "station":
        items_with_key.sort(
            key=lambda item: (
                -item[1].metrics[primary_metric],
                natural_station_sort_key(str(item[0])),
            )
        )
    else:
        items_with_key.sort(key=lambda item: str(item[0]))

    rows = [item[1] for item in items_with_key]
    if top_n is not None:
        rows = rows[:top_n]

    return QueryResult(
        rows=rows,
        used_periods=used_periods,
        snapshot_count=len(unique_ts),
        has_interruptions=len(used_periods) > 1 or has_gap,
        metrics=validated_metrics,
        group_by=group_by,
    )
