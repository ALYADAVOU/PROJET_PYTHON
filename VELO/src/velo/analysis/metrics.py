"""Calcul des métriques statistiques sur les relevés historiques.

Métriques supportées :
- ``avg_bikes`` : nombre moyen de vélos disponibles ;
- ``avg_docks`` : nombre moyen de places libres ;
- ``empty_rate`` : pourcentage de relevés où la station est en service et vide ;
- ``full_rate`` : pourcentage de relevés où la station est en service et pleine.
"""

from velo.models import ConfigError, StationSnapshot

VALID_METRICS = ("avg_bikes", "avg_docks", "empty_rate", "full_rate")


def is_snapshot_in_service(snap: StationSnapshot) -> bool:
    """Indique si la station était en service au moment du relevé."""
    return snap.is_installed and snap.is_renting and snap.is_returning


def validate_metrics(metrics: list[str]) -> list[str]:
    """Vérifie que toutes les métriques demandées sont reconnues et supprime les doublons."""
    if not metrics:
        raise ConfigError("Au moins une métrique doit être spécifiée avec --metric.")

    seen: list[str] = []
    for metric in metrics:
        if metric not in VALID_METRICS:
            allowed = ", ".join(VALID_METRICS)
            raise ConfigError(
                f"Métrique inconnue : '{metric}'. Métriques valides : {allowed}."
            )
        if metric not in seen:
            seen.append(metric)
    return seen


def compute_metrics(snapshots: list[StationSnapshot], metrics: list[str]) -> dict[str, float]:
    """Calcule les métriques demandées sur une liste non vide de ``StationSnapshot``."""
    validated = validate_metrics(metrics)
    count = len(snapshots)
    if count == 0:
        return {name: 0.0 for name in validated}

    results: dict[str, float] = {}
    for name in validated:
        if name == "avg_bikes":
            results[name] = sum(s.bikes for s in snapshots) / count
        elif name == "avg_docks":
            results[name] = sum(s.docks for s in snapshots) / count
        elif name == "empty_rate":
            # Une station hors service n'est pas comptée comme vide
            empty_count = sum(1 for s in snapshots if is_snapshot_in_service(s) and s.bikes == 0)
            results[name] = (empty_count / count) * 100.0
        elif name == "full_rate":
            # Une station hors service n'est pas comptée comme pleine
            full_count = sum(1 for s in snapshots if is_snapshot_in_service(s) and s.docks == 0)
            results[name] = (full_count / count) * 100.0

    return results


def format_metric_value(metric: str, value: float) -> str:
    """Formate proprement la valeur d'une métrique pour l'affichage terminal."""
    if metric in ("empty_rate", "full_rate"):
        return f"{round(value)} %"
    return f"{value:.1f}"

