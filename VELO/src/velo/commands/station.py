"""Implémentation de la commande ``velo station`` (search, list, show)."""

from rich.console import Console
from rich.table import Table

from velo.config import VeloConfig
from velo.gbfs import fetch_live_status, load_local_station_info
from velo.models import DataError
from velo.station_state import (
    classify_station_state,
    natural_station_sort_key,
    search_stations,
)


def run_station_search(config: VeloConfig, query: str) -> int:
    """Cherche les stations dont le nom correspond à l'expression régulière ``query``."""
    console = Console()
    stations_by_id = load_local_station_info(config.network_dir)
    matches = search_stations(stations_by_id.values(), query)

    if not matches:
        console.print(f"Aucune station trouvée pour le motif '{query}'.")
        return 0

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Station")
    for station in matches:
        table.add_row(station.station_id, station.name)

    console.print(table)
    return 0


def run_station_list(config: VeloConfig) -> int:
    """Liste toutes les stations connues du réseau avec leur identifiant."""
    console = Console()
    stations_by_id = load_local_station_info(config.network_dir)
    ordered = sorted(
        stations_by_id.values(),
        key=lambda st: natural_station_sort_key(st.station_id),
    )

    table = Table(title=f"Stations {config.network.name} ({len(ordered)})", header_style="bold")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Station")
    table.add_column("Capacité", justify="right")

    for station in ordered:
        cap = str(station.capacity) if station.capacity is not None else "-"
        table.add_row(station.station_id, station.name, cap)

    console.print(table)
    return 0


def run_station_show(config: VeloConfig, station_id: str) -> int:
    """Affiche les informations détaillées et l'état temps réel d'une station."""
    console = Console()
    stations_by_id = load_local_station_info(config.network_dir)
    station = stations_by_id.get(station_id)
    if station is None:
        raise DataError(f"Station inconnue : '{station_id}'. Utilisez 'velo station search'.")

    snapshot = fetch_live_status(config.network.gbfs_url, config.network.name)
    status_by_id = {st.station_id: st for st in snapshot.statuses}
    status = status_by_id.get(station_id)

    console.print(f"[bold]{station.station_id} - {station.name}[/bold]")
    if station.address:
        console.print(f"Adresse   : {station.address}")
    console.print(f"Position  : {station.lat:.5f}, {station.lon:.5f}")
    if station.capacity is not None:
        console.print(f"Capacité  : {station.capacity}")

    if status is None:
        console.print("[yellow]Aucun état temps réel disponible pour cette station.[/yellow]")
        return 0

    state_label = classify_station_state(
        status,
        low_bikes=config.alerts.low_bikes,
        low_docks=config.alerts.low_docks,
    )
    console.print(f"État      : {state_label}")
    console.print(f"Vélos     : {status.bikes_available}")
    console.print(f"Places    : {status.docks_available}")
    if status.last_reported is not None:
        console.print(f"Signalé à : {status.last_reported.strftime('%d/%m/%Y à %H:%M')}")
    return 0
