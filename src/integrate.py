import logging

import src.helpers as helpers
from src.eda import EDA
from src.subcommand import SubCommand

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

        print("== Running pre-checks ==")
        self.prechecks()

        # print("== Creating artifacts ==")
        # self.create_artifacts()

        # print("== Creating allocation pool ==")
        # self.create_allocation_pool()
        # self.eda.commit_transaction(
        #     "EDA Containerlab Connector: create IP-mgmt allocation pool"
        # )

        try:
            print("== Creating namespace ==")
            self.create_namespace()
            transactionId = self.eda.commit_transaction("EDA Containerlab Connector: create namespace")
            # Store the first transaction ID
            self.initial_transaction_id = transactionId - 1

            print("== Creating init ==")
            self.create_init()
            self.eda.commit_transaction(
            "EDA Containerlab Connector: create init (bootstrap)"
            )

            print("== Creating node security profile ==")
            self.create_node_security_profile()

            print("== Creating node users ==")
            self.create_node_user_groups()
            self.create_node_users()
            self.eda.commit_transaction(
            "EDA Containerlab Connector: create node users and groups"
            )

            print("== Creating node profiles ==")
            self.create_node_profiles()
            self.eda.commit_transaction("EDA Containerlab Connector: create node profiles")
            #self.bootstrap_config()

            print("== Onboarding nodes ==")
            self.create_bootstrap_nodes()
            self.eda.commit_transaction("EDA Containerlab Connector: create nodes")

            # print("== Adding system interfaces ==")
            # self.create_system_interfaces()
            # self.eda.commit_transaction(
            #     "EDA Containerlab Connector: create system interfaces"
            # )

            print("== Adding topolink interfaces ==")
            self.create_topolink_interfaces()
            self.eda.commit_transaction(
            "EDA Containerlab Connector: create topolink interfaces"
            )

            print("== Creating topolinks ==")
            self.create_topolinks()
            self.eda.commit_transaction("EDA Containerlab Connector: create topolinks")

            print("Done!")

        except Exception as e:
            if self.initial_transaction_id:
                print("Error occurred during integration. Restore to initial state...")
                self.eda.restore_transaction(self.initial_transaction_id)
                print("Revert completed.")
            raise e

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

    def create_artifacts(self):
        """
        Creates artifacts needed by nodes in the topology
        """
        logger.info("Creating artifacts for nodes that need them")

        processed = set()  # Track which artifacts we've already created

        for node in self.topology.nodes:
            if not node.needs_artifact():
                continue

            # Get artifact details
            artifact_name, filename, download_url = node.get_artifact_info()

            if not artifact_name or not filename or not download_url:
                logger.warning(f"Could not get artifact details for {node}. Skipping.")
                continue

            # Skip if we already processed this artifact
            if artifact_name in processed:
                continue
            processed.add(artifact_name)

            # Get the YAML and create the artifact
            artifact_yaml = node.get_artifact_yaml(
                artifact_name, filename, download_url
            )
            if not artifact_yaml:
                logger.warning(
                    f"Could not generate artifact YAML for {node}. Skipping."
                )
                continue

            try:
                helpers.apply_manifest_via_kubectl(
                    artifact_yaml, namespace="eda-system"
                )
                logger.info(f"Artifact '{artifact_name}' has been created.")
            except RuntimeError as ex:
                if "AlreadyExists" in str(ex):
                    logger.info(f"Artifact '{artifact_name}' already exists, skipping.")
                else:
                    logger.error(f"Error creating artifact '{artifact_name}': {ex}")

    # def create_allocation_pool(self):
    #     """
    #     Creates an IP allocation pool for the mgmt network of the topology
    #     """
    #     logger.info("Creating mgmt allocation pool")
    #     subnet_prefix = self.topology.mgmt_ipv4_subnet
    #     (subnet, prefix) = subnet_prefix.split("/")
    #     parts = subnet.split(".")
    #     gateway = f"{parts[0]}.{parts[1]}.{parts[2]}.{int(parts[3]) + 1}/{prefix}"

    #     data = {
    #         "pool_name": self.topology.get_mgmt_pool_name(),
    #         "subnet": subnet_prefix,
    #         "gateway": gateway,
    #     }

    #     pool = helpers.render_template("allocation-pool.j2", data)
    #     logger.debug(pool)
    #     item = self.eda.add_create_to_transaction(pool)
    #     if not self.eda.is_transaction_item_valid(item):
    #         raise Exception(
    #             "Validation error when trying to create a mgmt allocation pool, see warning above. Exiting..."
    #         )

    def create_namespace(self):
        """
        Creates EDA namespace named after clab-<lab_name>.
        """
        logger.info("Creating namespace")
        data = {
            "namespace": f"clab-{self.topology.name}",
            "namespace_description": f"Containerlab topology. Name: {self.topology.name}, Topology file: {self.topology.clab_file_path}, IPv4 subnet: {self.topology.mgmt_ipv4_subnet}",
        }

        ns = helpers.render_template("namespace.j2", data)
        logger.debug(ns)
        item = self.eda.add_replace_to_transaction(ns)
        if not self.eda.is_transaction_item_valid(item):
            raise Exception(
                "Validation error when trying to create a namespace, see warning above. Exiting..."
            )

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
        helpers.apply_manifest_via_kubectl(
            yaml_str=nsp, namespace=f"clab-{self.topology.name}"
        )

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
            item = self.eda.add_replace_to_transaction(bootstrap_node)
            logger.debug(item)
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
