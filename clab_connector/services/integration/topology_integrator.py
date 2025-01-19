# clab_connector/services/integration/topology_integrator.py

import logging
import typer

from clab_connector.models.topology import parse_topology_file
from clab_connector.clients.eda.client import (
    EDA,
)  # old eda.py -> EDA => in step 1, we just rename
from clab_connector.clients.kubernetes.client import (
    apply_manifest,
    edactl_namespace_bootstrap,
    wait_for_namespace,
    update_namespace_description,
)
from clab_connector.utils import helpers

logger = logging.getLogger(__name__)


class IntegrateCommand:
    PARSER_NAME = "integrate"
    PARSER_ALIASES = [PARSER_NAME, "i"]

    def run(self, args):
        self.args = args
        self.topology = parse_topology_file(str(self.args.topology_data))
        self.topology.check_connectivity()

        # minimal "only SR Linux is recognized" check
        srl_nodes = [n for n in self.topology.nodes if n.kind == "nokia_srlinux"]
        if not srl_nodes:
            logger.error("No Nokia SR Linux nodes found, exiting.")
            raise typer.Exit(code=1)

        self.eda = EDA(
            hostname=args.eda_url,
            username=args.eda_user,
            password=args.eda_password,
            verify=args.verify,
        )

        print("== Running pre-checks ==")
        self.prechecks()

        print("== Creating namespace ==")
        self.create_namespace()

        print("== Creating artifacts ==")
        self.create_artifacts()

        print("== Creating init ==")
        self.create_init()
        self.eda.commit_transaction("create init (bootstrap)")

        print("== Creating node security profile ==")
        self.create_node_security_profile()

        print("== Creating node users ==")
        self.create_node_user_groups()
        self.create_node_users()
        self.eda.commit_transaction("create node users and groups")

        print("== Creating node profiles ==")
        self.create_node_profiles()
        self.eda.commit_transaction("create node profiles")

        print("== Onboarding nodes ==")
        self.create_toponodes()
        self.eda.commit_transaction("create nodes")

        print("== Adding topolink interfaces ==")
        self.create_topolink_interfaces()
        self.eda.commit_transaction("create topolink interfaces")

        print("== Creating topolinks ==")
        self.create_topolinks()
        self.eda.commit_transaction("create topolinks")

        print("Done!")

    def prechecks(self):
        if not self.eda.is_up():
            raise Exception("EDA not up")
        if not self.eda.is_authenticated():
            raise Exception("EDA credentials invalid")

    def create_namespace(self):
        ns = f"clab-{self.topology.name}"
        logger.info(f"Creating namespace {ns}")
        edactl_namespace_bootstrap(ns)
        wait_for_namespace(ns)
        desc = f"Containerlab topology {self.topology.name}, file: {self.topology.clab_file_path}"
        update_namespace_description(ns, desc)

    def create_artifacts(self):
        """Creates artifacts needed by nodes that need them"""
        logger.info("Creating artifacts for nodes that need them")

        nodes_by_artifact = {}  # Track which nodes use which artifacts

        # First pass: collect all nodes and their artifacts
        for node in self.topology.nodes:
            if not node.needs_artifact():
                continue

            # Get artifact details
            artifact_name, filename, download_url = node.get_artifact_info()

            if not artifact_name or not filename or not download_url:
                logger.warning(f"Could not get artifact details for {node}. Skipping.")
                continue

            if artifact_name not in nodes_by_artifact:
                nodes_by_artifact[artifact_name] = {
                    "nodes": [],
                    "filename": filename,
                    "download_url": download_url,
                    "version": node.version,
                }
            nodes_by_artifact[artifact_name]["nodes"].append(node.name)

        # Second pass: create artifacts
        for artifact_name, info in nodes_by_artifact.items():
            first_node = info["nodes"][0]
            logger.info(
                f"Creating YANG artifact for node: {first_node} (version {info['version']})"
            )

            # Get the YAML and create the artifact
            artifact_yaml = self.topology.nodes[0].get_artifact_yaml(
                artifact_name, info["filename"], info["download_url"]
            )

            if not artifact_yaml:
                logger.warning(
                    f"Could not generate artifact YAML for {first_node}. Skipping."
                )
                continue

            try:
                apply_manifest(artifact_yaml, namespace="eda-system")
                logger.info(f"Artifact '{artifact_name}' has been created.")
                # Log about other nodes using this artifact
                other_nodes = info["nodes"][1:]
                if other_nodes:
                    logger.info(
                        f"Using same artifact for nodes: {', '.join(other_nodes)}"
                    )
            except RuntimeError as ex:
                if "AlreadyExists" in str(ex):
                    logger.info(
                        f"Artifact '{artifact_name}' already exists for nodes: {', '.join(info['nodes'])}"
                    )
                else:
                    logger.error(f"Error creating artifact '{artifact_name}': {ex}")

    def create_init(self):
        """
        Creates EDA init.
        """
        logger.info("Creating init")
        data = {
            "namespace": f"clab-{self.topology.name}",
        }

        nsp = helpers.render_template("init.yaml.j2", data)
        logger.debug(nsp)
        item = self.eda.add_replace_to_transaction(nsp)
        if not self.eda.is_transaction_item_valid(item):
            raise Exception(
                "Validation error when trying to create a node security profile, see warning above. Exiting..."
            )

    def create_node_security_profile(self):
        """
        Creates EDA node security profile.
        """
        logger.info("Creating node security profile")
        data = {
            "namespace": f"clab-{self.topology.name}",
        }

        nsp = helpers.render_template("nodesecurityprofile.yaml.j2", data)
        logger.debug(nsp)

        try:
            apply_manifest(nsp, namespace=f"clab-{self.topology.name}")
            logger.info("Node security profile has been created.")
        except RuntimeError as ex:
            if "AlreadyExists" in str(ex):
                logger.info("Node security profile already exists, skipping.")
            else:
                raise

    def create_node_user_groups(self):
        """
        Creates node user groups for the topology.
        """
        logger.info("Creating node user groups")
        data = {
            "namespace": f"clab-{self.topology.name}",
        }

        node_user_group = helpers.render_template("node-user-group.yaml.j2", data)
        logger.debug(node_user_group)
        item = self.eda.add_replace_to_transaction(node_user_group)
        if not self.eda.is_transaction_item_valid(item):
            raise Exception(
                "Validation error when trying to create a node user group, see warning above. Exiting..."
            )

    def create_node_users(self):
        """
        Creates node users for the topology.

        Currently simple changes the admin NodeUser to feature
        NokiaSrl1! password instead of the default eda124! password.
        """
        logger.info("Creating node users")
        data = {
            "namespace": f"clab-{self.topology.name}",
            "node_user": "admin",
            "username": "admin",
            "password": "NokiaSrl1!",
            "ssh_pub_keys": self.topology.ssh_pub_keys
            if hasattr(self.topology, "ssh_pub_keys")
            else [],
        }
        node_user = helpers.render_template("node-user.j2", data)
        logger.debug(node_user)
        item = self.eda.add_replace_to_transaction(node_user)
        if not self.eda.is_transaction_item_valid(item):
            raise Exception(
                "Validation error when trying to create a node user, see warning above. Exiting..."
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
            item = self.eda.add_replace_to_transaction(profile)
            if not self.eda.is_transaction_item_valid(item):
                raise Exception(
                    "Validation error when trying to create a node profile, see warning above. Exiting..."
                )

    def create_toponodes(self):
        """
        Creates nodes for the topology
        """
        logger.info("Creating nodes")
        toponodes = self.topology.get_toponodes()
        for toponode in toponodes:
            logger.debug(toponode)
            item = self.eda.add_replace_to_transaction(toponode)
            logger.debug(item)
            if not self.eda.is_transaction_item_valid(item):
                raise Exception(
                    "Validation error when trying to create a toponode, see warning above. Exiting..."
                )

    def create_topolink_interfaces(self):
        """
        Creates the interfaces that belong to topology links
        """
        logger.info("Creating topolink interfaces")
        interfaces = self.topology.get_topolink_interfaces()
        for interface in interfaces:
            logger.debug(interface)
            item = self.eda.add_replace_to_transaction(interface)
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
            item = self.eda.add_replace_to_transaction(topolink)
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
