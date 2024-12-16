import logging

from src.node import from_obj as node_from_obj
from src.link import from_obj as link_from_obj

# set up logging
logger = logging.getLogger(__name__)


class Topology:
    def __init__(self, name, mgmt_ipv4_subnet, nodes, links):
        self.name = name
        self.mgmt_ipv4_subnet = mgmt_ipv4_subnet
        self.nodes = nodes
        self.links = links

    def __repr__(self):
        return f"Topology(name={self.name}, mgmt_ipv4_subnet={self.mgmt_ipv4_subnet}) with {len(self.nodes)} nodes"

    def log_debug(self):
        """
        Prints the topology and all nodes that belong to it to the debug logger
        """
        logger.debug("=== Topology ===")
        logger.debug(self)

        logger.debug("== Nodes == ")
        for node in self.nodes:
            logger.debug(node)

        logger.debug("== Links == ")
        for link in self.links:
            logger.debug(link)

    def check_connectivity(self):
        """
        Checks whether all nodes are pingable, and have the SSH interface open
        """
        for node in self.nodes:
            node.ping()

        for node in self.nodes:
            node.test_ssh()

    def get_eda_safe_name(self):
        """
        Returns an EDA-safe name for the name of the topology
        """
        return self.name.replace("_", "-")

    def get_mgmt_pool_name(self):
        """
        Returns an EDA-safe name for the IPInSubnetAllocationPool for mgmt
        """
        return f"{self.get_eda_safe_name()}-mgmt-pool"

    def get_node_profiles(self):
        """
        Creates node profiles for all nodes in the topology. One node profile per type/sw-version is created
        """
        profiles = {}
        for node in self.nodes:
            node_profile = node.get_node_profile(self)
            if node_profile is None:
                # node profile not supported (for example, linux containers that are not managed by EDA)
                continue

            if f"{node.kind}-{node.version}" not in profiles:
                profiles[f"{node.kind}-{node.version}"] = node_profile

        # only return the node profiles, not the keys
        return profiles.values()

    def bootstrap_config(self):
        """
        Pushes the bootstrap configuration to the nodes
        """
        for node in self.nodes:
            node.bootstrap_config()

    def get_bootstrap_nodes(self):
        """
        Create nodes for the topology
        """
        bootstrap_nodes = []
        for node in self.nodes:
            bootstrap_node = node.get_bootstrap_node(self)
            if bootstrap_node is None:
                continue

            bootstrap_nodes.append(bootstrap_node)

        return bootstrap_nodes

    def get_topolinks(self):
        """
        Create topolinks for the topology
        """
        topolinks = []
        for link in self.links:
            if link.is_topolink():
                topolinks.append(link.get_topolink(self))

        return topolinks

    def get_system_interfaces(self):
        """
        Create system interfaces for the nodes in the topology
        """
        interfaces = []
        for node in self.nodes:
            if not node.is_eda_supported():
                continue

            interface = node.get_system_interface(self)
            if interface is not None:
                interfaces.append(interface)

        return interfaces

    def get_topolink_interfaces(self):
        """
        Create topolink interfaces for the links in the topology
        """
        interfaces = []
        for link in self.links:
            if link.is_topolink():
                interfaces.append(
                    link.node_1.get_topolink_interface(
                        self, link.interface_1, link.node_2
                    )
                )
                interfaces.append(
                    link.node_2.get_topolink_interface(
                        self, link.interface_2, link.node_1
                    )
                )

        return interfaces


def from_obj(python_obj):
    """
    Parsers a topology from a Python object

    Parameters
    ----------
    python_obj: the python object parsed from the yaml input file

    Returns
    -------
    The parsed Topology entity
    """
    logger.info(
        f"Parsing topology with name '{python_obj['name']}' which contains {len(python_obj['topology']['nodes'])} nodes"
    )

    name = python_obj["name"]
    mgmt_ipv4_subnet = python_obj["mgmt"]["ipv4-subnet"]
    nodes = []
    for node in python_obj["topology"]["nodes"]:
        nodes.append(
            node_from_obj(
                node,
                python_obj["topology"]["nodes"][node],
                python_obj["topology"]["kinds"],
            )
        )

    links = []
    for link in python_obj["topology"]["links"]:
        links.append(link_from_obj(link, nodes))

    return Topology(name, mgmt_ipv4_subnet, nodes, links)
