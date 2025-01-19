# clab_connector/models/topology.py

import logging
import os
import sys
import json

from clab_connector.models.node.factory import create_node
from clab_connector.models.link import create_link

logger = logging.getLogger(__name__)


class Topology:
    def __init__(self, name, mgmt_subnet, ssh_keys, nodes, links, clab_file_path=""):
        self.name = name
        self.mgmt_ipv4_subnet = mgmt_subnet
        self.ssh_pub_keys = ssh_keys
        self.nodes = nodes
        self.links = links
        self.clab_file_path = clab_file_path

    def __repr__(self):
        return (
            f"Topology(name={self.name}, mgmt_ipv4_subnet={self.mgmt_ipv4_subnet}, "
            f"nodes={len(self.nodes)}, links={len(self.links)})"
        )

    def get_eda_safe_name(self):
        # Just an example
        safe = self.name.lower().replace("_", "-").replace(" ", "-")
        safe = "".join(c for c in safe if c.isalnum() or c in ".-").strip(".-")
        if not safe or not safe[0].isalnum():
            safe = "x" + safe
        if not safe[-1].isalnum():
            safe += "0"
        return safe

    def check_connectivity(self):
        for node in self.nodes:
            node.ping()

    def get_node_profiles(self):
        """
        Return unique node profiles from each node if supported
        """
        profiles = {}
        for n in self.nodes:
            prof = n.get_node_profile(self)
            if prof:
                key = f"{n.kind}-{n.version}"
                profiles[key] = prof
        return profiles.values()

    def get_toponodes(self):
        toponodes = []
        for n in self.nodes:
            tn = n.get_toponode(self)
            if tn:
                toponodes.append(tn)
        return toponodes

    def get_topolinks(self):
        topolinks = []
        for ln in self.links:
            if ln.is_topolink():
                link_yaml = ln.get_topolink_yaml(self)
                if link_yaml:
                    topolinks.append(link_yaml)
        return topolinks

    def get_topolink_interfaces(self):
        interfaces = []
        for ln in self.links:
            if ln.is_topolink():
                intf1 = ln.node_1.get_topolink_interface(self, ln.intf_1, ln.node_2)
                intf2 = ln.node_2.get_topolink_interface(self, ln.intf_2, ln.node_1)
                if intf1:
                    interfaces.append(intf1)
                if intf2:
                    interfaces.append(intf2)
        return interfaces


def parse_topology_file(path: str) -> Topology:
    """
    Equivalent to old parse_topology function
    """
    logger.info(f"Parsing topology file '{path}'")
    if not os.path.isfile(path):
        logger.critical(f"Topology file '{path}' does not exist!")
        sys.exit(1)

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        logger.critical(f"File '{path}' is not valid JSON.")
        sys.exit(1)

    if data.get("type") != "clab":
        raise ValueError("Not a valid containerlab topology file (missing 'type=clab')")

    name = data["name"]
    mgmt_subnet = data["clab"]["config"]["mgmt"].get("ipv4-subnet")
    ssh_keys = data.get("ssh-pub-keys", [])
    file_path = ""

    # discover the file path from first node's label if present
    if data["nodes"]:
        first_key = next(iter(data["nodes"]))
        file_path = data["nodes"][first_key]["labels"].get("clab-topo-file", "")

    # build node objects
    node_objects = []
    for node_name, node_data in data["nodes"].items():
        image = node_data.get("image")
        version = None
        if image and ":" in image:
            version = image.split(":")[-1]
        config = {
            "kind": node_data["kind"],
            "type": node_data["labels"].get("clab-node-type", "ixrd2"),
            "version": version,
            "mgmt_ipv4": node_data.get("mgmt-ipv4-address"),
        }
        node_obj = create_node(node_name, config)
        if node_obj:
            node_objects.append(node_obj)

    # build link objects
    link_objects = []
    for link_info in data["links"]:
        a_node = link_info["a"]["node"]
        z_node = link_info["z"]["node"]
        # only build link if a_node & z_node exist among node_objects
        if any(n.name == a_node for n in node_objects) and any(
            n.name == z_node for n in node_objects
        ):
            endpoints = [
                f"{a_node}:{link_info['a']['interface']}",
                f"{z_node}:{link_info['z']['interface']}",
            ]
            ln = create_link(endpoints, node_objects)
            link_objects.append(ln)

    topo = Topology(
        name=name,
        mgmt_subnet=mgmt_subnet,
        ssh_keys=ssh_keys,
        nodes=node_objects,
        links=link_objects,
        clab_file_path=file_path,
    )
    # sanitize the name
    original = topo.name
    topo.name = topo.get_eda_safe_name()
    if topo.name != original:
        logger.info(f"Renamed topology '{original}' -> '{topo.name}' for EDA safety")
    return topo
