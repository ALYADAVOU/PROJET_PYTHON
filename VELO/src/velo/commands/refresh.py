"""Implémentation de la commande ``velo refresh``."""

import logging
from datetime import datetime

from rich.console import Console

from velo.config import VeloConfig
from velo.gbfs import fetch_static_feeds

logger = logging.getLogger(__name__)


def run_refresh(config: VeloConfig) -> int:
    """Retélécharge les trois fichiers statiques GBFS et affiche le bilan."""
    console = Console()
    _, stations, vehicle_types = fetch_static_feeds(config.network.gbfs_url, config.network_dir)

    now_str = datetime.now().astimezone().strftime("%d/%m/%Y à %H:%M")
    logger.info("Données statiques rafraîchies (%d stations)", len(stations))
    console.print(
        f"{config.network.name} - données statiques mises à jour le {now_str} "
        f"({len(stations)} stations, {len(vehicle_types)} types de vélos)"
    )
    return 0

