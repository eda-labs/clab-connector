# clab_connector/models/topology.py

import json
import logging
import os

from clab_connector.models.link import create_link
from clab_connector.models.node.base import Node
from clab_connector.models.node.factory import create_node
from clab_connector.utils.exceptions import ClabConnectorError, TopologyFileError

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

    def __init__(
        self, name, mgmt_subnet, mgmt_gw, ssh_keys, nodes, links, clab_file_path=""
    ):
        self.name = name
        self.mgmt_ipv4_subnet = mgmt_subnet
        self.mgmt_ipv4_gw = mgmt_gw
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

    def get_topolinks(self, skip_edge_links: bool = False):
        """Generate TopoLink YAML for all EDA-supported links.

        Parameters
        ----------
        skip_edge_links : bool, optional
            When True, omit TopoLink resources for edge links (links with only
            one EDA supported endpoint). Defaults to False.

        Returns
        -------
        list
            A list of topolink YAML strings.
        """
        links = []
        for ln in self.links:
            if skip_edge_links and ln.is_edge_link():
                continue
            if ln.is_topolink() or ln.is_edge_link():
                link_yaml = ln.get_topolink_yaml(self)
                if link_yaml:
                    links.append(link_yaml)
        return links

    def get_topolink_interfaces(self, skip_edge_link_interfaces: bool = False):
        """
        Generate Interface YAML for each link endpoint (if EDA-supported).

        Parameters
        ----------
        skip_edge_link_interfaces : bool, optional
            When True, interface resources for edge links (links where only one
            side is EDA-supported) are omitted. Defaults to False.

        Returns
        -------
        list
            A list of interface YAML strings for the link endpoints.
        """
        interfaces = []
        for ln in self.links:
            is_edge = ln.is_edge_link()
            for node, ifname, peer in (
                (ln.node_1, ln.intf_1, ln.node_2),
                (ln.node_2, ln.intf_2, ln.node_1),
            ):
                if node is None or not node.is_eda_supported():
                    continue
                if (
                    skip_edge_link_interfaces
                    and is_edge
                    and (peer is None or not peer.is_eda_supported())
                ):
                    continue
                intf_yaml = node.get_topolink_interface(self, ifname, peer)
                if intf_yaml:
                    interfaces.append(intf_yaml)
        return interfaces


def _load_topology_data(path: str) -> dict:
    if not os.path.isfile(path):
        logger.critical(f"Topology file '{path}' does not exist!")
        raise TopologyFileError(f"Topology file '{path}' does not exist!")

    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.critical(f"File '{path}' is not valid JSON.")
        raise TopologyFileError(f"File '{path}' is not valid JSON.") from e
    except OSError as e:
        logger.critical(f"Failed to read topology file '{path}': {e}")
        raise TopologyFileError(f"Failed to read topology file '{path}': {e}") from e


def _parse_nodes(nodes_data: dict) -> tuple[list[Node], dict[str, Node]]:
    node_objects: list[Node] = []
    all_nodes: dict[str, Node] = {}
    for node_name, node_data in nodes_data.items():
        image = node_data.get("image")
        version = image.split(":")[-1] if image and ":" in image else None
        config = {
            "kind": node_data["kind"],
            "type": node_data["labels"].get("clab-node-type", "ixrd2"),
            "version": version,
            "mgmt_ipv4": node_data.get("mgmt-ipv4-address"),
            "mgmt_ipv4_prefix_length": node_data.get("mgmt-ipv4-prefix-length"),
        }
        node_obj = create_node(node_name, config) or Node(
            name=node_name,
            kind=node_data["kind"],
            node_type=config.get("type"),
            version=version,
            mgmt_ipv4=node_data.get("mgmt-ipv4-address"),
            mgmt_ipv4_prefix_length=node_data.get("mgmt-ipv4-prefix-length"),
        )
        if node_obj.is_eda_supported():
            if not node_obj.version:
                raise ClabConnectorError(f"Node {node_name} is missing a version")
            node_objects.append(node_obj)
        all_nodes[node_name] = node_obj
    return node_objects, all_nodes


def _parse_links(links: list, all_nodes: dict[str, Node]) -> list:
    link_objects = []
    for link_info in links:
        a_name = link_info["a"]["node"]
        z_name = link_info["z"]["node"]
        if a_name not in all_nodes or z_name not in all_nodes:
            continue
        node_a = all_nodes[a_name]
        node_z = all_nodes[z_name]
        if not (node_a.is_eda_supported() or node_z.is_eda_supported()):
            continue
        endpoints = [
            f"{a_name}:{link_info['a']['interface']}",
            f"{z_name}:{link_info['z']['interface']}",
        ]
        ln = create_link(endpoints, list(all_nodes.values()))
        link_objects.append(ln)
    return link_objects


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
    TopologyFileError
        If the file does not exist or cannot be parsed.
    ValueError
        If the file is not recognized as a containerlab topology.
    """
    logger.info(f"Parsing topology file '{path}'")
    data = _load_topology_data(path)

    if data.get("type") != "clab":
        raise ValueError("Not a valid containerlab topology file (missing 'type=clab')")

    name = data["name"]
    mgmt_subnet = data["clab"]["config"]["mgmt"].get("ipv4-subnet")
    mgmt_gw = data["clab"]["config"]["mgmt"].get("ipv4-gw")
    ssh_keys = data.get("ssh-pub-keys", [])
    file_path = ""

    if data["nodes"]:
        first_key = next(iter(data["nodes"]))
        file_path = data["nodes"][first_key]["labels"].get("clab-topo-file", "")

    node_objects, all_nodes = _parse_nodes(data["nodes"])
    link_objects = _parse_links(data["links"], all_nodes)

    topo = Topology(
        name=name,
        mgmt_subnet=mgmt_subnet,
        mgmt_gw=mgmt_gw,
        ssh_keys=ssh_keys,
        nodes=node_objects,
        links=link_objects,
        clab_file_path=file_path,
    )

    original = topo.name
    topo.name = topo.get_eda_safe_name()
    if topo.name != original:
        logger.debug(f"Renamed topology '{original}' -> '{topo.name}' for EDA safety")
    return topo
