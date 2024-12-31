import logging

import src.helpers as helpers

from src.subcommand import SubCommand
from src.eda import EDA

import tempfile
import subprocess

# set up logging
logger = logging.getLogger(__name__)


class IntegrateCommand(SubCommand):
    PARSER_NAME = "integrate"
    PARSER_ALIASES = [PARSER_NAME, "i"]

    def run(self, args):
        """
        Run the program with the arguments specified for this sub-command

        Parameters
        ----------
        args: input arguments returned by the argument parser
        """
        self.args = args
        self.topology = helpers.parse_topology(self.args.topology_file)
        self.topology.log_debug()
        self.eda = EDA(
            args.eda_url,
            args.eda_user,
            args.eda_password,
            args.http_proxy,
            args.https_proxy,
            args.verify,
        )

        #print("== Running pre-checks ==")
        #self.prechecks()

        #print("== Creating SR Linux artifacts for YANG models (if needed) ==")
        self.create_srl_artifacts()

        exit()


        print("== Creating allocation pool ==")
        self.create_allocation_pool()
        self.eda.commit_transaction(
            "EDA Containerlab Connector: create IP-mgmt allocation pool"
        )

        print("== Creating node profiles ==")
        self.create_node_profiles()
        self.eda.commit_transaction("EDA Containerlab Connector: create node profiles")
        # self.bootstrap_config()

        print("== Onboarding nodes ==")
        self.create_bootstrap_nodes()
        self.eda.commit_transaction("EDA Containerlab Connector: create nodes")

        print("== Adding system interfaces ==")
        self.create_system_interfaces()
        self.eda.commit_transaction(
            "EDA Containerlab Connector: create system interfaces"
        )

        print("== Adding topolink interfaces ==")
        self.create_topolink_interfaces()
        self.eda.commit_transaction(
            "EDA Containerlab Connector: create topolink interfaces"
        )

        print("== Creating topolinks ==")
        self.create_topolinks()
        self.eda.commit_transaction("EDA Containerlab Connector: create topolinks")

        print("Done!")

    def prechecks(self):
        """
        Performs pre-checks to see if everything is reachable
        """
        # check if the nodes are reachable
        self.topology.check_connectivity()

        # check if EDA is reachable
        if not self.eda.is_up():
            raise Exception("EDA status is not 'UP'")

        # check if we can authenticate with EDA
        if not self.eda.is_authenticated():
            raise Exception(
                "Could not authenticate to EDA with the provided credentials"
            )

    def create_srl_artifacts(self):
        logger.info("Creating SR Linux Artifact resources (via kubectl)")

        created_versions = set()

        for node in self.topology.nodes:
            if node.kind == "srl":
                version = node.version  # e.g. "24.10.1"
                if version in created_versions:
                    continue
                created_versions.add(version)

                # 1) Query GitHub
                filename, download_url = helpers.get_srlinux_artifact_from_github(version)
                if not filename or not download_url:
                    logger.warning(f"No suitable YANG artifact found in GitHub for version {version}. Skipping.")
                    continue

                artifact_name = f"srlinux-ghcr-{version}"

                # 3) Render template
                data = {
                    "artifact_name": artifact_name,
                    "namespace": "eda-system",
                    "artifact_filename": filename,
                    "artifact_url": download_url
                }
                artifact_yaml = helpers.render_template("artifact.j2", data)
                logger.debug("Artifact YAML:\n" + artifact_yaml)

                # 4) Apply via kubectl
                helpers.apply_manifest_via_kubectl(artifact_yaml, namespace="eda-system")
                logger.info(f"Artifact '{artifact_name}' for version '{version}' applied.")


    def create_allocation_pool(self):
        """
        Creates an IP allocation pool for the mgmt network of the topology
        """
        logger.info("Creating mgmt allocation pool")
        subnet_prefix = self.topology.mgmt_ipv4_subnet
        (subnet, prefix) = subnet_prefix.split("/")
        parts = subnet.split(".")
        gateway = f"{parts[0]}.{parts[1]}.{parts[2]}.{int(parts[3]) + 1}/{prefix}"

        data = {
            "pool_name": self.topology.get_mgmt_pool_name(),
            "subnet": subnet_prefix,
            "gateway": gateway,
        }

        pool = helpers.render_template("allocation-pool.j2", data)
        logger.debug(pool)
        item = self.eda.add_create_to_transaction(pool)
        if not self.eda.is_transaction_item_valid(item):
            raise Exception(
                "Validation error when trying to create a mgmt allocation pool, see warning above. Exiting..."
            )

    def create_node_profiles(self):
        """
        Creates node profiles for the topology
        """
        logger.info("Creating node profiles")
        profiles = self.topology.get_node_profiles()
        logger.info(f"Discovered {len(profiles)} distinct node profile(s)")
        for profile in profiles:
            logger.debug(profile)
            item = self.eda.add_create_to_transaction(profile)
            if not self.eda.is_transaction_item_valid(item):
                raise Exception(
                    "Validation error when trying to create a node profile, see warning above. Exiting..."
                )

    def bootstrap_config(self):
        """
        Push the bootstrap configuration to the nodes
        """
        logger.info("Pushing bootstrap config to the nodes")
        self.topology.bootstrap_config()

    def create_bootstrap_nodes(self):
        """
        Creates nodes for the topology
        """
        logger.info("Creating nodes")
        bootstrap_nodes = self.topology.get_bootstrap_nodes()
        for bootstrap_node in bootstrap_nodes:
            logger.debug(bootstrap_node)
            item = self.eda.add_create_to_transaction(bootstrap_node)
            if not self.eda.is_transaction_item_valid(item):
                raise Exception(
                    "Validation error when trying to create a bootstrap node, see warning above. Exiting..."
                )

    def create_system_interfaces(self):
        """
        Creates the system interfaces for all nodes
        """
        logger.info("Creating system interfaces")
        interfaces = self.topology.get_system_interfaces()
        for interface in interfaces:
            logger.debug(interface)
            item = self.eda.add_create_to_transaction(interface)
            if not self.eda.is_transaction_item_valid(item):
                raise Exception(
                    "Validation error when trying to create a system interface, see warning above. Exiting..."
                )

    def create_topolink_interfaces(self):
        """
        Creates the interfaces that belong to topology links
        """
        logger.info("Creating topolink interfaces")
        interfaces = self.topology.get_topolink_interfaces()
        for interface in interfaces:
            logger.debug(interface)
            item = self.eda.add_create_to_transaction(interface)
            if not self.eda.is_transaction_item_valid(item):
                raise Exception(
                    "Validation error when trying to create a topolink interface, see warning above. Exiting..."
                )

    def create_topolinks(self):
        """
        Creates topolinks for the topology
        """
        logger.info("Creating topolinks")
        topolinks = self.topology.get_topolinks()
        for topolink in topolinks:
            logger.debug(topolink)
            item = self.eda.add_create_to_transaction(topolink)
            if not self.eda.is_transaction_item_valid(item):
                raise Exception(
                    "Validation error when trying to create a topolink, see warning above. Exiting..."
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
            help="integrate containerlab with EDA",
            aliases=self.PARSER_ALIASES,
        )

        parser.add_argument(
            "--topology-file",
            "-t",
            type=str,
            required=True,
            help="the containerlab topology file",
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
