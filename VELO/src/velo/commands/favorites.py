"""Implémentation de la commande ``velo favorites`` (affichage, ajout, retrait)."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from velo.config import MAX_FAVORITES, VeloConfig
from velo.gbfs import fetch_live_status, load_local_station_info
from velo.models import DataError, NetworkSnapshot, StationInfo
from velo.station_state import check_static_staleness, classify_station_state

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FavoriteStatusRow:
    """Ligne prête à afficher pour une station favorite."""

    station_id: str
    name: str
    bikes: int | None
    docks: int | None
    state_label: str


def load_favorites(favorites_path: Path) -> list[str]:
    """Charge la liste des identifiants favoris depuis ``favorites.json``."""
    if not favorites_path.exists():
        return []
    try:
        with favorites_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise DataError(f"Impossible de lire les favoris ({favorites_path}) : {exc}") from exc

    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise DataError(f"Format invalide dans le fichier des favoris ({favorites_path}).")

    return data


def save_favorites(favorites_path: Path, favorite_ids: list[str]) -> None:
    """Enregistre la liste des identifiants favoris dans un fichier dédié."""
    favorites_path.parent.mkdir(parents=True, exist_ok=True)
    with favorites_path.open("w", encoding="utf-8") as handle:
        json.dump(favorite_ids, handle, ensure_ascii=False, indent=2)


def compute_favorites_rows(
    favorite_ids: list[str],
    snapshot: NetworkSnapshot,
    stations_by_id: dict[str, StationInfo],
    low_bikes: int,
    low_docks: int,
) -> list[FavoriteStatusRow]:
    """Construit l'état courant des stations favorites (réutilisé par le dashboard)."""
    status_by_id = {st.station_id: st for st in snapshot.statuses}
    rows: list[FavoriteStatusRow] = []

    for sid in favorite_ids:
        info = stations_by_id.get(sid)
        name = info.name if info is not None else f"Station {sid}"
        status = status_by_id.get(sid)

        if status is None:
            rows.append(
                FavoriteStatusRow(
                    station_id=sid,
                    name=name,
                    bikes=None,
                    docks=None,
                    state_label="indisponible",
                )
            )
            continue

        state_label = classify_station_state(status, low_bikes=low_bikes, low_docks=low_docks)
        # On affiche une annotation d'état uniquement quand la station est notable
        display_state = "" if state_label == "disponible" else state_label
        rows.append(
            FavoriteStatusRow(
                station_id=sid,
                name=name,
                bikes=status.bikes_available,
                docks=status.docks_available,
                state_label=display_state,
            )
        )

    return rows


def run_favorites_list(config: VeloConfig) -> int:
    """Affiche l'état temps réel des stations favorites ou explique comment en ajouter."""
    console = Console()
    favorite_ids = load_favorites(config.favorites_path)

    if not favorite_ids:
        console.print(
            "Aucune station favorite enregistrée.\n"
            "Cherchez une station avec 'velo station search <texte>', "
            "puis ajoutez-la avec 'velo favorites add <id>'."
        )
        return 0

    staleness_warning = check_static_staleness(config)
    if staleness_warning is not None:
        console.print(f"[yellow]Avertissement :[/yellow] {staleness_warning}")

    stations_by_id = load_local_station_info(config.network_dir)
    snapshot = fetch_live_status(config.network.gbfs_url, config.network.name)
    rows = compute_favorites_rows(
        favorite_ids=favorite_ids,
        snapshot=snapshot,
        stations_by_id=stations_by_id,
        low_bikes=config.alerts.low_bikes,
        low_docks=config.alerts.low_docks,
    )

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Station")
    table.add_column("Vélos", justify="right")
    table.add_column("Places", justify="right")
    table.add_column("État")

    for row in rows:
        bikes_str = str(row.bikes) if row.bikes is not None else "-"
        docks_str = str(row.docks) if row.docks is not None else "-"
        table.add_row(row.station_id, row.name, bikes_str, docks_str, row.state_label)

    console.print(table)
    return 0


def run_favorites_add(config: VeloConfig, station_id: str) -> int:
    """Ajoute une station aux favoris après validation de l'ID et de la limite de 10."""
    console = Console()
    stations_by_id = load_local_station_info(config.network_dir)

    if station_id not in stations_by_id:
        raise DataError(
            f"Identifiant de station inconnu : '{station_id}'. "
            "Trouvez l'identifiant avec 'velo station search <texte>'."
        )

    favorite_ids = load_favorites(config.favorites_path)
    if station_id in favorite_ids:
        raise DataError(f"La station {station_id} est déjà dans vos favoris.")

    if len(favorite_ids) >= MAX_FAVORITES:
        raise DataError(
            f"La liste des favoris est pleine ({MAX_FAVORITES} stations maximum). "
            "Retirez d'abord un favori avec 'velo favorites remove <id>'."
        )

    favorite_ids.append(station_id)
    save_favorites(config.favorites_path, favorite_ids)
    station_name = stations_by_id[station_id].name
    logger.info("Favori ajouté : %s (%s)", station_id, station_name)
    console.print(f"Station ajoutée aux favoris : {station_id} - {station_name}")
    return 0


def run_favorites_remove(config: VeloConfig, station_id: str) -> int:
    """Retire une station de la liste des favoris."""
    console = Console()
    favorite_ids = load_favorites(config.favorites_path)

    if station_id not in favorite_ids:
        raise DataError(f"La station '{station_id}' n'est pas dans vos favoris.")

    updated = [sid for sid in favorite_ids if sid != station_id]
    save_favorites(config.favorites_path, updated)
    logger.info("Favori retiré : %s", station_id)
    console.print(f"Station retirée des favoris : {station_id}")
    return 0

