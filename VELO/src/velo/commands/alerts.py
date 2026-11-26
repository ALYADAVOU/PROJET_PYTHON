"""Implémentation de la commande ``velo alerts [--low-bikes N] [--low-docks N]``."""

from rich.console import Console

from velo.config import DEFAULT_LOW_BIKES, DEFAULT_LOW_DOCKS, VeloConfig, resolve_option
from velo.gbfs import fetch_live_status, load_local_station_info
from velo.models import ConfigError
from velo.station_state import check_static_staleness, compute_alerts


def run_alerts(
    config: VeloConfig,
    low_bikes_opt: int | None = None,
    low_docks_opt: int | None = None,
) -> int:
    """Affiche les stations hors service, vides/presque vides et pleines/presque pleines."""
    console = Console()

    # Validation des éventuels remplacements passés en ligne de commande
    if low_bikes_opt is not None and low_bikes_opt < 0:
        raise ConfigError("L'option --low-bikes doit être un entier positif ou nul.")
    if low_docks_opt is not None and low_docks_opt < 0:
        raise ConfigError("L'option --low-docks doit être un entier positif ou nul.")

    low_bikes = resolve_option(low_bikes_opt, config.alerts.low_bikes, DEFAULT_LOW_BIKES)
    low_docks = resolve_option(low_docks_opt, config.alerts.low_docks, DEFAULT_LOW_DOCKS)

    staleness_warning = check_static_staleness(config)
    if staleness_warning is not None:
        console.print(f"[yellow]Avertissement :[/yellow] {staleness_warning}")

    stations_by_id = load_local_station_info(config.network_dir)
    snapshot = fetch_live_status(config.network.gbfs_url, config.network.name)
    summary = compute_alerts(
        snapshot=snapshot,
        stations_by_id=stations_by_id,
        low_bikes=low_bikes,
        low_docks=low_docks,
    )

    console.print(f"[bold]{summary.network_name}[/bold] - alertes du {summary.last_updated_str}")

    if not (summary.out_of_service or summary.low_bikes_alerts or summary.low_docks_alerts):
        console.print("Aucune alerte détectée sur le réseau.")
        return 0

    if summary.out_of_service:
        items = ", ".join(f"{e.station_id} {e.name}" for e in summary.out_of_service)
        console.print(f"[red]Hors service ({len(summary.out_of_service)})[/red]   {items}")

    if summary.low_bikes_alerts:
        items = ", ".join(f"{e.station_id} {e.name} ({e.bikes})" for e in summary.low_bikes_alerts)
        console.print(
            f"[yellow]Vide ou presque ({len(summary.low_bikes_alerts)})[/yellow]   {items}"
        )

    if summary.low_docks_alerts:
        items = ", ".join(
            f"{e.station_id} {e.name} ({e.docks} place{'s' if e.docks > 1 else ''})"
            for e in summary.low_docks_alerts
        )
        console.print(
            f"[blue]Pleine ou presque ({len(summary.low_docks_alerts)})[/blue]   {items}"
        )

    return 0

