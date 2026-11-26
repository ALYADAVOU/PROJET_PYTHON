"""Point d'entrée de la commande ``velo`` dans le terminal.

Ce fichier lit les arguments tapés par l'utilisateur avec ``argparse``,
charge la configuration puis appelle la bonne fonction dans ``commands/``.
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
    """Déclare toutes les sous-commandes et options acceptées par ``velo``."""
    parser = argparse.ArgumentParser(
        prog="velo",
        description="Consulter, collecter et analyser les données d'un réseau de vélos.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Commande init
    init_p = sub.add_parser("init", help="Préparer la configuration et les dossiers")
    init_p.add_argument("--force", action="store_true", help="Réécrire config.yaml")

    # Commandes simples sans argument
    sub.add_parser("refresh", help="Mettre à jour les fichiers statiques du réseau")
    sub.add_parser("status", help="Afficher le résumé temps réel du réseau")

    # Commande station (search / list / show)
    st_p = sub.add_parser("station", help="Chercher, lister ou consulter une station")
    st_sub = st_p.add_subparsers(dest="station_action", required=True)
    st_sub.add_parser("search", help="Chercher par nom (regex)").add_argument("texte")
    st_sub.add_parser("list", help="Lister toutes les stations")
    st_sub.add_parser("show", help="Afficher une station en détail").add_argument("station_id")

    # Commande favorites (par défaut : affiche ; sinon add / remove)
    fav_p = sub.add_parser("favorites", help="Gérer les stations favorites (max 10)")
    fav_sub = fav_p.add_subparsers(dest="favorites_action")
    fav_sub.add_parser("add", help="Ajouter un favori").add_argument("station_id")
    fav_sub.add_parser("remove", help="Retirer un favori").add_argument("station_id")

    # Commande alerts
    al_p = sub.add_parser("alerts", help="Lister les stations en alerte")
    al_p.add_argument("--low-bikes", type=int, default=None, help="Seuil vélos")
    al_p.add_argument("--low-docks", type=int, default=None, help="Seuil places libres")

    # Commande dashboard
    dash_p = sub.add_parser("dashboard", help="Tableau de bord mis à jour en temps réel")
    dash_p.add_argument("--refresh", type=int, default=None, help="Secondes (min 60)")

    # Commande collect (--duration, --until et --once sont mutuellement exclusifs)
    col_p = sub.add_parser("collect", help="Enregistrer l'historique en CSV")
    col_p.add_argument("--interval", type=int, default=None, help="Secondes (min 60)")
    stop = col_p.add_mutually_exclusive_group()
    stop.add_argument("--duration", type=str, default=None, help="Durée (ex: 3h, 30m)")
    stop.add_argument("--until", type=str, default=None, help='Fin ("AAAA-MM-JJ HH:MM")')
    stop.add_argument("--once", action="store_true", help="Un seul relevé puis arrêt")

    # Commande history
    hist_p = sub.add_parser("history", help="Afficher les périodes collectées")
    hist_p.add_argument("--from", dest="date_from", type=str, default=None)
    hist_p.add_argument("--to", dest="date_to", type=str, default=None)

    # Commande query
    q_p = sub.add_parser("query", help="Analyser l'historique enregistré")
    q_p.add_argument("--metric", nargs="+", required=True, choices=VALID_METRICS)
    q_p.add_argument("--date", type=str, default=None)
    q_p.add_argument("--from", dest="from_dt", type=str, default=None)
    q_p.add_argument("--to", dest="to_dt", type=str, default=None)
    q_p.add_argument("--period", nargs="+", type=int, default=None)
    q_p.add_argument("--days", type=str, default=None)
    q_p.add_argument("--hours", type=str, default=None)
    q_p.add_argument("--station", type=str, default=None)
    q_p.add_argument("--by", dest="group_by", choices=VALID_GROUP_BY, default=None)
    q_p.add_argument("--top", type=int, default=None)

    return parser


def _dispatch(args: argparse.Namespace) -> int:
    """Envoie les arguments analysés vers la fonction de commande correspondante."""
    if args.command == "init":
        return run_init(force=args.force)

    # Toutes les autres commandes lisent config.yaml et activent les logs dès le début
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
    """Fonction principale lancée par la commande ``velo``."""
    args = build_parser().parse_args(argv)
    err_console = Console(stderr=True)

    try:
        exit_code = _dispatch(args)
    except VeloError as exc:
        # Erreur prévue (réseau, config, ID inconnu) : message clair sans traceback
        logger.error("%s", exc)
        err_console.print(f"[red]Erreur :[/red] {exc}")
        return 1
    except KeyboardInterrupt:
        err_console.print("\nOpération interrompue.")
        return 130
    except Exception as exc:
        # Erreur imprévue : on garde le détail dans velo.log sans bloquer l'affichage propre
        logger.exception("Erreur inattendue")
        err_console.print(f"[red]Erreur inattendue :[/red] {exc}")
        return 1

    if argv is None and exit_code != 0:
        sys.exit(exit_code)
    return exit_code
