import logging

import src.helpers as helpers
from src.eda import EDA
from src.subcommand import SubCommand

# set up logging
logger = logging.getLogger(__name__)


class RemoveCommand(SubCommand):
    PARSER_NAME = "remove"
    PARSER_ALIASES = [PARSER_NAME, "r"]

    def run(self, args):
        """
        Run the program with the arguments specified for this sub-command

        Parameters
        ----------
        args: input arguments returned by the argument parser
        """
        self.args = args
        self.topology = helpers.parse_topology(self.args.topology_data)
        self.topology.log_debug()
        self.eda = EDA(
            args.eda_url,
            args.eda_user,
            args.eda_password,
            args.verify,
        )

        print("== Removing namespace ==")
        self.remove_namespace()
        self.eda.commit_transaction("EDA Containerlab Connector: remove namespace")

        print("Done!")

    def remove_namespace(self):
        """
        Removes the namespace for the topology
        """
        logger.info("Removing namespace")
        self.eda.add_delete_to_transaction(
            "",
            "Namespace",
            f"clab-{self.topology.name}",
        )

    def create_parser(self, subparsers):
        """
        Creates a subparser with arguments specific to this subcommand of the program

        Parameters
        ----------
        subparsers: the subparsers object for the parent command

        Returns
        -------
        An argparse subparser
        """
        parser = subparsers.add_parser(
            self.PARSER_NAME,
            help="remove containerlab integration from EDA",
            aliases=self.PARSER_ALIASES,
        )

        parser.add_argument(
            "--topology-data",
            "-t",
            type=str,
            required=True,
            help="the containerlab topology data JSON file",
        )

        parser.add_argument(
            "--eda-url",
            "-e",
            type=str,
            required=True,
            help="the hostname or IP of your EDA deployment",
        )

        parser.add_argument(
            "--eda-user", type=str, default="admin", help="the username of the EDA user"
        )

        parser.add_argument(
            "--eda-password",
            type=str,
            default="admin",
            help="the password of the EDA user",
        )

        return parser
