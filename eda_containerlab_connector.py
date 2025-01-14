import argparse
import logging
import os

import urllib3

from src.integrate import IntegrateCommand
from src.remove import RemoveCommand

urllib3.disable_warnings()

SUPPORTED_KINDS = ["nokia_srlinux"]

subcommands = [IntegrateCommand(), RemoveCommand()]

parser = argparse.ArgumentParser(
    prog="Containerlab EDA connector",
    description="Integrate an existing containerlab topology with EDA (Event-Driven Automation)",
    epilog="Made by Zeno Dhaene (zeno.dhaene@nokia.com)",
)

parser.add_argument(
    "--log-level",
    "-l",
    type=str,
    default="WARNING",
    choices={"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"},
    help="log level for the application",
)

parser.add_argument(
    "--http-proxy",
    type=str,
    default="",
    help="HTTP proxy to be used to communicate with EDA",
)

parser.add_argument(
    "--https-proxy",
    type=str,
    default="",
    help="HTTPS proxy to be used to communicate with EDA",
)

parser.add_argument(
    "--verify", action="store_true", help="Enables certificate verification for EDA"
)

subparsers = parser.add_subparsers(
    dest="subparser",
    title="sub-commands",
    description="valid sub-commands",
    help="choose a sub-command for more information",
    required=True,
)

for command in subcommands:
    command.create_parser(subparsers)

args = parser.parse_args()
logging.basicConfig(
    level=args.log_level,
    format="[%(asctime)s][%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

print(args)

# set fancy logging colours
logging.addLevelName(
    logging.INFO, f"\x1b[1;32m{logging.getLevelName(logging.INFO)}\x1b[0m"
)
logging.addLevelName(
    logging.WARN, f"\x1b[1;38;5;220m{logging.getLevelName(logging.WARN)}\x1b[0m"
)
logging.addLevelName(
    logging.DEBUG, f"\x1b[1;94m{logging.getLevelName(logging.DEBUG)}\x1b[0m"
)
logging.addLevelName(
    logging.ERROR, f"\x1b[1;91m{logging.getLevelName(logging.ERROR)}\x1b[0m"
)
logging.addLevelName(
    logging.CRITICAL, f"\x1b[1;91m{logging.getLevelName(logging.CRITICAL)}\x1b[0m"
)

# set up logging
logger = logging.getLogger(__name__)
logger.warning(f"Supported containerlab kinds are: {SUPPORTED_KINDS}")

# this will bite me in the ass someday
os.environ["no_proxy"] = args.eda_url

matched_subparser = [x for x in subcommands if args.subparser in x.PARSER_ALIASES]

if len(matched_subparser) > 1:
    raise Exception(
        f"Multiple {len(matched_subparser)} match given subparser {args.subparser}"
    )
else:
    matched_subparser[0].run(args)
