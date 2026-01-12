import logging
import re
from typing import ClassVar

from clab_connector.utils import helpers
from clab_connector.utils.constants import SUBSTEP_INDENT

from .base import Node

logger = logging.getLogger(__name__)


class AristaCEOSNode(Node):
    """
    Arista cEOS Node representation.

    This subclass implements specific logic for Arista cEOS nodes, including
    naming, interface mapping, and EDA resource generation.
    """

    CEOS_USERNAME = "admin"
    CEOS_PASSWORD = "admin"
    GNMI_PORT = "50051"
    YANG_PATH = "https://eda-asvr.eda-system.svc/eda-system/clab-schemaprofiles/{artifact_name}/{filename}"

    # Mapping for EDA operating system
    EDA_OPERATING_SYSTEM: ClassVar[str] = "eos"

    SUPPORTED_SCHEMA_PROFILES: ClassVar[dict[str, tuple[str, str]]] = {
        "4.33.2f": (
            "https://github.com/hellt/tmp/"
            "releases/download/v0.0.1-test1/eos-4.33.2f-v1.zip"
        ),
        "4.34.2f": (
            "https://github.com/hellt/tmp/"
            "releases/download/v0.0.1-test1/eos-4.34.2f-v1.zip"
        ),
    }

    def get_platform(self):
        """
        Return the platform name based on node type.

        """
        return "EOS"  # Default

    def is_eda_supported(self):
        """
        Indicates cEOS nodes are EDA-supported.
        """
        return True

    def _normalize_version(self, version):
        """
        Normalize version string to ensure consistent format between TopoNode and NodeProfile.
        """
        if not version:
            self._require_version()
        normalized = version.lower()
        return normalized

    def get_profile_name(self, topology):
        """
        Generate a NodeProfile name specific to this cEOS node.
        Make sure it follows Kubernetes naming conventions (lowercase)
        and includes the topology name to ensure uniqueness.
        """
        # Convert version to lowercase to comply with K8s naming rules
        self._require_version()
        normalized_version = self._normalize_version(self.version)
        # Include the topology name in the profile name for uniqueness
        return f"{topology.get_eda_safe_name()}-ceos-{normalized_version}"

    def get_node_profile(self, topology):
        """
        Render the NodeProfile YAML for this cEOS node.
        """
        logger.debug(f"Rendering node profile for {self.name}")
        self._require_version()
        artifact_name = self.get_artifact_name()
        normalized_version = self._normalize_version(self.version)
        filename = f"eos-{normalized_version}.zip"

        data = {
            "namespace": topology.namespace,
            "profile_name": self.get_profile_name(topology),
            "sw_version": normalized_version,  # Use normalized version consistently
            "gnmi_port": self.GNMI_PORT,
            "operating_system": self.EDA_OPERATING_SYSTEM,
            "version_path": "",
            "version_match": "",
            "yang_path": self.YANG_PATH.format(
                artifact_name=artifact_name, filename=filename
            ),
            "annotate": "false",
            "node_user": "admin-ceos",
            "onboarding_password": "admin",
            "onboarding_username": "admin",
        }
        return helpers.render_template("node-profile.j2", data)

    def get_toponode(self, topology):
        """
        Render the TopoNode YAML for this cEOS node.
        """
        logger.info(f"{SUBSTEP_INDENT}Creating toponode for {self.name}")
        self._require_version()
        # default role
        role_value = "leaf"
        nl = self.name.lower()
        if "spine" in nl:
            role_value = "spine"
        elif "borderleaf" in nl or "bl" in nl:
            role_value = "borderleaf"
        elif "dcgw" in nl:
            role_value = "dcgw"

        # Allow override from containerlab topology labels
        if isinstance(self.labels, dict) and self.labels.get("role"):
            role_value = str(self.labels["role"])
        # Sanitize role label value for Kubernetes
        role_value = helpers.sanitize_label_value(role_value)

        # Filter user labels to pass through (excludes reserved labels)
        user_labels = helpers.filter_user_labels(self.labels)

        # Ensure all values are lowercase and valid
        node_name = self.get_node_name(topology)
        topo_name = topology.get_eda_safe_name()
        normalized_version = self._normalize_version(self.version)

        data = {
            "namespace": topology.namespace,
            "node_name": node_name,
            "topology_name": topo_name,
            "role_value": role_value,
            "user_labels": user_labels,
            "node_profile": self.get_profile_name(topology),
            "kind": self.EDA_OPERATING_SYSTEM,
            "platform": self.get_platform(),
            "sw_version": normalized_version,
            "mgmt_ip": f"{self.mgmt_ipv4}/{self.mgmt_ipv4_prefix_length}",
            "containerlab_label": "managedEos",
        }
        return helpers.render_template("toponode.j2", data)

    def get_interface_name_for_kind(self, ifname):
        """
        Convert a containerlab interface name to an Arista cEOS style interface.

        Parameters
        ----------
        ifname : str
            Containerlab interface name, e.g., 'eth1_1'.

        Returns
        -------
        str
            Arista cEOS style name, e.g. 'ethernet-1-1'.
        """
        pattern = re.compile(r"^[a-zA-Z]+(\d+)_(\d+)$")
        match = pattern.match(ifname)
        if match:
            return f"ethernet-{match.group(1)}-{match.group(2)}"
        return ifname

    def get_topolink_interface_name(self, topology, ifname):
        """
        Generate a unique interface resource name for a link in EDA.
        Creates a valid Kubernetes resource name based on the EDA interface format.

        This normalizes complex interface names into valid resource names.
        """
        node_name = self.get_node_name(topology)
        eda_ifname = self.get_interface_name_for_kind(ifname)

        # No longer strip out the 'ethernet-' prefix to maintain consistency with SR Linux
        return f"{node_name}-{eda_ifname}"

    def get_topolink_interface(
        self,
        topology,
        ifname,
        other_node,
        edge_encapsulation: str | None = None,
        isl_encapsulation: str | None = None,
    ):
        """
        Render the Interface CR YAML for an cEOS link endpoint.
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
            "label_value": helpers.sanitize_label_value(role),
            "encap_type": encap_type,
            "node_name": self.get_node_name(topology),
            "interface": self.get_interface_name_for_kind(ifname),
            "description": f"{role} link to {peer_name}",
        }
        return helpers.render_template("interface.j2", data)

    def needs_artifact(self):
        """
        cEOS nodes may require a YANG artifact.
        """
        return True

    def get_artifact_name(self):
        """
        Return a name for the cEOS schema artifact.
        """
        normalized_version = self._normalize_version(self.version)
        return f"clab-eos-{normalized_version}"

    def get_artifact_info(self):
        """
        Return artifact metadata for the cEOS YANG schema file.
        """
        normalized_version = self._normalize_version(self.version)
        # Check if we have a supported schema for this normalized version
        if normalized_version not in self.SUPPORTED_SCHEMA_PROFILES:
            logger.warning(
                f"{SUBSTEP_INDENT}No schema profile for version {normalized_version}"
            )
            return (None, None, None)

        artifact_name = self.get_artifact_name()
        filename = f"eos-{normalized_version}.zip"
        download_url = self.SUPPORTED_SCHEMA_PROFILES[normalized_version]
        return (artifact_name, filename, download_url)

    def get_artifact_yaml(self, artifact_name, filename, download_url):
        """
        Render the Artifact CR YAML for the cEOS YANG schema.
        """
        data = {
            "artifact_name": artifact_name,
            "namespace": "eda-system",
            "artifact_filename": filename,
            "artifact_url": download_url,
        }
        return helpers.render_template("artifact.j2", data)
