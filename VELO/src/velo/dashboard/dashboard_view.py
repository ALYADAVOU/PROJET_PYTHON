"""Vue Rich du tableau de bord temps réel.

Ce module ne fait aucun calcul métier ni aucun appel réseau : il se contente
de mettre en forme les données préparées par ``station_state`` et ``favorites``.
"""

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from velo.commands.favorites import FavoriteStatusRow
from velo.station_state import AlertsSummary, NetworkStats


def render_dashboard(
    stats: NetworkStats | None,
    favorites_rows: list[FavoriteStatusRow],
    alerts: AlertsSummary | None,
    network_name: str,
    countdown_seconds: int,
    error_message: str | None = None,
    staleness_warning: str | None = None,
) -> Panel:
    """Construit le composant Rich complet du tableau de bord."""
    blocks: list[object] = []

    # 1. En-tête : réseau, horodatage des données et compte à rebours
    date_label = stats.last_updated_str if stats is not None else "en attente"
    header = Text()
    header.append(f"{network_name}", style="bold cyan")
    header.append(f"  |  Données du : {date_label}")
    header.append(f"  |  Prochaine mise à jour dans {countdown_seconds}s", style="dim")
    header.append("  (Ctrl+C pour quitter)", style="dim")
    blocks.append(header)

    if staleness_warning:
        blocks.append(Text(f"Avertissement : {staleness_warning}", style="yellow"))
    if error_message:
        blocks.append(
            Text(
                f"Erreur réseau : {error_message} (dernières données conservées)",
                style="bold red",
            )
        )

    # 2. Statistiques globales du réseau
    if stats is not None:
        stats_table = Table(show_header=False, box=None, padding=(0, 2))
        stats_table.add_column("Catégorie", style="bold")
        stats_table.add_column("Détails")
        stats_table.add_row(
            "Stations",
            f"en service {stats.in_service_count} / {stats.total_stations} | "
            f"hors service {stats.out_of_service_count} | "
            f"vides {stats.empty_count} | pleines {stats.full_count}",
        )
        stats_table.add_row(
            "Vélos",
            f"disponibles {stats.total_bikes} | places libres {stats.total_docks} | "
            f"taux de remplissage {stats.fill_rate_pct} %",
        )
        blocks.append(Panel(stats_table, title="État du réseau", border_style="green"))

    # 3. Stations favorites
    fav_table = Table(show_header=True, header_style="bold", expand=True)
    fav_table.add_column("ID", style="cyan", no_wrap=True)
    fav_table.add_column("Station")
    fav_table.add_column("Vélos", justify="right")
    fav_table.add_column("Places", justify="right")
    fav_table.add_column("État")

    if favorites_rows:
        for row in favorites_rows:
            bikes_str = str(row.bikes) if row.bikes is not None else "-"
            docks_str = str(row.docks) if row.docks is not None else "-"
            fav_table.add_row(row.station_id, row.name, bikes_str, docks_str, row.state_label)
    else:
        fav_table.add_row("-", "Aucune station favorite (velo favorites add <id>)", "-", "-", "")
    blocks.append(Panel(fav_table, title="Favoris", border_style="cyan"))

    # 4. Alertes du réseau (limitées à un aperçu lisible si la liste est longue)
    if alerts is not None:
        alerts_text = Text()
        if not (alerts.out_of_service or alerts.low_bikes_alerts or alerts.low_docks_alerts):
            alerts_text.append("Aucune alerte sur le réseau.", style="green")
        else:
            if alerts.out_of_service:
                preview = ", ".join(
                    f"{e.station_id} {e.name}" for e in alerts.out_of_service[:5]
                )
                suffix = " ..." if len(alerts.out_of_service) > 5 else ""
                alerts_text.append(
                    f"Hors service ({len(alerts.out_of_service)}) : {preview}{suffix}\n",
                    style="red",
                )
            if alerts.low_bikes_alerts:
                preview = ", ".join(
                    f"{e.station_id} {e.name} ({e.bikes})" for e in alerts.low_bikes_alerts[:5]
                )
                suffix = " ..." if len(alerts.low_bikes_alerts) > 5 else ""
                alerts_text.append(
                    f"Vide ou presque ({len(alerts.low_bikes_alerts)}) : {preview}{suffix}\n",
                    style="yellow",
                )
            if alerts.low_docks_alerts:
                preview = ", ".join(
                    f"{e.station_id} {e.name} ({e.docks})" for e in alerts.low_docks_alerts[:5]
                )
                suffix = " ..." if len(alerts.low_docks_alerts) > 5 else ""
                alerts_text.append(
                    f"Pleine ou presque ({len(alerts.low_docks_alerts)}) : {preview}{suffix}",
                    style="blue",
                )
        blocks.append(Panel(alerts_text, title="Alertes", border_style="yellow"))

    return Panel(Group(*blocks), title="Tableau de bord Vélo", border_style="bright_blue")

