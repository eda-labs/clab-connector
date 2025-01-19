# clab_connector/models/topology.py

import logging
import os
import sys
import json

from clab_connector.models.node.factory import create_node
from clab_connector.models.link import create_link

logger = logging.getLogger(__name__)


class Topology:
    """
    Represents a containerlab topology.

    Parameters
    ----------
    name : str
        The name of the topology.
    mgmt_subnet : str
        The management IPv4 subnet for the topology.
    ssh_keys : list
        A list of SSH public keys.
    nodes : list
        A list of Node objects in the topology.
    links : list
        A list of Link objects in the topology.
    clab_file_path : str
        Path to the original containerlab file if available.
    """

    def __init__(self, name, mgmt_subnet, ssh_keys, nodes, links, clab_file_path=""):
        self.name = name
        self.mgmt_ipv4_subnet = mgmt_subnet
        self.ssh_pub_keys = ssh_keys
        self.nodes = nodes
        self.links = links
        self.clab_file_path = clab_file_path

    def __repr__(self):
        """
        Return a string representation of the topology.

        Returns
        -------
        str
            Description of the topology name, mgmt_subnet, number of nodes and links.
        """
        return (
            f"Topology(name={self.name}, mgmt_subnet={self.mgmt_ipv4_subnet}, "
            f"nodes={len(self.nodes)}, links={len(self.links)})"
        )

    def get_eda_safe_name(self):
        """
        Convert the topology name into a format safe for use in EDA.

        Returns
        -------
        str
            A name suitable for EDA resource naming.
        """
        safe = self.name.lower().replace("_", "-").replace(" ", "-")
        safe = "".join(c for c in safe if c.isalnum() or c in ".-").strip(".-")
        if not safe or not safe[0].isalnum():
            safe = "x" + safe
        if not safe[-1].isalnum():
            safe += "0"
        return safe

    def check_connectivity(self):
        """
        Attempt to ping each node's management IP from the bootstrap server.

        Raises
        ------
        RuntimeError
            If any node fails to respond to ping.
        """
        for node in self.nodes:
            node.ping()

    def get_node_profiles(self):
        """
        Generate NodeProfile YAML for all nodes that produce them.

        Returns
        -------
        list
            A list of node profile YAML strings.
        """
        profiles = {}
        for n in self.nodes:
            prof = n.get_node_profile(self)
            if prof:
                key = f"{n.kind}-{n.version}"
                profiles[key] = prof
        return profiles.values()

    def get_toponodes(self):
        """
        Generate TopoNode YAML for all EDA-supported nodes.

        Returns
        -------
        list
            A list of toponode YAML strings.
        """
        tnodes = []
        for n in self.nodes:
            tn = n.get_toponode(self)
            if tn:
                tnodes.append(tn)
        return tnodes

    def get_topolinks(self):
        """
        Generate TopoLink YAML for all EDA-supported links.

        Returns
        -------
        list
            A list of topolink YAML strings.
        """
        links = []
        for ln in self.links:
            if ln.is_topolink():
                link_yaml = ln.get_topolink_yaml(self)
                if link_yaml:
                    links.append(link_yaml)
        return links

    def get_topolink_interfaces(self):
        """
        Generate Interface YAML for each link endpoint (if EDA-supported).

        Returns
        -------
        list
            A list of interface YAML strings for the link endpoints.
        """
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
    Parse a containerlab topology JSON file and return a Topology object.

    Parameters
    ----------
    path : str
        Path to the containerlab topology JSON file.

    Returns
    -------
    Topology
        A populated Topology object.

    Raises
    ------
    SystemExit
        If the file does not exist or cannot be parsed.
    ValueError
        If the file is not recognized as a containerlab topology.
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

    if data["nodes"]:
        first_key = next(iter(data["nodes"]))
        file_path = data["nodes"][first_key]["labels"].get("clab-topo-file", "")

    # Create node objects
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

    # Create link objects
    link_objects = []
    for link_info in data["links"]:
        a_node = link_info["a"]["node"]
        z_node = link_info["z"]["node"]
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

    original = topo.name
    topo.name = topo.get_eda_safe_name()
    if topo.name != original:
        logger.info(f"Renamed topology '{original}' -> '{topo.name}' for EDA safety")
    return topo
