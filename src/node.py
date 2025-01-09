import os
import logging

# set up logging
logger = logging.getLogger(__name__)


class Node:
    def __init__(self, name, kind, node_type, version, mgmt_ipv4):
        self.name = name
        self.kind = kind

        self.node_type = node_type
        if node_type is None:
            node_type = self.get_default_node_type()

        self.version = version
        self.mgmt_ipv4 = mgmt_ipv4

    def __repr__(self):
        return f"Node(name={self.name}, kind={self.kind}, type={self.node_type}, version={self.version}, mgmt_ipv4={self.mgmt_ipv4})"

    def ping(self):
        """
        Pings the node

        Returns
        -------
        True if the ping was successful, False otherwise
        """
        logger.debug(f"Pinging {self.kind} node '{self.name}' with IP {self.mgmt_ipv4}")
        param = "-n" if os.sys.platform.lower() == "win32" else "-c"
        response = os.system(f"ping {param} 1 {self.mgmt_ipv4} > /dev/null 2>&1")

        if response == 0:
            logger.info(
                f"Ping to {self.kind} node '{self.name}' with IP {self.mgmt_ipv4} successfull"
            )
        else:
            logger.warning(
                f"Ping to {self.kind} node '{self.name}' with IP {self.mgmt_ipv4} not successfull"
            )

        return response == 0

    def test_ssh(self):
        """
        Tests the SSH connectivity to the node. This method needs to be overwritten by nodes that support it

        Returns
        -------
        True if the SSH was successful, raises exception otherwise
        """
        logger.info(f"Testing SSH is not supported for {self}")

    def get_node_name(self, topology):
        """
        Returns an EDA-safe name for a node
        """
        return f"{topology.get_eda_safe_name()}-{self.name}"

    def get_profile_name(self, topology):
        """
        Returns an EDA-safe name for a node profile
        """
        raise Exception("Node not supported in EDA")

    def get_default_node_type(self):
        """
        Allows to override the default node type, if no type was provided
        """
        return None

    def get_platform(self):
        """
        Platform name to be used in the bootstrap node resource
        """
        return "UNKOWN"

    def get_node_profile(self, topology):
        """
        Creates a node profile for this node kind & version. This method needs to be overwritten by nodes that support it

        Returns
        -------
        the rendered node-profile jinja template
        """
        logger.info(f"Node profile is not supported for {self}")
        return None

    def bootstrap_config(self):
        """
        Pushes the bootstrap configuration to the node. This method needs to be overwritten by nodes that support it
        """
        logger.info(f"Pushing bootstrap config to the node not supported for {self}")

    def get_bootstrap_node(self, topology):
        """
        Creates a bootstrap node for this node. This method needs to be overwritten by nodes that support it
        """
        logger.info(f"Bootstrap node is not supported for {self}")
        return None

    def is_eda_supported(self):
        """
        Returns True if this node is supported as part of an EDA topology
        """
        return False

    def get_interface_name_for_kind(self, ifname):
        """
        Converts the containerlab name of an interface to the node's naming convention

        Parameters
        ----------
        ifname: name of the interface as specified in the containerlab topology file

        Returns
        -------
        The name of the interface as accepted by the node
        """
        return ifname

    def get_system_interface_name(self, topology):
        """
        Returns the name of this node's system interface, if supported
        """
        logger.info(f"Getting system interface name is not supported for {self}")
        return None

    def get_system_interface(self, topology):
        """
        Creates a system interface for this node. This method needs to be overwritten by nodes that support it

        Parameters
        ----------
        topology: the parsed Topology

        Returns
        -------
        The rendered interface jinja template
        """
        logger.info(f"System interface is not supported for {self}")
        return None

    def get_topolink_interface_name(self, topology, ifname):
        """
        Returns the name of this node's topolink with given interface
        """
        return (
            f"{self.get_node_name(topology)}-{self.get_interface_name_for_kind(ifname)}"
        )

    def get_topolink_interface(self, topology, ifname, other_node):
        """
        Creates a topolink interface for this node and interface. This method needs to be overwritten by nodes that support it

        Parameters
        ----------
        topology:   the parsed Topology
        ifname:     name of the topolink interface
        other_node: node at the other end of the topolink (used for description)

        Returns
        -------
        The rendered interface jinja template
        """
        logger.info(f"Topolink interface is not supported for {self}")
        return None

    def needs_artifact(self):
        """
        Returns whether this node type needs an artifact to be created in EDA
        """
        return False

    def get_artifact_info(self):
        """
        Gets artifact information required for this node type.
        Should be implemented by node types that return True for needs_artifact()

        Returns
        -------
        Tuple of (artifact_name, filename, download_url) or (None, None, None) if not found
        """
        return None, None, None

    def get_artifact_yaml(self, artifact_name, filename, download_url):
        """
        Returns the YAML definition for creating the artifact in EDA.
        Should be implemented by node types that return True for needs_artifact()

        Returns
        -------
        str containing the artifact YAML definition or None if not supported
        """
        return None


# import specific nodes down here to avoid circular dependencies
from src.node_srl import SRLNode  # noqa: E402


def from_obj(name, python_object, kinds):
    """
    Parses a node from a Python object

    Parameters
    ----------
    name: the name of the node
    python_obj: the python object for this node parsed from the yaml input file
    kinds: the python object for the kinds in the topology yaml file

    Returns
    -------
    The parsed Node entity
    """
    logger.info(f"Parsing node with name '{name}'")
    kind = python_object["kind"]
    node_type = python_object["type"] if "type" in python_object else None

    # support for legacy containerlab files
    if "mgmt_ipv4" in python_object:
        logger.warning(
            "Property mgmt_ipv4 is deprecated, please use mgmt-ipv4 in your clab topology file"
        )
        mgmt_ipv4 = python_object["mgmt_ipv4"]
    else:
        mgmt_ipv4 = python_object["mgmt-ipv4"]

    # check if the kind is in the kinds object
    if kind not in kinds:
        logger.warning(
            f"Could not find kind '{kind}' for node '{name}' in the topology file"
        )
        kind = None
        version = None
    else:
        image = kinds[kind]["image"]
        parts = image.split(":")
        if len(parts) != 2:
            logger.warning(f"Could not parse version from node image '{image}'")
            version = None
        else:
            version = parts[1]

    if kind == "srl" or kind == "nokia_srlinux":
        return SRLNode(name, kind, node_type, version, mgmt_ipv4)

    return Node(name, kind, node_type, version, mgmt_ipv4)
