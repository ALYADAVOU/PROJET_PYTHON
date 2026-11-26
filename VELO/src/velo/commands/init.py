"""Implémentation de la commande ``velo init [--force]``."""

import logging
from pathlib import Path

from rich.console import Console

from velo.config import (
    build_default_config,
    get_config_path,
    load_config,
    save_config,
)
from velo.gbfs import fetch_static_feeds
from velo.logging_config import setup_logging
from velo.models import VeloError

logger = logging.getLogger(__name__)


def run_init(
    force: bool = False,
    config_path: Path | None = None,
    data_folder: Path | None = None,
) -> int:
    """Initialise la configuration, le dossier de données et teste la connexion GBFS.

    Si ``config.yaml`` existe déjà et que ``--force`` n'est pas fourni, le fichier
    n'est pas écrasé. Si la connexion au flux GBFS échoue, la configuration et les
    dossiers sont tout de même créés et un avertissement est affiché.
    """
    console = Console()
    target_config_path = config_path if config_path is not None else get_config_path()

    # Étape 1 : création (ou conservation) du fichier config.yaml
    if target_config_path.exists() and not force:
        console.print(
            f"[yellow]Configuration déjà existante :[/yellow] {target_config_path} "
            "(conservée, utilisez --force pour la réinitialiser)"
        )
        config = load_config(target_config_path)
    else:
        config = build_default_config(data_folder=data_folder)
        save_config(config, target_config_path)
        console.print(f"Configuration créée : {target_config_path}")

    # Étape 2 : création des dossiers de données du réseau et de l'historique
    config.data.folder.mkdir(parents=True, exist_ok=True)
    config.network_dir.mkdir(parents=True, exist_ok=True)
    config.history_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"Dossier de données créé : {config.data.folder}")

    # Active la journalisation dès que le dossier de données est prêt
    setup_logging(config.logging.level, config.log_file)
    logger.info(
        "Initialisation effectuée (config=%s, data=%s)",
        target_config_path,
        config.data.folder,
    )

    # Étape 3 : vérification de la connexion avec le réseau GBFS configuré
    try:
        _, stations, _ = fetch_static_feeds(config.network.gbfs_url, config.network_dir)
    except VeloError as exc:
        # Conformément au cahier des charges : on avertit sans faire échouer init
        logger.warning("Échec de la connexion initiale à %s : %s", config.network.name, exc)
        console.print(
            f"[yellow]Avertissement :[/yellow] connexion à {config.network.name} impossible "
            f"pour le moment ({exc}). Les dossiers et la configuration ont bien été créés."
        )
        return 0

    console.print(f"Connexion à {config.network.name} : OK ({len(stations)} stations)")
    return 0
