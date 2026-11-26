"""Moteur de collecte périodique de l'état des stations vers des fichiers CSV."""

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from velo.collection.storage import append_snapshot
from velo.config import VeloConfig
from velo.gbfs import fetch_live_status
from velo.models import ConfigError, VeloError

logger = logging.getLogger(__name__)

# Expression régulière pour analyser une durée comme "3h", "30m", "1h30m" ou "90s"
_DURATION_PATTERN = re.compile(
    r"^\s*(?:(?P<hours>\d+)h)?\s*(?:(?P<minutes>\d+)m)?\s*(?:(?P<seconds>\d+)s)?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CollectorSummary:
    """Bilan affiché à la fin d'une session de collecte."""

    saved_snapshots: int
    skipped_duplicates: int
    errors: int
    started_at: datetime
    ended_at: datetime


def parse_duration(raw: str) -> timedelta:
    """Convertit une durée texte (ex: ``3h``, ``45m``, ``1h30m``) en ``timedelta``."""
    if not raw or not raw.strip():
        raise ConfigError("La durée fournie à --duration ne peut pas être vide.")

    match = _DURATION_PATTERN.match(raw)
    if match is None:
        raise ConfigError(
            f"Format de durée invalide pour --duration : {raw!r}. "
            "Exemples valides : '3h', '45m', '1h30m', '120s'."
        )

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    total = timedelta(hours=hours, minutes=minutes, seconds=seconds)

    if total.total_seconds() <= 0:
        raise ConfigError("La durée passée à --duration doit être strictement positive.")
    return total


def parse_until_datetime(raw: str) -> datetime:
    """Convertit une date/heure cible (``AAAA-MM-JJ HH:MM``) en ``datetime`` local."""
    text = raw.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            naive = datetime.strptime(text, fmt)
            return naive.astimezone()
        except ValueError:
            continue
    raise ConfigError(
        f"Format de date/heure invalide pour --until : {raw!r}. "
        "Format attendu : 'AAAA-MM-JJ HH:MM'."
    )


def collect_loop(
    config: VeloConfig,
    interval_seconds: int,
    duration: timedelta | None = None,
    until: datetime | None = None,
    once: bool = False,
    sleep_fn: Callable[[float], None] = time.sleep,
    now_fn: Callable[[], datetime] | None = None,
) -> CollectorSummary:
    """Exécute la boucle de collecte périodique jusqu'à la condition d'arrêt.

    - Ne ré-enregistre pas deux relevés consécutifs ayant le même ``last_updated``.
    - Journalise toute erreur réseau/GBFS et poursuit au cycle suivant.
    - Interrompt proprement sur ``Ctrl+C`` en renvoyant toujours un bilan complet.
    """
    current_time = now_fn if now_fn is not None else (lambda: datetime.now().astimezone())
    started_at = current_time()
    deadline: datetime | None = None

    if duration is not None:
        deadline = started_at + duration
    elif until is not None:
        deadline = until

    saved_snapshots = 0
    skipped_duplicates = 0
    errors = 0
    last_recorded_updated: datetime | None = None

    logger.info(
        "Démarrage de la collecte pour %s (intervalle=%ds)",
        config.network.name,
        interval_seconds,
    )

    try:
        while True:
            cycle_start = current_time()
            if deadline is not None and cycle_start > deadline:
                break

            try:
                snapshot = fetch_live_status(config.network.gbfs_url, config.network.name)

                # Déduplication : on ignore si le flux n'a pas changé depuis le dernier relevé
                if (
                    last_recorded_updated is not None
                    and snapshot.last_updated == last_recorded_updated
                ):
                    skipped_duplicates += 1
                    logger.info(
                        "Relevé ignoré (last_updated inchangé : %s)",
                        snapshot.last_updated.isoformat(),
                    )
                else:
                    csv_path, rows_written = append_snapshot(config.history_dir, snapshot)
                    last_recorded_updated = snapshot.last_updated
                    saved_snapshots += 1
                    logger.info(
                        "Relevé #%d enregistré (%d stations) dans %s",
                        saved_snapshots,
                        rows_written,
                        csv_path.name,
                    )
            except VeloError as exc:
                # Une erreur réseau ne doit jamais arrêter la collecte
                errors += 1
                logger.warning(
                    "Erreur lors de la collecte (nouvel essai au prochain cycle) : %s",
                    exc,
                )

            if once:
                break

            now_after = current_time()
            if deadline is not None and now_after >= deadline:
                break

            # Attente jusqu'au prochain relevé (sans dépasser l'échéance fixée)
            remaining_wait = float(interval_seconds)
            if deadline is not None:
                until_deadline = (deadline - now_after).total_seconds()
                if until_deadline <= 0:
                    break
                remaining_wait = min(remaining_wait, until_deadline)

            sleep_fn(remaining_wait)
    except KeyboardInterrupt:
        logger.info("Collecte interrompue par l'utilisateur (Ctrl+C).")

    ended_at = current_time()
    return CollectorSummary(
        saved_snapshots=saved_snapshots,
        skipped_duplicates=skipped_duplicates,
        errors=errors,
        started_at=started_at,
        ended_at=ended_at,
    )
