"""Implémentation de la commande ``velo query``."""

from rich.console import Console
from rich.table import Table

from velo.analysis.analysis import (
    NoQueryDataError,
    QueryFilters,
    parse_date_only,
    parse_datetime_bound,
    parse_days_filter,
    parse_hours_range,
    run_query_analysis,
)
from velo.analysis.metrics import format_metric_value
from velo.collection.storage import detect_periods, load_history_snapshots
from velo.commands.history import format_duration_hm
from velo.config import VeloConfig
from velo.gbfs import load_local_station_info
from velo.models import ConfigError, GBFSError


def run_query(
    config: VeloConfig,
    metrics: list[str],
    date_str: str | None = None,
    from_str: str | None = None,
    to_str: str | None = None,
    period_ids: list[int] | None = None,
    days_str: str | None = None,
    hours_str: str | None = None,
    station_id: str | None = None,
    group_by: str | None = None,
    top_n: int | None = None,
) -> int:
    """Exécute une requête analytique sur l'historique collecté."""
    console = Console()
    err_console = Console(stderr=True)

    if date_str is not None and (from_str is not None or to_str is not None):
        raise ConfigError("L'option --date ne peut pas être combinée avec --from ou --to.")

    date_only = parse_date_only(date_str) if date_str is not None else None
    dt_from = parse_datetime_bound(from_str, "--from", is_end=False) if from_str else None
    dt_to = parse_datetime_bound(to_str, "--to", is_end=True) if to_str else None

    if dt_from is not None and dt_to is not None and dt_from > dt_to:
        raise ConfigError("La borne --from doit être antérieure ou égale à --to.")

    weekdays = parse_days_filter(days_str) if days_str is not None else None
    hours_range = parse_hours_range(hours_str) if hours_str is not None else None

    filters = QueryFilters(
        date_only=date_only,
        dt_from=dt_from,
        dt_to=dt_to,
        period_ids=period_ids,
        weekdays=weekdays,
        hours_range=hours_range,
        station_id=station_id,
    )

    snapshots = load_history_snapshots(config.history_dir)
    max_gap_seconds = 3 * config.collect.interval_seconds
    periods = detect_periods(snapshots, max_gap_seconds=max_gap_seconds)

    # Si station_information.json n'est pas disponible, on conserve l'affichage par ID
    try:
        stations_by_id = load_local_station_info(config.network_dir)
    except GBFSError:
        stations_by_id = {}

    try:
        result = run_query_analysis(
            snapshots=snapshots,
            periods=periods,
            stations_by_id=stations_by_id,
            filters=filters,
            metrics=metrics,
            group_by=group_by,
            top_n=top_n,
            max_gap_seconds=max_gap_seconds,
        )
    except NoQueryDataError as exc:
        err_console.print(f"[red]Erreur :[/red] {exc}")
        if exc.available_periods:
            err_console.print("Périodes disponibles :")
            for period in exc.available_periods:
                err_console.print(
                    f"  #{period.index} : {period.start.strftime('%d/%m/%Y %H:%M')} -> "
                    f"{period.end.strftime('%d/%m/%Y %H:%M')} "
                    f"({format_duration_hm(period.duration_seconds)}, "
                    f"{period.snapshot_count} relevés)"
                )
        return 1

    periods_label = ", ".join(str(p) for p in result.used_periods) or "-"
    console.print(f"Données : périodes {periods_label} - {result.snapshot_count} relevés")

    if result.has_interruptions:
        console.print("[yellow]Avertissement :[/yellow] la sélection comporte des interruptions.")

    group_headers = {
        "station": "Station",
        "hour": "Heure",
        "weekday": "Jour",
        "day": "Date",
        None: "Cible",
    }
    table = Table(show_header=True, header_style="bold")
    table.add_column(group_headers[result.group_by])
    for metric_name in result.metrics:
        table.add_column(metric_name, justify="right")
    table.add_column("Relevés", justify="right")

    for row in result.rows:
        values = [format_metric_value(m, row.metrics[m]) for m in result.metrics]
        table.add_row(row.label, *values, str(row.snapshot_count))

    console.print(table)
    return 0
