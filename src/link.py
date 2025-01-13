import logging

import src.helpers as helpers

# set up logging
logger = logging.getLogger(__name__)


class Link:
    def __init__(self, node_1, interface_1, node_2, interface_2):
        self.node_1 = node_1
        self.interface_1 = interface_1
        self.node_2 = node_2
        self.interface_2 = interface_2

    def __repr__(self):
        return (
            f"Link({self.node_1}-{self.interface_1}, {self.node_2}-{self.interface_2})"
        )

    def get_link_name(self, topology):
        """
        Returns an eda-safe name for the link
        """
        return f"{self.node_1.get_node_name(topology)}-{self.interface_1}-{self.node_2.get_node_name(topology)}-{self.interface_2}"

    def get_interface1_name(self):
        """
        Returns the name for the interface name of endpoint 1, as specified in EDA
        """
        return self.node_1.get_interface_name_for_kind(self.interface_1)

    def get_interface2_name(self):
        """
        Returns the name for the interface name of endpoint 2, as specified in EDA
        """
        return self.node_2.get_interface_name_for_kind(self.interface_2)

    def is_topolink(self):
        """
        Returns True if both endpoints are supported in EDA as topology nodes, False otherwise
        """
        # check that both ends of the link are supported in EDA
        if self.node_1 is None or not self.node_1.is_eda_supported():
            logger.debug(
                f"Link {self} is not a topolink because endpoint 1 node kind '{self.node_1.kind}' is not supported in EDA"
            )
            return False
        if self.node_2 is None or not self.node_2.is_eda_supported():
            logger.debug(
                f"Link {self} is not a topolink because endpoint 2 node kind '{self.node_2.kind}' is not supported in EDA"
            )
            return False

        return True

    def get_topolink(self, topology):
        """
        Returns an EDA topolink resource that represents this link
        """
        logger.info(f"Rendering topolink for {self}")
        if not self.is_topolink():
            logger.warning(
                f"Could not render topolink, {self} is not a topolink. Please call is_topolink() first"
            )
            return None

        data = {
            "namespace": f"clab-{topology.name}",
            "link_role": "interSwitch",
            "link_name": self.get_link_name(topology),
            "local_node": self.node_1.get_node_name(topology),
            "local_interface": self.get_interface1_name(),
            "remote_node": self.node_2.get_node_name(topology),
            "remote_interface": self.get_interface2_name(),
        }

        return helpers.render_template("topolink.j2", data)


def from_obj(python_object, nodes):
    """
    Parses a link from a python array of 2 endpoints

    Parameters
    ----------
    python_object:  the python object containing the endpoints from the input json file
    nodes:          nodes part of the topology

    Returns
    -------
    The parsed Link entity
    """
    logger.info(f"Parsing link with endpoints {python_object}")
    if "endpoints" not in python_object:
        raise Exception("The python object does not contain the key 'endpoints'")

    if len(python_object["endpoints"]) != 2:
        raise Exception("The endpoint array should be an array of two objects")

    endpoint_1 = python_object["endpoints"][0]
    endpoint_2 = python_object["endpoints"][1]

    (node_name_1, interface_1) = split_endpoint(endpoint_1)
    (node_name_2, interface_2) = split_endpoint(endpoint_2)

    node_1 = find_node(node_name_1, nodes)
    node_2 = find_node(node_name_2, nodes)

    return Link(node_1, interface_1, node_2, interface_2)


def split_endpoint(endpoint):
    """
    Splits and endpoint into its node name, and the interface

    Parameters
    ----------
    endpoint: the name of an endpoint as found in the topology file

    Returns
    -------
    A tuple of (node_name, node_interface) where node_name is the name of the node, and node_interface the interface
    """
    parts = endpoint.split(":")

    if len(parts) != 2:
        raise Exception(
            f"Endpoint '{endpoint}' does not adhere to the format '[node]:[interface]'"
        )

    return (parts[0], parts[1])


def find_node(node_name, nodes):
    """
    Searches through the provided nodes array for a node with name node_name

    Parameters
    ----------
    node_name:  the name of the node that's being looked for
    nodes:      the array of Node that will be searched

    Returns:
    --------
    The Node if it was found, None otherwise
    """
    for node in nodes:
        if node.name == node_name:
            return node

    return None
