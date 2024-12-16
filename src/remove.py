import logging

import src.helpers as helpers

from src.subcommand import SubCommand
from src.eda import EDA

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

        print("== Removing topolinks ==")
        self.remove_topolinks()
        self.eda.commit_transaction("EDA Containerlab Connector: remove topolinks")

        print("== Removing topolink interfaces ==")
        self.remove_topolink_interfaces()
        self.eda.commit_transaction(
            "EDA Containerlab Connector: remove topolink interfaces"
        )

        print("== Removing system interfaces ==")
        self.remove_system_interfaces()
        self.eda.commit_transaction(
            "EDA Containerlab Connector: remove system interfaces"
        )

        print("== Removing nodes ==")
        self.remove_bootstrap_nodes()
        self.eda.commit_transaction("EDA Containerlab Connector: remove nodes")

        print("== Removing node profiles ==")
        self.remove_node_profiles()
        self.eda.commit_transaction("EDA Containerlab Connector: remove node profiles")

        print("== Removing allocation pool ==")
        self.remove_allocation_pool()
        self.eda.commit_transaction(
            "EDA Containerlab Connector: remove allocation pool"
        )

        print("Done!")

    def remove_topolinks(self):
        """
        Removes the topolinks for the topology
        """
        logger.info("Removing topolinks")
        for link in self.topology.links:
            logger.debug(link)
            if not link.is_topolink():
                logger.debug("Ignoring link, not a topolink")
                continue
            self.eda.add_delete_to_transaction(
                "TopoLink", link.get_link_name(self.topology)
            )

    def remove_topolink_interfaces(self):
        """
        Removes the topolink interfaces of the nodes of the topology
        """
        logger.info("Removing topolink interfaces")
        for link in self.topology.links:
            logger.debug(link)
            if not link.is_topolink():
                logger.debug("Ignoring link, not a topolink")
                continue

            ifname_1 = link.node_1.get_topolink_interface_name(
                self.topology, link.interface_1
            )
            ifname_2 = link.node_2.get_topolink_interface_name(
                self.topology, link.interface_2
            )

            for interface in [ifname_1, ifname_2]:
                self.eda.add_delete_to_transaction(
                    "Interface",
                    interface,
                    group=self.eda.INTERFACE_GROUP,
                    version=self.eda.INTERFACE_VERSION,
                )

    def remove_system_interfaces(self):
        """
        Removes the system interfaces of the nodes of the topology
        """
        logger.info("Removing system interfaces")
        for node in self.topology.nodes:
            logger.debug(node)
            ifname = node.get_system_interface_name(self.topology)
            if ifname is None:
                logger.debug("Ignoring node, system interface not supported")
                continue
            self.eda.add_delete_to_transaction(
                "Interface",
                ifname,
                group=self.eda.INTERFACE_GROUP,
                version=self.eda.INTERFACE_VERSION,
            )

    def remove_bootstrap_nodes(self):
        """
        Removes the toponodes for the topology
        """
        logger.info("Removing bootstrapped nodes")
        for node in self.topology.nodes:
            logger.debug(node)
            self.eda.add_delete_to_transaction(
                "TopoNode", node.get_node_name(self.topology)
            )

    def remove_node_profiles(self):
        """
        Removes the node profiles for the different node kinds in the topology
        """
        logger.info("Removing the node profiles")
        profile_names = []
        for node in self.topology.nodes:
            logger.debug(node)

            if not node.is_eda_supported():
                continue

            profile_name = node.get_profile_name(self.topology)
            if profile_name not in profile_names:
                # avoids removing the same node profile twice
                profile_names.append(profile_name)
                logger.debug(f"Profile name: {profile_name}")
                self.eda.add_delete_to_transaction("NodeProfile", profile_name)

    def remove_allocation_pool(self):
        """
        Removes the allocation pool for the mgmt network of the topology
        """
        logger.info("Removing mgmt allocation pool")
        self.eda.add_delete_to_transaction(
            "IPInSubnetAllocationPool", self.topology.get_mgmt_pool_name()
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
