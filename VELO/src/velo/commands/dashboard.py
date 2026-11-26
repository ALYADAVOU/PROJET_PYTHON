"""Implémentation de la commande ``velo dashboard [--refresh SECONDES]``."""

import logging
import time
from collections.abc import Callable

from rich.console import Console
from rich.live import Live

from velo.commands.favorites import FavoriteStatusRow, compute_favorites_rows, load_favorites
from velo.config import (
    DEFAULT_DASHBOARD_REFRESH_SECONDS,
    MIN_DASHBOARD_REFRESH_SECONDS,
    VeloConfig,
    resolve_option,
)
from velo.dashboard.dashboard_view import render_dashboard
from velo.gbfs import fetch_live_status, load_local_station_info
from velo.models import ConfigError, NetworkSnapshot, VeloError
from velo.station_state import (
    AlertsSummary,
    NetworkStats,
    check_static_staleness,
    compute_alerts,
    compute_network_stats,
)

logger = logging.getLogger(__name__)


def run_dashboard(
    config: VeloConfig,
    refresh_opt: int | None = None,
    max_cycles: int | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Lance le tableau de bord temps réel jusqu'à Ctrl+C (ou ``max_cycles``).

    Réutilise les fonctions de calcul de ``status``, ``favorites`` et ``alerts``.
    En cas d'erreur réseau lors d'un rafraîchissement, conserve les dernières
    données affichées et affiche un bandeau d'avertissement.
    """
    refresh_seconds = resolve_option(
        refresh_opt,
        config.dashboard.refresh_seconds,
        DEFAULT_DASHBOARD_REFRESH_SECONDS,
    )
    if refresh_seconds < MIN_DASHBOARD_REFRESH_SECONDS:
        raise ConfigError(
            f"L'intervalle de rafraîchissement ({refresh_seconds}s) doit être "
            f"au moins égal à {MIN_DASHBOARD_REFRESH_SECONDS} secondes."
        )

    console = Console()
    stations_by_id = load_local_station_info(config.network_dir)
    staleness_warning = check_static_staleness(config)

    last_snapshot: NetworkSnapshot | None = None
    last_stats: NetworkStats | None = None
    last_favs: list[FavoriteStatusRow] = []
    last_alerts: AlertsSummary | None = None
    error_message: str | None = None

    cycle = 0
    try:
        with Live(console=console, refresh_per_second=2) as live:
            while max_cycles is None or cycle < max_cycles:
                cycle += 1
                # Relit les favoris à chaque cycle pour refléter d'éventuelles modifications
                favorite_ids = load_favorites(config.favorites_path)

                try:
                    last_snapshot = fetch_live_status(
                        config.network.gbfs_url,
                        config.network.name,
                    )
                    last_stats = compute_network_stats(last_snapshot)
                    last_favs = compute_favorites_rows(
                        favorite_ids=favorite_ids,
                        snapshot=last_snapshot,
                        stations_by_id=stations_by_id,
                        low_bikes=config.alerts.low_bikes,
                        low_docks=config.alerts.low_docks,
                    )
                    last_alerts = compute_alerts(
                        snapshot=last_snapshot,
                        stations_by_id=stations_by_id,
                        low_bikes=config.alerts.low_bikes,
                        low_docks=config.alerts.low_docks,
                    )
                    error_message = None
                except VeloError as exc:
                    # Conserve les dernières données valides et avertit l'utilisateur
                    logger.warning("Échec de mise à jour du tableau de bord : %s", exc)
                    error_message = str(exc)

                # Si max_cycles est atteint (cas des tests), on affiche puis on quitte sans attendre
                if max_cycles is not None and cycle >= max_cycles:
                    live.update(
                        render_dashboard(
                            stats=last_stats,
                            favorites_rows=last_favs,
                            alerts=last_alerts,
                            network_name=config.network.name,
                            countdown_seconds=refresh_seconds,
                            error_message=error_message,
                            staleness_warning=staleness_warning,
                        )
                    )
                    break

                # Compte à rebours seconde par seconde jusqu'au prochain téléchargement
                for remaining in range(refresh_seconds, 0, -1):
                    live.update(
                        render_dashboard(
                            stats=last_stats,
                            favorites_rows=last_favs,
                            alerts=last_alerts,
                            network_name=config.network.name,
                            countdown_seconds=remaining,
                            error_message=error_message,
                            staleness_warning=staleness_warning,
                        )
                    )
                    sleep_fn(1.0)
    except KeyboardInterrupt:
        console.print("\nTableau de bord fermé.")

    return 0

