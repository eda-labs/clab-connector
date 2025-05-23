# clab_connector/models/node/base.py

import logging

from clab_connector.utils import helpers
from clab_connector.clients.kubernetes.client import ping_from_bsvr

logger = logging.getLogger(__name__)


class Node:
    """
    Base Node class for representing a generic containerlab node.

    Parameters
    ----------
    name : str
        The name of the node.
    kind : str
        The kind of the node (e.g. nokia_srlinux).
    node_type : str
        The specific node type (e.g. ixrd2).
    version : str
        The software version of the node.
    mgmt_ipv4 : str
        The management IPv4 address of the node.
    """

    def __init__(self, name, kind, node_type, version, mgmt_ipv4):
        self.name = name
        self.kind = kind
        self.node_type = node_type or self.get_default_node_type()
        self.version = version
        self.mgmt_ipv4 = mgmt_ipv4

    def __repr__(self):
        """
        Return a string representation of the node.

        Returns
        -------
        str
            A string describing the node and its parameters.
        """
        return (
            f"Node(name={self.name}, kind={self.kind}, type={self.node_type}, "
            f"version={self.version}, mgmt_ipv4={self.mgmt_ipv4})"
        )

    def ping(self):
        """
        Attempt to ping the node from the EDA bootstrap server (bsvr).

        Returns
        -------
        bool
            True if the ping is successful, raises a RuntimeError otherwise.
        """
        logger.debug(f"Pinging node '{self.name}' IP {self.mgmt_ipv4}")
        if ping_from_bsvr(self.mgmt_ipv4):
            logger.debug(f"Ping to '{self.name}' ({self.mgmt_ipv4}) successful")
            return True
        else:
            msg = f"Ping to '{self.name}' ({self.mgmt_ipv4}) failed"
            logger.error(msg)
            raise RuntimeError(msg)

    def get_node_name(self, topology):
        """
        Generate a name suitable for EDA resources, based on the node name.

        Parameters
        ----------
        topology : Topology
            The topology the node belongs to.

        Returns
        -------
        str
            A normalized node name safe for EDA.
        """
        return helpers.normalize_name(self.name)

    def get_default_node_type(self):
        """
        Get the default node type if none is specified.

        Returns
        -------
        str or None
            A default node type or None.
        """
        return None

    def get_platform(self):
        """
        Return the platform name for the node.

        Returns
        -------
        str
            The platform name (default 'UNKNOWN').
        """
        return "UNKNOWN"

    def is_eda_supported(self):
        """
        Check whether the node kind is supported by EDA.

        Returns
        -------
        bool
            True if supported, False otherwise.
        """
        return False

    def get_profile_name(self, topology):
        """
        Get the name of the NodeProfile for this node.

        Parameters
        ----------
        topology : Topology
            The topology this node belongs to.

        Returns
        -------
        str
            The NodeProfile name for EDA resource creation.

        Raises
        ------
        NotImplementedError
            Must be implemented by subclasses.
        """
        raise NotImplementedError("Must be implemented by subclass")

    def get_node_profile(self, topology):
        """
        Render and return NodeProfile YAML for the node.

        Parameters
        ----------
        topology : Topology
            The topology the node belongs to.

        Returns
        -------
        str or None
            The rendered NodeProfile YAML, or None if not applicable.
        """
        return None

    def get_toponode(self, topology):
        """
        Render and return TopoNode YAML for the node.

        Parameters
        ----------
        topology : Topology
            The topology the node belongs to.

        Returns
        -------
        str or None
            The rendered TopoNode YAML, or None if not applicable.
        """
        return None

    def get_interface_name_for_kind(self, ifname):
        """
        Convert an interface name from a containerlab style to EDA style.

        Parameters
        ----------
        ifname : str
            The interface name in containerlab format.

        Returns
        -------
        str
            A suitable interface name for EDA.
        """
        return ifname

    def get_topolink_interface_name(self, topology, ifname):
        """
        Generate a unique interface resource name for a link.

        Parameters
        ----------
        topology : Topology
            The topology that this node belongs to.
        ifname : str
            The interface name (containerlab style).

        Returns
        -------
        str
            The name that EDA will use for this interface resource.
        """
        return (
            f"{self.get_node_name(topology)}-{self.get_interface_name_for_kind(ifname)}"
        )

    def get_topolink_interface(self, topology, ifname, other_node):
        """
        Render and return the interface resource YAML (Interface CR) for a link endpoint.

        Parameters
        ----------
        topology : Topology
            The topology that this node belongs to.
        ifname : str
            The interface name on this node (containerlab style).
        other_node : Node
            The peer node at the other end of the link.

        Returns
        -------
        str or None
            The rendered Interface CR YAML, or None if not applicable.
        """
        return None

    def needs_artifact(self):
        """
        Determine if this node requires a schema or binary artifact in EDA.

        Returns
        -------
        bool
            True if an artifact is needed, False otherwise.
        """
        return False

    def get_artifact_name(self):
        """
        Return the artifact name if needed by the node.

        Returns
        -------
        str or None
            The artifact name, or None if not needed.
        """
        return None

    def get_artifact_info(self):
        """
        Return the artifact name, filename, and download URL if needed.

        Returns
        -------
        tuple
            (artifact_name, filename, download_url) or (None, None, None).
        """
        return (None, None, None)

    def get_artifact_yaml(self, artifact_name, filename, download_url):
        """
        Render and return an Artifact CR YAML for this node.

        Parameters
        ----------
        artifact_name : str
            The name of the artifact in EDA.
        filename : str
            The artifact file name.
        download_url : str
            The source URL of the artifact file.

        Returns
        -------
        str or None
            The rendered Artifact CR YAML, or None if not applicable.
        """
        return None
