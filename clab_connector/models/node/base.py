# clab_connector/models/node/base.py

import logging

from clab_connector.utils import helpers
from clab_connector.clients.kubernetes.client import ping_from_bsvr

logger = logging.getLogger(__name__)


class Node:
    """
    Base Node class
    """

    def __init__(self, name, kind, node_type, version, mgmt_ipv4):
        self.name = name
        self.kind = kind
        self.node_type = node_type or self.get_default_node_type()
        self.version = version
        self.mgmt_ipv4 = mgmt_ipv4

    def __repr__(self):
        return (
            f"Node(name={self.name}, kind={self.kind}, type={self.node_type}, "
            f"version={self.version}, mgmt_ipv4={self.mgmt_ipv4})"
        )

    def ping(self):
        logger.debug(f"Pinging node '{self.name}' IP {self.mgmt_ipv4}")
        if ping_from_bsvr(self.mgmt_ipv4):
            logger.info(f"Ping to '{self.name}' ({self.mgmt_ipv4}) successful")
            return True
        else:
            msg = f"Ping to '{self.name}' ({self.mgmt_ipv4}) failed"
            logger.error(msg)
            raise RuntimeError(msg)

    def test_ssh(self):
        """
        Overridden by subclasses if they support SSH test
        """
        logger.info(f"SSH test not supported for {self}")

    def get_node_name(self, topology):
        """
        Return a name that is safe in EDA or K8s contexts
        """
        return helpers.normalize_name(self.name)

    def get_default_node_type(self):
        return None

    def get_platform(self):
        return "UNKNOWN"

    # By default, do not support EDA
    def is_eda_supported(self):
        return False

    def get_profile_name(self, topology):
        raise NotImplementedError("Must be implemented by subclass")

    def get_node_profile(self, topology):
        """
        Subclass: Return the rendered NodeProfile YAML or None if not supported
        """
        return None

    def get_toponode(self, topology):
        """
        Subclass: Return a toponode YAML or None if not supported
        """
        return None

    def get_interface_name_for_kind(self, ifname):
        return ifname

    def get_topolink_interface_name(self, topology, ifname):
        return (
            f"{self.get_node_name(topology)}-{self.get_interface_name_for_kind(ifname)}"
        )

    def get_topolink_interface(self, topology, ifname, other_node):
        """
        Subclass: Return the interface YAML if relevant
        """
        return None

    def needs_artifact(self):
        return False

    def get_artifact_name(self):
        return None

    def get_artifact_info(self):
        return (None, None, None)

    def get_artifact_yaml(self, artifact_name, filename, download_url):
        return None
