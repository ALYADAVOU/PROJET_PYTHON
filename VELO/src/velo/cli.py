"""Point d'entrée en ligne de commande (CLI) de l'outil Vélo.

Utilise ``argparse`` pour analyser les commandes et options, charge et valide
``config.yaml`` avant d'exécuter les commandes, et intercepte les erreurs attendues
pour afficher un message propre sans trace d'exception.
"""

import argparse
import logging
import sys

from rich.console import Console

from velo.analysis.analysis import VALID_GROUP_BY
from velo.analysis.metrics import VALID_METRICS
from velo.commands.alerts import run_alerts
from velo.commands.collect import run_collect
from velo.commands.dashboard import run_dashboard
from velo.commands.favorites import (
    run_favorites_add,
    run_favorites_list,
    run_favorites_remove,
)
from velo.commands.history import run_history
from velo.commands.init import run_init
from velo.commands.query import run_query
from velo.commands.refresh import run_refresh
from velo.commands.station import run_station_list, run_station_search, run_station_show
from velo.commands.status import run_status
from velo.config import load_config
from velo.logging_config import setup_logging
from velo.models import VeloError

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Construit l'arbre complet des commandes et sous-commandes ``velo``."""
    parser = argparse.ArgumentParser(
        prog="velo",
        description="Consulter, collecter et analyser les données temps réel d'un réseau de vélos.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # velo init [--force]
    init_parser = subparsers.add_parser(
        "init",
        help="Prépare l'outil : configuration, dossier de données et premiers téléchargements",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Écrase le fichier config.yaml existant avec les valeurs par défaut",
    )

    # velo refresh
    subparsers.add_parser(
        "refresh",
        help="Met à jour les données statiques (stations, réseau, types de vélos)",
    )

    # velo status
    subparsers.add_parser(
        "status",
        help="Affiche un résumé de l'état du réseau en temps réel",
    )

    # velo station {search, list, show}
    station_parser = subparsers.add_parser(
        "station",
        help="Consulter, chercher ou lister les stations",
    )
    station_sub = station_parser.add_subparsers(dest="station_action", required=True)

    search_p = station_sub.add_parser("search", help="Chercher une station par son nom (regex)")
    search_p.add_argument("texte", help="Expression régulière à rechercher dans le nom")

    station_sub.add_parser("list", help="Lister toutes les stations avec leur identifiant")

    show_p = station_sub.add_parser("show", help="Afficher le détail temps réel d'une station")
    show_p.add_argument("station_id", help="Identifiant de la station")

    # velo favorites [add <id> | remove <id>]
    fav_parser = subparsers.add_parser(
        "favorites",
        help="Afficher, ajouter ou retirer des stations favorites",
    )
    fav_sub = fav_parser.add_subparsers(dest="favorites_action")
    fav_add = fav_sub.add_parser("add", help="Ajouter une station aux favoris (max 10)")
    fav_add.add_argument("station_id", help="Identifiant de la station à ajouter")
    fav_rm = fav_sub.add_parser("remove", help="Retirer une station des favoris")
    fav_rm.add_argument("station_id", help="Identifiant de la station à retirer")

    # velo alerts [--low-bikes N] [--low-docks N]
    alerts_parser = subparsers.add_parser(
        "alerts",
        help="Lister les stations hors service, vides/presque vides ou pleines/presque pleines",
    )
    alerts_parser.add_argument("--low-bikes", type=int, default=None, help="Seuil de vélos")
    alerts_parser.add_argument("--low-docks", type=int, default=None, help="Seuil de places libres")

    # velo dashboard [--refresh SECONDES]
    dash_parser = subparsers.add_parser(
        "dashboard",
        help="Tableau de bord du réseau mis à jour en temps réel",
    )
    dash_parser.add_argument(
        "--refresh",
        type=int,
        default=None,
        help="Intervalle de mise à jour en secondes (minimum 60)",
    )

    # velo collect [--interval S] [--duration D | --until "..." | --once]
    collect_parser = subparsers.add_parser(
        "collect",
        help="Enregistrer l'état de toutes les stations à intervalle régulier",
    )
    collect_parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Secondes entre deux relevés (minimum 60)",
    )
    stop_group = collect_parser.add_mutually_exclusive_group()
    stop_group.add_argument(
        "--duration",
        type=str,
        default=None,
        help="Arrêt automatique après une durée (ex: 3h, 30m)",
    )
    stop_group.add_argument(
        "--until",
        type=str,
        default=None,
        help='Arrêt automatique à une date/heure ("AAAA-MM-JJ HH:MM")',
    )
    stop_group.add_argument(
        "--once",
        action="store_true",
        help="Effectue un seul relevé puis s'arrête",
    )

    # velo history [--from AAAA-MM-JJ] [--to AAAA-MM-JJ]
    history_parser = subparsers.add_parser(
        "history",
        help="Afficher les périodes et relevés enregistrés",
    )
    history_parser.add_argument(
        "--from",
        dest="date_from",
        type=str,
        default=None,
        help="Date début",
    )
    history_parser.add_argument("--to", dest="date_to", type=str, default=None, help="Date fin")

    # velo query --metric ... [filtres] [--by ...] [--top N]
    query_parser = subparsers.add_parser(
        "query",
        help="Analyser l'historique enregistré",
    )
    query_parser.add_argument(
        "--metric",
        nargs="+",
        required=True,
        choices=VALID_METRICS,
        help="Une ou plusieurs métriques à calculer",
    )
    query_parser.add_argument("--date", type=str, default=None, help="Jour exact (AAAA-MM-JJ)")
    query_parser.add_argument("--from", dest="from_dt", type=str, default=None, help="Borne début")
    query_parser.add_argument("--to", dest="to_dt", type=str, default=None, help="Borne fin")
    query_parser.add_argument(
        "--period",
        nargs="+",
        type=int,
        default=None,
        help="Numéro(s) de période issus de velo history",
    )
    query_parser.add_argument(
        "--days",
        type=str,
        default=None,
        help="weekdays, weekend ou liste de jours (lundi,mardi)",
    )
    query_parser.add_argument(
        "--hours",
        type=str,
        default=None,
        help="Plage horaire (ex: 7-9)",
    )
    query_parser.add_argument(
        "--station",
        type=str,
        default=None,
        help="Identifiant d'une station",
    )
    query_parser.add_argument(
        "--by",
        dest="group_by",
        choices=VALID_GROUP_BY,
        default=None,
        help="Regroupement des résultats",
    )
    query_parser.add_argument("--top", type=int, default=None, help="N premiers résultats")

    return parser


def _dispatch(args: argparse.Namespace) -> int:
    """Exécute la commande sélectionnée par ``argparse``."""
    if args.command == "init":
        return run_init(force=args.force)

    # Toutes les autres commandes nécessitent une configuration valide dès le démarrage
    config = load_config()
    setup_logging(config.logging.level, config.log_file)

    if args.command == "refresh":
        return run_refresh(config)
    if args.command == "status":
        return run_status(config)
    if args.command == "station":
        if args.station_action == "search":
            return run_station_search(config, args.texte)
        if args.station_action == "list":
            return run_station_list(config)
        if args.station_action == "show":
            return run_station_show(config, args.station_id)
    if args.command == "favorites":
        if args.favorites_action == "add":
            return run_favorites_add(config, args.station_id)
        if args.favorites_action == "remove":
            return run_favorites_remove(config, args.station_id)
        return run_favorites_list(config)
    if args.command == "alerts":
        return run_alerts(config, low_bikes_opt=args.low_bikes, low_docks_opt=args.low_docks)
    if args.command == "dashboard":
        return run_dashboard(config, refresh_opt=args.refresh)
    if args.command == "collect":
        return run_collect(
            config,
            interval_opt=args.interval,
            duration_str=args.duration,
            until_str=args.until,
            once=args.once,
        )
    if args.command == "history":
        return run_history(config, from_str=args.date_from, to_str=args.date_to)
    if args.command == "query":
        return run_query(
            config,
            metrics=args.metric,
            date_str=args.date,
            from_str=args.from_dt,
            to_str=args.to_dt,
            period_ids=args.period,
            days_str=args.days,
            hours_str=args.hours,
            station_id=args.station,
            group_by=args.group_by,
            top_n=args.top,
        )

    return 1


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée principal de l'exécutable ``velo``."""
    parser = build_parser()
    args = parser.parse_args(argv)
    err_console = Console(stderr=True)

    try:
        exit_code = _dispatch(args)
    except VeloError as exc:
        # Erreur attendue : message clair, aucune trace d'exception, code de sortie non nul
        logger.error("%s", exc)
        err_console.print(f"[red]Erreur :[/red] {exc}")
        return 1
    except KeyboardInterrupt:
        err_console.print("\nOpération interrompue par l'utilisateur.")
        return 130
    except Exception as exc:
        # Filet de sécurité : on journalise le détail technique sans afficher de traceback brutal
        logger.exception("Erreur inattendue dans velo")
        err_console.print(f"[red]Erreur inattendue :[/red] {exc}")
        return 1

    if argv is None and exit_code != 0:
        sys.exit(exit_code)
    return exit_code
