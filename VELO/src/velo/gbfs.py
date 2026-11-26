"""Seul module qui lit et décode le format GBFS (v2 et v3).

Rôle de ce fichier :
1. Lire ``gbfs.json`` pour découvrir les liens vers les autres fichiers de l'API.
2. Vérifier que les données reçues sont valides.
3. Convertir le JSON brut en objets simples définis dans ``models.py``.
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

# Noms des 3 fichiers statiques enregistrés localement dans le dossier du réseau
SYSTEM_INFO_FILENAME = "system_information.json"
STATION_INFO_FILENAME = "station_information.json"
VEHICLE_TYPES_FILENAME = "vehicle_types.json"


def _parse_timestamp(value: Any, field_name: str = "last_updated") -> datetime:
    """Convertit un horodatage GBFS (nombre Unix ou texte ISO) en heure locale."""
    # En GBFS v2, la date est un nombre de secondes depuis 1970
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, tz=UTC).astimezone()

    # En GBFS v3, la date est un texte ISO 8601 (ex: "2026-11-18T08:14:00+01:00")
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError as exc:
            raise GBFSError(f"Date GBFS invalide pour '{field_name}' : {value!r}.") from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone()

    raise GBFSError(f"Champ date manquant ou invalide : '{field_name}'.")


def _parse_bool(value: Any, field_name: str, default: bool = True) -> bool:
    """Convertit ``True/False`` ou ``1/0`` en booléen Python."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise GBFSError(f"Booléen invalide pour '{field_name}' : {value!r}.")


def _parse_int(value: Any, field_name: str) -> int:
    """Vérifie qu'une valeur est un entier positif ou nul (>= 0)."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GBFSError(f"Nombre >= 0 attendu pour '{field_name}', reçu : {value!r}.")
    return value


def _parse_name(value: Any, field_name: str) -> str:
    """Lit un texte simple (GBFS v2) ou une liste multilingue (GBFS v3)."""
    if isinstance(value, str):
        return value
    # En GBFS v3, un nom ressemble à [{"language": "fr", "text": "Gare"}]
    if isinstance(value, list) and value:
        for lang in ("fr", "en"):
            for item in value:
                if isinstance(item, dict) and item.get("language") == lang:
                    if isinstance(item.get("text"), str):
                        return item["text"]
        if isinstance(value[0], dict) and isinstance(value[0].get("text"), str):
            return value[0]["text"]
    raise GBFSError(f"Nom invalide pour '{field_name}' : {value!r}.")


def discover_feeds(gbfs_payload: dict[str, Any]) -> dict[str, str]:
    """Extrait les liens ``{nom_flux: url}`` depuis ``gbfs.json`` (v2 ou v3)."""
    data = gbfs_payload.get("data")
    if not isinstance(data, dict):
        raise GBFSError("Le fichier gbfs.json ne contient pas de bloc 'data' valide.")

    # Récupère la liste des flux selon la version GBFS
    feeds_list: Any = data.get("feeds")
    if feeds_list is None:
        # En GBFS v2, les flux sont rangés sous un code langue ("fr", "en"...)
        for lang in ("fr", "en", *data.keys()):
            block = data.get(lang)
            if isinstance(block, dict) and isinstance(block.get("feeds"), list):
                feeds_list = block["feeds"]
                break

    if not isinstance(feeds_list, list) or not feeds_list:
        raise GBFSError("Aucun flux trouvé dans gbfs.json.")

    feeds: dict[str, str] = {}
    for entry in feeds_list:
        if isinstance(entry, dict) and entry.get("name") and entry.get("url"):
            feeds[str(entry["name"])] = str(entry["url"])

    if not feeds:
        raise GBFSError("Liste des flux vide dans gbfs.json.")
    return feeds


def parse_system_information(payload: dict[str, Any]) -> SystemInfo:
    """Transforme le JSON ``system_information`` en objet ``SystemInfo``."""
    data = payload.get("data")
    if not isinstance(data, dict) or not data.get("system_id"):
        raise GBFSError("Données invalides dans system_information.")

    name = _parse_name(data.get("name"), "system_information.name").strip()
    last_updated = (
        _parse_timestamp(payload["last_updated"]) if "last_updated" in payload else None
    )
    return SystemInfo(
        system_id=str(data["system_id"]).strip(),
        name=name,
        language=data.get("language"),
        timezone=data.get("timezone"),
        url=data.get("url"),
        last_updated=last_updated,
    )


def parse_station_information(payload: dict[str, Any]) -> list[StationInfo]:
    """Transforme le JSON ``station_information`` en liste de ``StationInfo``."""
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("stations"), list):
        raise GBFSError("Liste 'data.stations' absente dans station_information.")

    stations: list[StationInfo] = []
    for raw in data["stations"]:
        if not isinstance(raw, dict) or raw.get("station_id") is None:
            raise GBFSError("Station invalide dans station_information.")

        sid = str(raw["station_id"]).strip()
        name = _parse_name(raw.get("name"), f"station({sid}).name").strip()
        lat, lon = raw.get("lat"), raw.get("lon")
        if isinstance(lat, bool) or not isinstance(lat, (int, float)):
            raise GBFSError(f"Latitude invalide pour la station {sid}.")
        if isinstance(lon, bool) or not isinstance(lon, (int, float)):
            raise GBFSError(f"Longitude invalide pour la station {sid}.")

        cap_raw = raw.get("capacity")
        capacity = _parse_int(cap_raw, f"station({sid}).capacity") if cap_raw is not None else None
        addr = raw.get("address")
        stations.append(
            StationInfo(
                station_id=sid,
                name=name,
                lat=float(lat),
                lon=float(lon),
                capacity=capacity,
                address=addr.strip() if isinstance(addr, str) else None,
            )
        )
    return stations


def parse_vehicle_types(payload: dict[str, Any]) -> list[VehicleType]:
    """Transforme le JSON ``vehicle_types`` en liste de ``VehicleType``."""
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("vehicle_types"), list):
        raise GBFSError("Liste 'data.vehicle_types' absente dans vehicle_types.")

    result: list[VehicleType] = []
    for raw in data["vehicle_types"]:
        if not isinstance(raw, dict) or not raw.get("vehicle_type_id"):
            raise GBFSError("Entrée invalide dans vehicle_types.")
        raw_name = raw.get("name")
        name = _parse_name(raw_name, "vehicle_type.name") if raw_name is not None else None
        result.append(
            VehicleType(
                vehicle_type_id=str(raw["vehicle_type_id"]).strip(),
                form_factor=str(raw.get("form_factor", "bicycle")),
                propulsion_type=str(raw.get("propulsion_type", "human")),
                name=name,
            )
        )
    return result


def parse_station_status(payload: dict[str, Any], network_name: str) -> NetworkSnapshot:
    """Transforme ``station_status`` en ``NetworkSnapshot`` utilisable par les commandes."""
    if "last_updated" not in payload:
        raise GBFSError("Champ 'last_updated' absent de station_status.")
    last_updated = _parse_timestamp(payload["last_updated"], "station_status.last_updated")

    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("stations"), list):
        raise GBFSError("Liste 'data.stations' absente dans station_status.")

    statuses: list[StationStatus] = []
    for raw in data["stations"]:
        if not isinstance(raw, dict) or raw.get("station_id") is None:
            raise GBFSError("Entrée invalide dans station_status.")
        sid = str(raw["station_id"]).strip()

        # GBFS v2 utilise num_bikes_available ; GBFS v3 utilise num_vehicles_available
        raw_bikes = raw.get("num_bikes_available", raw.get("num_vehicles_available"))
        bikes = _parse_int(raw_bikes, f"station({sid}).num_bikes_available")
        docks = _parse_int(raw.get("num_docks_available", 0), f"station({sid}).num_docks_available")

        last_rep = (
            _parse_timestamp(raw["last_reported"], f"station({sid}).last_reported")
            if raw.get("last_reported") is not None
            else None
        )
        statuses.append(
            StationStatus(
                station_id=sid,
                bikes_available=bikes,
                docks_available=docks,
                is_installed=_parse_bool(raw.get("is_installed"), "is_installed"),
                is_renting=_parse_bool(raw.get("is_renting"), "is_renting"),
                is_returning=_parse_bool(raw.get("is_returning"), "is_returning"),
                last_reported=last_rep,
            )
        )
    return NetworkSnapshot(network_name=network_name, last_updated=last_updated, statuses=statuses)


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    """Enregistre un dictionnaire JSON dans ``path`` (encodage UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fichier:
        json.dump(payload, fichier, ensure_ascii=False, indent=2)


def fetch_static_feeds(
    gbfs_url: str,
    network_dir: Path,
) -> tuple[SystemInfo, list[StationInfo], list[VehicleType]]:
    """Télécharge, vérifie et sauvegarde les 3 fichiers statiques du réseau."""
    feeds = discover_feeds(fetch_json(gbfs_url))
    for required in ("system_information", "station_information"):
        if required not in feeds:
            raise GBFSError(f"Le flux obligatoire '{required}' est absent de gbfs.json.")

    sys_payload = fetch_json(feeds["system_information"])
    system_info = parse_system_information(sys_payload)

    stations_payload = fetch_json(feeds["station_information"])
    stations = parse_station_information(stations_payload)

    # vehicle_types est parfois absent sur certains réseaux : on prévoit un repli vide
    if "vehicle_types" in feeds:
        vt_payload = fetch_json(feeds["vehicle_types"])
        vehicle_types = parse_vehicle_types(vt_payload)
    else:
        vt_payload = {"data": {"vehicle_types": []}}
        vehicle_types = []

    _save_json(network_dir / SYSTEM_INFO_FILENAME, sys_payload)
    _save_json(network_dir / STATION_INFO_FILENAME, stations_payload)
    _save_json(network_dir / VEHICLE_TYPES_FILENAME, vt_payload)
    logger.info("Fichiers statiques enregistrés dans %s (%d stations)", network_dir, len(stations))
    return system_info, stations, vehicle_types


def fetch_live_status(gbfs_url: str, network_name: str) -> NetworkSnapshot:
    """Télécharge et décode l'état temps réel des stations."""
    feeds = discover_feeds(fetch_json(gbfs_url))
    if "station_status" not in feeds:
        raise GBFSError("Le flux 'station_status' est absent de gbfs.json.")
    return parse_station_status(fetch_json(feeds["station_status"]), network_name=network_name)


def load_local_station_info(network_dir: Path) -> dict[str, StationInfo]:
    """Lit ``station_information.json`` sur le disque et renvoie ``{id: StationInfo}``."""
    path = network_dir / STATION_INFO_FILENAME
    if not path.exists():
        raise GBFSError(
            f"Données locales introuvables ({path}). Lancez 'velo init' ou 'velo refresh'."
        )
    try:
        with path.open("r", encoding="utf-8") as fichier:
            payload = json.load(fichier)
    except (OSError, ValueError) as exc:
        raise GBFSError(f"Impossible de lire '{path}' : {exc}") from exc
    return {st.station_id: st for st in parse_station_information(payload)}


def get_static_files_age_days(network_dir: Path) -> float | None:
    """Calcule l'âge en jours du fichier statique le plus ancien (ou None s'il manque)."""
    now_ts = datetime.now().timestamp()
    ages: list[float] = []
    for filename in (SYSTEM_INFO_FILENAME, STATION_INFO_FILENAME, VEHICLE_TYPES_FILENAME):
        file_path = network_dir / filename
        if not file_path.exists():
            return None
        ages.append(max(0.0, now_ts - file_path.stat().st_mtime) / 86400.0)
    return max(ages)
