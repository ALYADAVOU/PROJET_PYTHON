"""Boucle de collecte périodique de l'état des stations vers les fichiers CSV."""

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from velo.collection.storage import append_snapshot
from velo.config import VeloConfig
from velo.gbfs import fetch_live_status
from velo.models import ConfigError, VeloError

logger = logging.getLogger(__name__)

# Reconnaît les durées de type "3h", "45m", "1h30m" ou "90s"
_DURATION_PATTERN = re.compile(
    r"^\s*(?:(?P<hours>\d+)h)?\s*(?:(?P<minutes>\d+)m)?\s*(?:(?P<seconds>\d+)s)?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CollectorSummary:
    """Résumé affiché à la fin d'une collecte."""

    saved_snapshots: int
    skipped_duplicates: int
    errors: int
    started_at: datetime
    ended_at: datetime


def parse_duration(raw: str) -> timedelta:
    """Transforme une durée texte (``3h``, ``30m``, ``1h30m``) en ``timedelta``."""
    if not raw or not raw.strip():
        raise ConfigError("La durée fournie à --duration ne peut pas être vide.")

    match = _DURATION_PATTERN.match(raw)
    if match is None:
        raise ConfigError(
            f"Format de durée invalide : {raw!r}. Exemples : '3h', '45m', '1h30m'."
        )

    total = timedelta(
        hours=int(match.group("hours") or 0),
        minutes=int(match.group("minutes") or 0),
        seconds=int(match.group("seconds") or 0),
    )
    if total.total_seconds() <= 0:
        raise ConfigError("La durée passée à --duration doit être supérieure à 0.")
    return total


def parse_until_datetime(raw: str) -> datetime:
    """Lit une date/heure de fin (ex: ``2026-11-18 19:00``)."""
    text = raw.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt).astimezone()
        except ValueError:
            continue
    raise ConfigError(
        f"Format invalide pour --until : {raw!r}. Format attendu : 'AAAA-MM-JJ HH:MM'."
    )


def collect_loop(
    config: VeloConfig,
    interval_seconds: int,
    duration: timedelta | None = None,
    until: datetime | None = None,
    once: bool = False,
    sleep_fn: Any = time.sleep,
    now_fn: Any = None,
) -> CollectorSummary:
    """Exécute la collecte à intervalle régulier jusqu'à la fin ou Ctrl+C."""
    get_now = now_fn if now_fn is not None else (lambda: datetime.now().astimezone())
    started_at = get_now()
    deadline = (started_at + duration) if duration is not None else until

    saved = 0
    duplicates = 0
    errors = 0
    last_updated_seen: datetime | None = None

    try:
        while True:
            if deadline is not None and get_now() > deadline:
                break

            try:
                snapshot = fetch_live_status(config.network.gbfs_url, config.network.name)

                # Si la date last_updated n'a pas changé, on n'enregistre pas un doublon
                if last_updated_seen is not None and snapshot.last_updated == last_updated_seen:
                    duplicates += 1
                else:
                    csv_path, count = append_snapshot(config.history_dir, snapshot)
                    last_updated_seen = snapshot.last_updated
                    saved += 1
                    logger.info("Relevé #%d (%d stations) -> %s", saved, count, csv_path.name)
            except VeloError as exc:
                # Une erreur réseau est notée dans le log, puis on réessaie au cycle suivant
                errors += 1
                logger.warning("Erreur réseau pendant la collecte : %s", exc)

            if once:
                break

            now = get_now()
            if deadline is not None and now >= deadline:
                break

            wait = float(interval_seconds)
            if deadline is not None:
                wait = min(wait, (deadline - now).total_seconds())
                if wait <= 0:
                    break
            sleep_fn(wait)
    except KeyboardInterrupt:
        logger.info("Collecte arrêtée par l'utilisateur (Ctrl+C).")

    return CollectorSummary(
        saved_snapshots=saved,
        skipped_duplicates=duplicates,
        errors=errors,
        started_at=started_at,
        ended_at=get_now(),
    )
