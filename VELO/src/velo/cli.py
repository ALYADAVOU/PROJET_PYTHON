from velo.commands.init import run_init

init_parser = subparsers.add_parser(
    "init",
    help="Initialiser l'application"
)

init_parser.set_defaults(func=run_init)

args = parser.parse_args()

args.func(args)