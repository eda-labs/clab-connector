# clab_connector/models/link.py

import logging

from clab_connector.utils import helpers

logger = logging.getLogger(__name__)


class Link:
    """
    Represents a bidirectional link between two nodes.

    Parameters
    ----------
    node_1 : Node
        The first node in the link.
    intf_1 : str
        The interface name on the first node.
    node_2 : Node
        The second node in the link.
    intf_2 : str
        The interface name on the second node.
    """

    def __init__(self, node_1, intf_1, node_2, intf_2):
        self.node_1 = node_1
        self.intf_1 = intf_1
        self.node_2 = node_2
        self.intf_2 = intf_2

    def __repr__(self):
        """
        Return a string representation of the link.

        Returns
        -------
        str
            A description of the link endpoints.
        """
        return f"Link({self.node_1}-{self.intf_1}, {self.node_2}-{self.intf_2})"

    def is_topolink(self):
        """
        Check if both endpoints are EDA-supported nodes.

        Returns
        -------
        bool
            True if both nodes support EDA, False otherwise.
        """
        if self.node_1 is None or not self.node_1.is_eda_supported():
            return False
        return not (self.node_2 is None or not self.node_2.is_eda_supported())

    def is_edge_link(self):
        """Check if exactly one endpoint is EDA-supported and the other is a linux node."""
        if not self.node_1 or not self.node_2:
            return False
        if self.node_1.is_eda_supported() and self.node_2.kind == "linux":
            return True
        return bool(self.node_2.is_eda_supported() and self.node_1.kind == "linux")

    def get_link_name(self, topology):
        """
        Create a unique name for the link resource.

        Parameters
        ----------
        topology : Topology
            The topology that owns this link.

        Returns
        -------
        str
            A link name safe for EDA.
        """
        return f"{self.node_1.get_node_name(topology)}-{self.intf_1}-{self.node_2.get_node_name(topology)}-{self.intf_2}"

    def get_topolink_yaml(self, topology):
        """
        Render and return the TopoLink YAML if the link is EDA-supported.

        Parameters
        ----------
        topology : Topology
            The topology that owns this link.

        Returns
        -------
        str or None
            The rendered TopoLink CR YAML, or None if not EDA-supported.
        """
        if self.is_topolink():
            role = "interSwitch"
        elif self.is_edge_link():
            role = "edge"
        else:
            return None
        data = {
            "namespace": f"clab-{topology.name}",
            "link_role": role,
            "link_name": self.get_link_name(topology),
            "local_node": self.node_1.get_node_name(topology),
            "local_interface": self.node_1.get_interface_name_for_kind(self.intf_1),
            "remote_node": self.node_2.get_node_name(topology),
            "remote_interface": self.node_2.get_interface_name_for_kind(self.intf_2),
        }
        return helpers.render_template("topolink.j2", data)


def create_link(endpoints: list, nodes: list) -> Link:
    """
    Create a Link object from two endpoint definitions and a list of Node objects.

    Parameters
    ----------
    endpoints : list
        A list of exactly two endpoint strings, e.g. ["nodeA:e1-1", "nodeB:e1-1"].
    nodes : list
        A list of Node objects in the topology.

    Returns
    -------
    Link
        A Link object representing the connection.

    Raises
    ------
    ValueError
        If the endpoint format is invalid or length is not 2.
    """

    if len(endpoints) != 2:
        raise ValueError("Link endpoints must be a list of length 2")

    def parse_endpoint(ep):
        parts = ep.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid endpoint '{ep}', must be 'node:iface'")
        return parts[0], parts[1]

    nodeA, ifA = parse_endpoint(endpoints[0])
    nodeB, ifB = parse_endpoint(endpoints[1])

    nA = next((n for n in nodes if n.name == nodeA), None)
    nB = next((n for n in nodes if n.name == nodeB), None)

    return Link(nA, ifA, nB, ifB)

