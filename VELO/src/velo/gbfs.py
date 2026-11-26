"""Module unique d'interaction et de décodage du format GBFS.

Conformément aux règles de conception du projet :
- aucune URL n'est écrite en dur ici : tout part de ``gbfs_url`` ;
- la structure brute GBFS est isolée dans ce module, qui renvoie uniquement
  des objets métier définis dans ``velo.models``.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from velo.models import (
    GBFSError,
    NetworkSnapshot,
    StationInfo,
    StationStatus,
    SystemInfo,
    VehicleType,
)
from velo.network import fetch_json

logger = logging.getLogger(__name__)

# Noms standard des fichiers JSON locaux sauvegardés dans le dossier du réseau
SYSTEM_INFO_FILENAME = "system_information.json"
STATION_INFO_FILENAME = "station_information.json"
VEHICLE_TYPES_FILENAME = "vehicle_types.json"


def _parse_timestamp(value: Any, field_name: str = "last_updated") -> datetime:
    """Convertit un horodatage GBFS (epoch Unix ou ISO 8601) en ``datetime`` local."""
    # Cas GBFS v2.x : entier ou flottant en secondes Unix UTC
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, tz=UTC).astimezone()

    # Cas GBFS v3.0 : chaîne ISO 8601 (ex: "2026-11-18T08:14:00+01:00" ou "...Z")
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError as exc:
            raise GBFSError(
                f"Horodatage GBFS invalide pour '{field_name}' : {value!r}."
            ) from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone()

    raise GBFSError(f"Champ horodatage GBFS manquant ou invalide : '{field_name}'.")


def _parse_bool(value: Any, field_name: str, default: bool | None = None) -> bool:
    """Convertit un booléen GBFS (``bool`` ou ``0``/``1``) en ``bool`` Python."""
    if value is None and default is not None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise GBFSError(f"Booléen GBFS invalide pour '{field_name}' : {value!r}.")


def _parse_non_negative_int(value: Any, field_name: str) -> int:
    """Valide et retourne un entier positif ou nul issu d'un flux GBFS."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GBFSError(f"Entier positif ou nul attendu pour '{field_name}', reçu : {value!r}.")
    return value


def _parse_localized_text(value: Any, field_name: str) -> str:
    """Extrait un texte lisible depuis une chaîne (v2) ou une liste localisée (v3)."""
    if isinstance(value, str):
        return value
    # En GBFS v3.0, certains noms sont une liste d'objets [{"text": "...", "language": "fr"}]
    if isinstance(value, list) and value:
        for preferred_lang in ("fr", "en"):
            for item in value:
                if isinstance(item, dict) and item.get("language") == preferred_lang:
                    text = item.get("text")
                    if isinstance(text, str):
                        return text
        first = value[0]
        if isinstance(first, dict) and isinstance(first.get("text"), str):
            return first["text"]
    raise GBFSError(f"Texte GBFS invalide pour '{field_name}' : {value!r}.")


def discover_feeds(gbfs_payload: dict[str, Any]) -> dict[str, str]:
    """Extrait la table ``{nom_du_flux: url}`` depuis le fichier racine ``gbfs.json``.

    Gère automatiquement :
    - GBFS v2.x : ``data.<langue>.feeds`` (priorité ``fr``, puis ``en``, puis première langue) ;
    - GBFS v3.0 : ``data.feeds``.
    """
    data = gbfs_payload.get("data")
    if not isinstance(data, dict):
        raise GBFSError("Le fichier gbfs.json ne contient pas de section 'data' valide.")

    feeds_list: Any = None
    if "feeds" in data:
        # Format GBFS v3.0
        feeds_list = data.get("feeds")
    else:
        # Format GBFS v2.x indexé par code de langue ("fr", "en", etc.)
        for lang in ("fr", "en"):
            lang_block = data.get(lang)
            if isinstance(lang_block, dict) and isinstance(lang_block.get("feeds"), list):
                feeds_list = lang_block["feeds"]
                break
        if feeds_list is None:
            for lang_block in data.values():
                if isinstance(lang_block, dict) and isinstance(lang_block.get("feeds"), list):
                    feeds_list = lang_block["feeds"]
                    break

    if not isinstance(feeds_list, list) or not feeds_list:
        raise GBFSError("Aucun flux ('feeds') trouvé dans gbfs.json.")

    feeds: dict[str, str] = {}
    for entry in feeds_list:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        url = entry.get("url")
        if isinstance(name, str) and name and isinstance(url, str) and url:
            feeds[name] = url

    if not feeds:
        raise GBFSError("La liste 'feeds' de gbfs.json ne contient aucune entrée valide.")

    return feeds


def parse_system_information(payload: dict[str, Any]) -> SystemInfo:
    """Valide et transforme ``system_information.json`` en ``SystemInfo``."""
    data = payload.get("data")
    if not isinstance(data, dict):
        raise GBFSError("Le flux system_information ne contient pas de bloc 'data' valide.")

    system_id = data.get("system_id")
    if not isinstance(system_id, str) or not system_id.strip():
        raise GBFSError("Champ 'system_id' manquant dans system_information.")

    raw_name = data.get("name")
    name = _parse_localized_text(raw_name, "system_information.name")

    # last_updated est au niveau racine dans la spécification GBFS
    last_updated = (
        _parse_timestamp(payload["last_updated"], "system_information.last_updated")
        if "last_updated" in payload
        else None
    )

    return SystemInfo(
        system_id=system_id.strip(),
        name=name.strip(),
        language=data.get("language") if isinstance(data.get("language"), str) else None,
        timezone=data.get("timezone") if isinstance(data.get("timezone"), str) else None,
        url=data.get("url") if isinstance(data.get("url"), str) else None,
        last_updated=last_updated,
    )


def parse_station_information(payload: dict[str, Any]) -> list[StationInfo]:
    """Valide et transforme ``station_information.json`` en liste de ``StationInfo``."""
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("stations"), list):
        raise GBFSError("Le flux station_information ne contient pas de liste 'data.stations'.")

    stations: list[StationInfo] = []
    for raw_station in data["stations"]:
        if not isinstance(raw_station, dict):
            raise GBFSError("Entrée de station invalide dans station_information.")

        station_id = raw_station.get("station_id")
        if station_id is None or str(station_id).strip() == "":
            raise GBFSError("Une station dans station_information n'a pas de 'station_id'.")

        name = _parse_localized_text(raw_station.get("name"), "station.name")

        lat = raw_station.get("lat")
        lon = raw_station.get("lon")
        if isinstance(lat, bool) or not isinstance(lat, (int, float)):
            raise GBFSError(f"Latitude invalide pour la station {station_id}.")
        if isinstance(lon, bool) or not isinstance(lon, (int, float)):
            raise GBFSError(f"Longitude invalide pour la station {station_id}.")

        capacity_raw = raw_station.get("capacity")
        capacity: int | None = None
        if capacity_raw is not None:
            capacity = _parse_non_negative_int(capacity_raw, f"station({station_id}).capacity")

        address_raw = raw_station.get("address")
        address = address_raw.strip() if isinstance(address_raw, str) else None

        stations.append(
            StationInfo(
                station_id=str(station_id).strip(),
                name=name.strip(),
                lat=float(lat),
                lon=float(lon),
                capacity=capacity,
                address=address,
            )
        )

    return stations


def parse_vehicle_types(payload: dict[str, Any]) -> list[VehicleType]:
    """Valide et transforme ``vehicle_types.json`` en liste de ``VehicleType``."""
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("vehicle_types"), list):
        raise GBFSError("Le flux vehicle_types ne contient pas de liste 'data.vehicle_types'.")

    vehicle_types: list[VehicleType] = []
    for raw_vt in data["vehicle_types"]:
        if not isinstance(raw_vt, dict):
            raise GBFSError("Entrée invalide dans vehicle_types.")

        vt_id = raw_vt.get("vehicle_type_id")
        if not isinstance(vt_id, str) or not vt_id.strip():
            raise GBFSError("Champ 'vehicle_type_id' manquant dans vehicle_types.")

        form_factor = str(raw_vt.get("form_factor", "bicycle"))
        propulsion = str(raw_vt.get("propulsion_type", "human"))
        raw_name = raw_vt.get("name")
        name = (
            _parse_localized_text(raw_name, "vehicle_type.name")
            if raw_name is not None
            else None
        )

        vehicle_types.append(
            VehicleType(
                vehicle_type_id=vt_id.strip(),
                form_factor=form_factor,
                propulsion_type=propulsion,
                name=name,
            )
        )

    return vehicle_types


def parse_station_status(payload: dict[str, Any], network_name: str) -> NetworkSnapshot:
    """Valide et transforme ``station_status.json`` en ``NetworkSnapshot``."""
    if "last_updated" not in payload:
        raise GBFSError("Le flux station_status ne contient pas 'last_updated'.")
    last_updated = _parse_timestamp(payload["last_updated"], "station_status.last_updated")

    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("stations"), list):
        raise GBFSError("Le flux station_status ne contient pas de liste 'data.stations'.")

    statuses: list[StationStatus] = []
    for raw_st in data["stations"]:
        if not isinstance(raw_st, dict):
            raise GBFSError("Entrée de station invalide dans station_status.")

        station_id = raw_st.get("station_id")
        if station_id is None or str(station_id).strip() == "":
            raise GBFSError("Une station dans station_status n'a pas de 'station_id'.")
        sid = str(station_id).strip()

        # GBFS v2 utilise num_bikes_available ; GBFS v3 utilise num_vehicles_available
        raw_bikes = raw_st.get("num_bikes_available", raw_st.get("num_vehicles_available"))
        raw_docks = raw_st.get("num_docks_available", 0)

        bikes = _parse_non_negative_int(raw_bikes, f"station({sid}).num_bikes_available")
        docks = _parse_non_negative_int(raw_docks, f"station({sid}).num_docks_available")

        # Par défaut en GBFS si non précisé, on considère True (sauf indication contraire)
        is_installed = _parse_bool(raw_st.get("is_installed"), f"station({sid}).is_installed", True)
        is_renting = _parse_bool(raw_st.get("is_renting"), f"station({sid}).is_renting", True)
        is_returning = _parse_bool(
            raw_st.get("is_returning"),
            f"station({sid}).is_returning",
            True,
        )

        last_reported = (
            _parse_timestamp(raw_st["last_reported"], f"station({sid}).last_reported")
            if raw_st.get("last_reported") is not None
            else None
        )

        statuses.append(
            StationStatus(
                station_id=sid,
                bikes_available=bikes,
                docks_available=docks,
                is_installed=is_installed,
                is_renting=is_renting,
                is_returning=is_returning,
                last_reported=last_reported,
            )
        )

    return NetworkSnapshot(
        network_name=network_name,
        last_updated=last_updated,
        statuses=statuses,
    )


def _save_json_file(path: Path, payload: dict[str, Any]) -> None:
    """Sauvegarde un dictionnaire JSON sur disque en UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _load_json_file(path: Path) -> dict[str, Any]:
    """Lit un fichier JSON local en UTF-8 et vérifie qu'il contient un objet."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise GBFSError(f"Impossible de lire le fichier local '{path}' : {exc}") from exc
    if not isinstance(data, dict):
        raise GBFSError(f"Le fichier '{path}' ne contient pas un objet JSON valide.")
    return data


def fetch_static_feeds(
    gbfs_url: str,
    network_dir: Path,
) -> tuple[SystemInfo, list[StationInfo], list[VehicleType]]:
    """Télécharge, valide et sauvegarde les trois fichiers qui changent rarement.

    Les fichiers enregistrés sont : ``system_information.json``,
    ``station_information.json`` et ``vehicle_types.json``.
    """
    logger.info("Découverte des flux GBFS depuis %s", gbfs_url)
    gbfs_payload = fetch_json(gbfs_url)
    feeds = discover_feeds(gbfs_payload)

    # Vérification de la présence des flux obligatoires
    for required_feed in ("system_information", "station_information"):
        if required_feed not in feeds:
            raise GBFSError(
                f"Le flux obligatoire '{required_feed}' est absent de gbfs.json."
            )

    sys_payload = fetch_json(feeds["system_information"])
    system_info = parse_system_information(sys_payload)

    stations_payload = fetch_json(feeds["station_information"])
    stations = parse_station_information(stations_payload)

    # vehicle_types est parfois absent sur certains réseaux GBFS : on gère un repli propre
    if "vehicle_types" in feeds:
        vt_payload = fetch_json(feeds["vehicle_types"])
        vehicle_types = parse_vehicle_types(vt_payload)
    else:
        logger.warning("Flux 'vehicle_types' absent de gbfs.json ; liste vide enregistrée.")
        vt_payload = {"data": {"vehicle_types": []}}
        vehicle_types = []

    # Sauvegarde sur disque uniquement après validation complète des données
    _save_json_file(network_dir / SYSTEM_INFO_FILENAME, sys_payload)
    _save_json_file(network_dir / STATION_INFO_FILENAME, stations_payload)
    _save_json_file(network_dir / VEHICLE_TYPES_FILENAME, vt_payload)

    logger.info(
        "Fichiers statiques mis à jour dans %s (%d stations)",
        network_dir,
        len(stations),
    )
    return system_info, stations, vehicle_types


def fetch_live_status(gbfs_url: str, network_name: str) -> NetworkSnapshot:
    """Télécharge et décode l'état temps réel des stations (``station_status``)."""
    gbfs_payload = fetch_json(gbfs_url)
    feeds = discover_feeds(gbfs_payload)

    if "station_status" not in feeds:
        raise GBFSError("Le flux 'station_status' est absent de gbfs.json.")

    status_payload = fetch_json(feeds["station_status"])
    return parse_station_status(status_payload, network_name=network_name)


def load_local_station_info(network_dir: Path) -> dict[str, StationInfo]:
    """Charge la table ``{station_id: StationInfo}`` depuis ``station_information.json``."""
    path = network_dir / STATION_INFO_FILENAME
    if not path.exists():
        raise GBFSError(
            f"Données locales des stations introuvables ({path}). "
            "Lancez 'velo init' ou 'velo refresh'."
        )
    payload = _load_json_file(path)
    stations = parse_station_information(payload)
    return {station.station_id: station for station in stations}


def load_local_system_info(network_dir: Path) -> SystemInfo | None:
    """Charge ``system_information.json`` s'il existe, ou retourne None."""
    path = network_dir / SYSTEM_INFO_FILENAME
    if not path.exists():
        return None
    payload = _load_json_file(path)
    return parse_system_information(payload)


def get_static_files_age_days(network_dir: Path) -> float | None:
    """Retourne l'âge en jours du fichier statique le plus ancien, ou None si manquant."""
    now_ts = datetime.now().timestamp()
    ages: list[float] = []

    for filename in (SYSTEM_INFO_FILENAME, STATION_INFO_FILENAME, VEHICLE_TYPES_FILENAME):
        file_path = network_dir / filename
        if not file_path.exists():
            return None
        age_seconds = max(0.0, now_ts - file_path.stat().st_mtime)
        ages.append(age_seconds / 86400.0)

    return max(ages) if ages else None
