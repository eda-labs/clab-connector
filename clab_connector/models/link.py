# clab_connector/models/link.py

import logging
from clab_connector.utils import helpers

logger = logging.getLogger(__name__)


class Link:
    def __init__(self, node_1, intf_1, node_2, intf_2):
        self.node_1 = node_1
        self.intf_1 = intf_1
        self.node_2 = node_2
        self.intf_2 = intf_2

    def __repr__(self):
        return f"Link({self.node_1}-{self.intf_1}, {self.node_2}-{self.intf_2})"

    def is_topolink(self):
        if self.node_1 is None or not self.node_1.is_eda_supported():
            return False
        if self.node_2 is None or not self.node_2.is_eda_supported():
            return False
        return True

    def get_link_name(self, topology):
        return f"{self.node_1.get_node_name(topology)}-{self.intf_1}-{self.node_2.get_node_name(topology)}-{self.intf_2}"

    def get_topolink_yaml(self, topology):
        if not self.is_topolink():
            return None
        data = {
            "namespace": f"clab-{topology.name}",
            "link_role": "interSwitch",
            "link_name": self.get_link_name(topology),
            "local_node": self.node_1.get_node_name(topology),
            "local_interface": self.node_1.get_interface_name_for_kind(self.intf_1),
            "remote_node": self.node_2.get_node_name(topology),
            "remote_interface": self.node_2.get_interface_name_for_kind(self.intf_2),
        }
        return helpers.render_template("topolink.j2", data)


def create_link(endpoints: list, nodes: list) -> Link:
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
