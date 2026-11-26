"""Implémentation de la commande ``velo history [--from AAAA-MM-JJ] [--to AAAA-MM-JJ]``."""

from datetime import date

from rich.console import Console
from rich.table import Table

from velo.collection.storage import detect_periods, load_history_snapshots
from velo.config import VeloConfig
from velo.models import ConfigError


def _parse_date_arg(raw: str | None, option_name: str) -> date | None:
    """Parse une date ``AAAA-MM-JJ`` passée en option CLI."""
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ConfigError(
            f"Format de date invalide pour {option_name} : {raw!r}. Format attendu : AAAA-MM-JJ."
        ) from exc


def format_duration_hm(seconds: int) -> str:
    """Formate une durée en secondes sous la forme ``3 h 00``."""
    total_minutes = seconds // 60
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours} h {minutes:02d}"


def run_history(
    config: VeloConfig,
    from_str: str | None = None,
    to_str: str | None = None,
) -> int:
    """Affiche les périodes et le nombre de relevés enregistrés dans l'historique."""
    console = Console()
    date_from = _parse_date_arg(from_str, "--from")
    date_to = _parse_date_arg(to_str, "--to")

    if date_from is not None and date_to is not None and date_from > date_to:
        raise ConfigError("La date --from doit être antérieure ou égale à --to.")

    snapshots = load_history_snapshots(config.history_dir, date_from=date_from, date_to=date_to)
    if not snapshots:
        console.print(
            "Aucun historique disponible pour cette sélection.\n"
            "Lancez 'velo collect' pour enregistrer des relevés."
        )
        return 0

    # Seuil de continuité : 3 fois l'intervalle de collecte configuré
    max_gap_seconds = 3 * config.collect.interval_seconds
    periods = detect_periods(snapshots, max_gap_seconds=max_gap_seconds)
    total_snapshots = sum(p.snapshot_count for p in periods)

    console.print(
        f"[bold]Historique {config.network.name}[/bold] : "
        f"{len(periods)} période{'s' if len(periods) > 1 else ''}, {total_snapshots} relevés"
    )

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Début")
    table.add_column("Fin")
    table.add_column("Durée", justify="right")
    table.add_column("Relevés", justify="right")

    for period in periods:
        table.add_row(
            str(period.index),
            period.start.strftime("%d/%m/%Y %H:%M"),
            period.end.strftime("%d/%m/%Y %H:%M"),
            format_duration_hm(period.duration_seconds),
            str(period.snapshot_count),
        )

    console.print(table)
    return 0

