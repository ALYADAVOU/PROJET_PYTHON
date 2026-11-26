"""Implémentation de la commande ``velo collect``."""

from rich.console import Console

from velo.collection.collector import (
    collect_loop,
    parse_duration,
    parse_until_datetime,
)
from velo.config import (
    DEFAULT_INTERVAL_SECONDS,
    MIN_INTERVAL_SECONDS,
    VeloConfig,
    resolve_option,
)
from velo.models import ConfigError


def run_collect(
    config: VeloConfig,
    interval_opt: int | None = None,
    duration_str: str | None = None,
    until_str: str | None = None,
    once: bool = False,
) -> int:
    """Lance la collecte périodique de l'historique puis affiche le bilan final."""
    console = Console()

    interval_seconds = resolve_option(
        interval_opt,
        config.collect.interval_seconds,
        DEFAULT_INTERVAL_SECONDS,
    )
    if interval_seconds < MIN_INTERVAL_SECONDS:
        raise ConfigError(
            f"L'intervalle de collecte ({interval_seconds}s) doit être "
            f"au moins égal à {MIN_INTERVAL_SECONDS} secondes."
        )

    duration = parse_duration(duration_str) if duration_str is not None else None
    until = parse_until_datetime(until_str) if until_str is not None else None

    if once:
        console.print(f"Collecte ponctuelle pour {config.network.name}...")
    else:
        console.print(
            f"Collecte démarrée pour {config.network.name} "
            f"(intervalle : {interval_seconds}s, Ctrl+C pour arrêter)..."
        )

    summary = collect_loop(
        config=config,
        interval_seconds=interval_seconds,
        duration=duration,
        until=until,
        once=once,
    )

    console.print("\n[bold]Bilan de la collecte[/bold]")
    console.print(f"Relevés enregistrés : {summary.saved_snapshots}")
    if summary.skipped_duplicates:
        console.print(f"Doublons ignorés    : {summary.skipped_duplicates}")
    if summary.errors:
        console.print(f"Erreurs réseau      : {summary.errors}")
    console.print(f"Début               : {summary.started_at.strftime('%d/%m/%Y à %H:%M:%S')}")
    console.print(f"Fin                 : {summary.ended_at.strftime('%d/%m/%Y à %H:%M:%S')}")
    return 0

