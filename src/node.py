import logging
from abc import ABC, abstractmethod

from src import helpers
from src.k8s_utils import ping_from_bsvr

# set up logging
logger = logging.getLogger(__name__)


class Node(ABC):
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
        Pings the node from the EDA bootstrap server pod

        Raises
        ------
        RuntimeError
            If ping fails or if the eda-bsvr pod cannot be found
        """
        logger.debug(f"Pinging {self.kind} node '{self.name}' with IP {self.mgmt_ipv4}")
        if ping_from_bsvr(self.mgmt_ipv4):
            logger.info(
                f"Ping to {self.kind} node '{self.name}' with IP {self.mgmt_ipv4} successful"
            )
            return True
        else:
            error_msg = f"Ping to {self.kind} node '{self.name}' with IP {self.mgmt_ipv4} failed"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    @abstractmethod
    def test_ssh(self):
        """
        Tests the SSH connectivity to the node.

        Returns
        -------
        True if the SSH was successful, raises exception otherwise
        """
        ...

    def get_node_name(self, topology):
        """
        Returns an EDA-safe name for a node
        """
        return helpers.normalize_name(self.name)

    @abstractmethod
    def get_profile_name(self, topology):
        """
        Returns an EDA-safe name for a node profile
        """
        ...

    @abstractmethod
    def get_default_node_type(self):
        """
        Allows to override the default node type, if no type was provided
        """
        ...

    @abstractmethod
    def get_platform(self):
        """
        Platform name to be used in the toponode resource
        """
        ...

    @abstractmethod
    def get_node_profile(self, topology):
        """
        Creates a node profile for this node kind & version. This method needs to be overwritten by nodes that support it

        Returns
        -------
        the rendered node-profile jinja template
        """
        ...

    @abstractmethod
    def get_toponode(self, topology):
        """
        Get as toponode. This method needs to be overwritten by nodes that support it
        """
        ...

    @abstractmethod
    def is_eda_supported(self):
        """
        Returns True if this node is supported as part of an EDA topology
        """
        ...

    @abstractmethod
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
        ...

    @abstractmethod
    def get_topolink_interface_name(self, topology, ifname):
        """
        Returns the name of this node's topolink with given interface
        """
        ...

    @abstractmethod
    def get_topolink_interface(self, topology, ifname, other_node):
        """
        Creates a topolink interface for this node and interface.

        Parameters
        ----------
        topology:   the parsed Topology
        ifname:     name of the topolink interface
        other_node: node at the other end of the topolink (used for description)

        Returns
        -------
        The rendered interface jinja template
        """
        ...

    @abstractmethod
    def needs_artifact(self):
        """
        Returns whether this node type needs an artifact to be created in EDA
        """
        ...

    @abstractmethod
    def get_artifact_name(self):
        """
        Returns the standardized artifact name for this node type and version.
        Should be implemented by node types that return True for needs_artifact()

        Returns
        -------
        str containing the artifact name or None if not supported
        """
        ...

    @abstractmethod
    def get_artifact_info(self):
        """
        Gets artifact information required for this node type.
        Should be implemented by node types that return True for needs_artifact()

        Returns
        -------
        Tuple of (artifact_name, filename, download_url) or (None, None, None) if not found
        """
        ...

    @abstractmethod
    def get_artifact_yaml(self, artifact_name, filename, download_url):
        """
        Returns the YAML definition for creating the artifact in EDA.
        Should be implemented by node types that return True for needs_artifact()

        Returns
        -------
        str containing the artifact YAML definition or None if not supported
        """
        ...


# import specific nodes down here to avoid circular dependencies
from src.node_srl import SRLNode  # noqa: E402

KIND_MAPPING = {
    "nokia_srlinux": "srl",
}

SUPPORTED_NODE_TYPES = {
    "srl": SRLNode,
}


def from_obj(name, python_object, kinds):
    """
    Parses a node from a Python object

    Parameters
    ----------
    name: the name of the node
    python_obj: the python object for this node parsed from the json input file
    kinds: the python object for the kinds in the topology file (not used for topology-data.json)

    Returns
    -------
    The parsed Node entity
    """
    logger.info(f"Parsing node with name '{name}'")
    original_kind = python_object.get("kind")
    if not original_kind:
        logger.warning(f"No kind specified for node '{name}', skipping")
        return None

    # Translate kind if needed
    kind = KIND_MAPPING.get(original_kind)
    if not kind:
        logger.debug(
            f"Unsupported kind '{original_kind}' for node '{name}', skipping. Supported kinds: {list(KIND_MAPPING.keys())}"
        )
        return None

    node_type = python_object.get("type", None)
    mgmt_ipv4 = python_object.get("mgmt-ipv4") or python_object.get("mgmt_ipv4")
    version = python_object.get("version")  # Get version directly if provided

    if not mgmt_ipv4:
        logger.warning(f"No management IP found for node {name}")
        return None

    # Create the appropriate node type using the mapping
    NodeClass = SUPPORTED_NODE_TYPES[kind]
    return NodeClass(name, kind, node_type, version, mgmt_ipv4)
