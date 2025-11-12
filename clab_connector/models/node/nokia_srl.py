# clab_connector/models/node/nokia_srl.py

import logging
import re
from typing import ClassVar

from clab_connector.utils import helpers
from clab_connector.utils.constants import SUBSTEP_INDENT

from .base import Node

logger = logging.getLogger(__name__)


class NokiaSRLinuxNode(Node):
    """
    Nokia SR Linux Node representation.

    This subclass implements specific logic for SR Linux nodes, including
    naming, interface mapping, and EDA resource generation.
    """

    SRL_USERNAME = "admin"
    SRL_PASSWORD = "NokiaSrl1!"
    NODE_TYPE = "srlinux"
    GNMI_PORT = "57410"
    VERSION_PATH = ".system.information.version"
    YANG_PATH = "https://eda-asvr.eda-system.svc/eda-system/clab-schemaprofiles/{artifact_name}/{filename}"
    SRL_IMAGE = "eda-system/srlimages/srlinux-{version}-bin/srlinux.bin"
    SRL_IMAGE_MD5 = "eda-system/srlimages/srlinux-{version}-bin/srlinux.bin.md5"
    LLM_DB_PATH = "https://eda-asvr.eda-system.svc/eda-system/llm-dbs/llm-db-srlinux-ghcr-{version}/llm-embeddings-srl-{version}.tar.gz"

    # Mapping for EDA operating system
    EDA_OPERATING_SYSTEM: ClassVar[str] = "srl"

    def __init__(
        self,
        name,
        kind,
        node_type,
        version,
        mgmt_ipv4,
        mgmt_ipv4_prefix_length,
    ):
        """Initialize a Nokia SR Linux node and check for deprecated type syntax."""
        super().__init__(
            name,
            kind,
            node_type,
            version,
            mgmt_ipv4,
            mgmt_ipv4_prefix_length,
        )

        # Check if using old syntax (without dash) and warn about deprecation
        if self.node_type and "-" not in self.node_type:
            if "ixr" in self.node_type.lower():
                logger.warning(
                    f"Node '{self.name}' uses deprecated type syntax '{self.node_type}'. "
                    f"Please update to '{self.node_type.replace('ixr', 'ixr-')}'. "
                    "Old syntax will be deprecated in early 2026."
                )
            elif self.node_type.lower() == "ixsa1":
                logger.warning(
                    f"Node '{self.name}' uses deprecated type syntax '{self.node_type}'. "
                    f"Please update to 'ixs-a1'. "
                    "Old syntax will be deprecated in early 2026."
                )

    SUPPORTED_SCHEMA_PROFILES: ClassVar[dict[str, str]] = {
        "24.10.1": (
            "https://github.com/nokia/srlinux-yang-models/"
            "releases/download/v24.10.1/srlinux-24.10.1-492.zip"
        ),
        "24.10.2": (
            "https://github.com/nokia/srlinux-yang-models/"
            "releases/download/v24.10.2/srlinux-24.10.2-357.zip"
        ),
        "24.10.3": (
            "https://github.com/nokia/srlinux-yang-models/"
            "releases/download/v24.10.3/srlinux-24.10.3-201.zip"
        ),
        "24.10.4": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-srl-24.10.4/srlinux-24.10.4-244.zip"
        ),
        "24.10.5": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-srl-24.10.5/srlinux-24.10.5-344.zip"
        ),
        "25.3.1": (
            "https://github.com/nokia/srlinux-yang-models/"
            "releases/download/v25.3.1/srlinux-25.3.1-149.zip"
        ),
        "25.3.2": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-srl-25.3.2/srlinux-25.3.2-312.zip"
        ),
        "25.3.3": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-srl-25.3.3/srlinux-25.3.3-158.zip"
        ),
        "25.7.1": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-srl-25.7.1/srlinux-25.7.1-187.zip"
        ),
        "25.7.2": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-srl-25.7.2/srlinux-25.7.2-266.zip"
        ),
        "25.10.1": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-srl-25.10.1/srlinux-25.10.1-399.zip"
        ),
    }

    def get_default_node_type(self):
        """
        Return the default node type for an SR Linux node.

        Returns
        -------
        str
            The default node type (e.g., "ixr-d3l").
        """
        return "ixr-d3l"

    def get_platform(self):
        """
        Return the platform name based on node type.

        Returns
        -------
        str
            The platform name (e.g. '7220 IXR-D3L').
        """
        m = re.match(r"(?i)(^ixr|^sxr|^ixs)-?(.*)$", self.node_type)
        if m:
            prefix = m.group(1) or ""
            suffix = m.group(2) or ""
            if prefix.lower().startswith("ixr") and suffix.lower().startswith(
                ("h", "d")
            ):
                return f"7220 IXR-{suffix.upper()}"
            elif prefix.lower().startswith("sxr"):
                return f"7730 IXR-{suffix.upper()}"
            elif prefix.lower().startswith("ixs"):
                return f"7215 IXS-{suffix.upper()}"
            else:
                return f"7250 IXR-{suffix.upper()}"
        else:
            return "NoMatchOnClabType"

    def is_eda_supported(self):
        """
        Indicates SR Linux nodes are EDA-supported.

        Returns
        -------
        bool
            True for SR Linux.
        """
        return True

    def get_profile_name(self, topology):
        """
        Generate a NodeProfile name specific to this SR Linux node.

        Parameters
        ----------
        topology : Topology
            The topology object.

        Returns
        -------
        str
            The NodeProfile name for EDA.
        """
        self._require_version()
        return f"{topology.get_eda_safe_name()}-{self.NODE_TYPE}-{self.version}"

    def get_node_profile(self, topology):
        """
        Render the NodeProfile YAML for this SR Linux node.
        """
        logger.debug(f"Rendering node profile for {self.name}")
        self._require_version()
        artifact_name = self.get_artifact_name()
        filename = f"srlinux-{self.version}.zip"

        data = {
            "namespace": topology.namespace,
            "profile_name": self.get_profile_name(topology),
            "sw_version": self.version,
            "gnmi_port": self.GNMI_PORT,
            "operating_system": self.EDA_OPERATING_SYSTEM,
            "version_path": self.VERSION_PATH,
            "version_match": "v{}.*".format(self.version.replace(".", "\\.")),
            "yang_path": self.YANG_PATH.format(
                artifact_name=artifact_name, filename=filename
            ),
            "node_user": "admin",
            "onboarding_password": self.SRL_PASSWORD,
            "onboarding_username": self.SRL_USERNAME,
            "sw_image": self.SRL_IMAGE.format(version=self.version),
            "sw_image_md5": self.SRL_IMAGE_MD5.format(version=self.version),
            "llm_db": self.LLM_DB_PATH.format(version=self.version),
        }
        return helpers.render_template("node-profile.j2", data)

    def get_toponode(self, topology):
        """
        Render the TopoNode YAML for this SR Linux node.
        """
        logger.info(f"{SUBSTEP_INDENT}Creating toponode for {self.name}")
        self._require_version()
        role_value = "leaf"
        nl = self.name.lower()
        if "spine" in nl:
            role_value = "spine"
        elif "borderleaf" in nl or "bl" in nl:
            role_value = "borderleaf"
        elif "dcgw" in nl:
            role_value = "dcgw"

        data = {
            "namespace": topology.namespace,
            "node_name": self.get_node_name(topology),
            "topology_name": topology.get_eda_safe_name(),
            "role_value": role_value,
            "node_profile": self.get_profile_name(topology),
            "kind": self.EDA_OPERATING_SYSTEM,
            "platform": self.get_platform(),
            "sw_version": self.version,
            "mgmt_ip": self.mgmt_ipv4,
            "containerlab_label": "managedSrl",
        }
        return helpers.render_template("toponode.j2", data)

    def get_interface_name_for_kind(self, ifname):
        """
        Convert a containerlab interface name to an SR Linux style interface.

        Parameters
        ----------
        ifname : str
            Containerlab interface name, e.g., 'e1-1'.

        Returns
        -------
        str
            SR Linux style name, e.g. 'ethernet-1-1'.
        """
        pattern = re.compile(r"^e(\d+)-(\d+)$")
        match = pattern.match(ifname)
        if match:
            return f"ethernet-{match.group(1)}-{match.group(2)}"
        return ifname

    def get_topolink_interface(
        self,
        topology,
        ifname,
        other_node,
        edge_encapsulation: str | None = None,
        isl_encapsulation: str | None = None,
    ):
        """
        Render the Interface CR YAML for an SR Linux link endpoint.

        Parameters
        ----------
        topology : Topology
            The topology object.
        ifname : str
            The containerlab interface name on this node.
        other_node : Node
            The peer node.

        Returns
        -------
        str
            The rendered Interface CR YAML.
        """
        logger.debug(f"{SUBSTEP_INDENT}Creating topolink interface for {self.name}")
        role = "interSwitch"
        if other_node is None or not other_node.is_eda_supported():
            role = "edge"
        peer_name = (
            other_node.get_node_name(topology)
            if other_node is not None
            else "external-endpoint"
        )
        if role == "edge":
            encap_type = "dot1q" if edge_encapsulation == "dot1q" else None
        else:
            encap_type = "dot1q" if isl_encapsulation == "dot1q" else None

        data = {
            "namespace": topology.namespace,
            "interface_name": self.get_topolink_interface_name(topology, ifname),
            "label_key": "eda.nokia.com/role",
            "label_value": role,
            "encap_type": encap_type,
            "node_name": self.get_node_name(topology),
            "interface": self.get_interface_name_for_kind(ifname),
            "description": f"{role} link to {peer_name}",
        }
        return helpers.render_template("interface.j2", data)

    def needs_artifact(self):
        """
        SR Linux nodes may require a YANG artifact.

        Returns
        -------
        bool
            True if an artifact is needed based on the version.
        """
        return True

    def get_artifact_name(self):
        """
        Return a name for the SR Linux schema artifact.

        Returns
        -------
        str
            A string such as 'clab-srlinux-24.10.1'.
        """
        return f"clab-srlinux-{self.version}"

    def get_artifact_info(self):
        """
        Return artifact metadata for the SR Linux YANG schema file.

        Returns
        -------
        tuple
            (artifact_name, filename, download_url)
        """
        if self.version not in self.SUPPORTED_SCHEMA_PROFILES:
            logger.warning(
                f"{SUBSTEP_INDENT}No schema profile for version {self.version}"
            )
            return (None, None, None)
        artifact_name = self.get_artifact_name()
        filename = f"srlinux-{self.version}.zip"
        download_url = self.SUPPORTED_SCHEMA_PROFILES[self.version]
        return (artifact_name, filename, download_url)

    def get_artifact_yaml(self, artifact_name, filename, download_url):
        """
        Render the Artifact CR YAML for the SR Linux YANG schema.

        Parameters
        ----------
        artifact_name : str
            The name of the artifact in EDA.
        filename : str
            The artifact file name.
        download_url : str
            The download URL of the artifact file.

        Returns
        -------
        str
            The rendered Artifact CR YAML.
        """
        data = {
            "artifact_name": artifact_name,
            "namespace": "eda-system",
            "artifact_filename": filename,
            "artifact_url": download_url,
        }
        return helpers.render_template("artifact.j2", data)
