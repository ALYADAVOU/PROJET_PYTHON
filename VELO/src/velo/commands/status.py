"""Implémentation de la commande ``velo status``."""

from rich.console import Console

from velo.config import VeloConfig
from velo.gbfs import fetch_live_status
from velo.station_state import check_static_staleness, compute_network_stats


def run_status(config: VeloConfig) -> int:
    """Télécharge l'état temps réel et affiche le résumé global du réseau."""
    console = Console()

    # Signale si les fichiers qui changent rarement sont trop anciens
    staleness_warning = check_static_staleness(config)
    if staleness_warning is not None:
        console.print(f"[yellow]Avertissement :[/yellow] {staleness_warning}")

    snapshot = fetch_live_status(config.network.gbfs_url, config.network.name)
    stats = compute_network_stats(snapshot)

    console.print(f"[bold]{stats.network_name}[/bold] - données du {stats.last_updated_str}")
    console.print(
        f"Stations  en service {stats.in_service_count} / {stats.total_stations}   "
        f"hors service {stats.out_of_service_count}"
    )
    console.print(
        f"          vides {stats.empty_count:<14} pleines {stats.full_count}"
    )
    console.print(
        f"Vélos     disponibles {stats.total_bikes:<8} places libres {stats.total_docks}"
    )
    console.print(f"          taux de remplissage {stats.fill_rate_pct} %")
    return 0

