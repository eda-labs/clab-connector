import logging
import re

from .base import Node
from clab_connector.utils import helpers

logger = logging.getLogger(__name__)


class NokiaSROSNode(Node):
    """
    Nokia SROS Node representation.

    This subclass implements specific logic for SROS nodes, including
    naming, interface mapping, and EDA resource generation.
    """

    SROS_USERNAME = "admin"
    SROS_PASSWORD = "NokiaSros1!"
    NODE_TYPE = "sros"
    GNMI_PORT = "57400"
    VERSION_PATH = ".system.information.version"
    YANG_PATH = "https://eda-asvr.eda-system.svc/eda-system/clab-schemaprofiles/{artifact_name}/{filename}"
    LLM_DB_PATH = "https://eda-asvr.eda-system.svc/eda-system/llm-dbs/llm-db-sros-ghcr-{version}/llm-embeddings-sros-{version_short}.tar.gz"

    # Mapping for EDA operating system
    EDA_OPERATING_SYSTEM = "sros"

    SUPPORTED_SCHEMA_PROFILES = {
        "25.3.r2": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-sros-v25.3.r2/sros-25.3.r2.zip"
        ),
    }

    def get_default_node_type(self):
        """
        Return the default node type for an SROS node.
        """
        return "sr7750"  # Default to 7750 SR router type

    def get_platform(self):
        """
        Return the platform name based on node type.

        Returns
        -------
        str
            The platform name (e.g. '7750 SR-1').
        """
        if self.node_type and self.node_type.lower().startswith("sr-"):
            # For SR-1, SR-7, etc.
            return f"7750 {self.node_type.upper()}"
        return "7750 SR"  # Default fallback

    def is_eda_supported(self):
        """
        Indicates SROS nodes are EDA-supported.
        """
        return True

    def _normalize_version(self, version):
        """
        Normalize version string to ensure consistent format between TopoNode and NodeProfile.
        """
        # Convert to lowercase for consistent handling
        normalized = version.lower()
        return normalized

    def get_profile_name(self, topology):
        """
        Generate a NodeProfile name specific to this SROS node.
        Make sure it follows Kubernetes naming conventions (lowercase)
        and includes the topology name to ensure uniqueness.
        """
        # Convert version to lowercase to comply with K8s naming rules
        normalized_version = self._normalize_version(self.version)
        # Include the topology name in the profile name for uniqueness
        return f"{topology.get_eda_safe_name()}-sros-{normalized_version}"

    def get_node_profile(self, topology):
        """
        Render the NodeProfile YAML for this SROS node.
        """
        logger.info(f"Rendering node profile for {self.name}")
        artifact_name = self.get_artifact_name()
        normalized_version = self._normalize_version(self.version)
        filename = f"sros-{normalized_version}.zip"

        # Extract version parts for LLM path, ensure consistent formatting
        version_short = normalized_version.replace(".", "-")

        data = {
            "namespace": f"clab-{topology.name}",
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
            "node_user": "admin-sros",
            "onboarding_password": "NokiaSros1!",
            "onboarding_username": "admin",
            "license": f"sros-ghcr-{normalized_version}-dummy-license",
            "llm_db": self.LLM_DB_PATH.format(
                version=normalized_version, version_short=version_short
            ),
        }
        return helpers.render_template("node-profile.j2", data)

    def get_toponode(self, topology):
        """
        Render the TopoNode YAML for this SROS node.
        """
        logger.info(f"Creating toponode for {self.name}")
        role_value = "dcgw"

        # Ensure all values are lowercase and valid
        node_name = self.get_node_name(topology)
        topo_name = topology.get_eda_safe_name()
        normalized_version = self._normalize_version(self.version)

        data = {
            "namespace": f"clab-{topology.name}",
            "node_name": node_name,
            "topology_name": topo_name,
            "role_value": role_value,
            "node_profile": self.get_profile_name(topology),
            "kind": self.EDA_OPERATING_SYSTEM,
            "platform": self.get_platform(),
            "sw_version": normalized_version,  # Use normalized version consistently
            "mgmt_ip": self.mgmt_ipv4,
            "containerlab_label": "managedSros"  # Added this line
        }
        return helpers.render_template("toponode.j2", data)

    def get_interface_name_for_kind(self, ifname):
        """
        Convert a containerlab interface name to an SROS style interface.
        """
        pattern = re.compile(r"^e(\d+)-(\d+)$")
        match = pattern.match(ifname)
        if match:
            return f"{match.group(1)}/1/{match.group(2)}"
        return ifname

    def get_topolink_interface(self, topology, ifname, other_node):
        """
        Render the Interface CR YAML for an SROS link endpoint.
        """
        logger.info(f"Creating topolink interface for {self.name}")
        data = {
            "namespace": f"clab-{topology.name}",
            "interface_name": self.get_topolink_interface_name(topology, ifname),
            "label_key": "eda.nokia.com/role",
            "label_value": "interSwitch",
            "encap_type": "'null'",
            "node_name": self.get_node_name(topology),
            "interface": self.get_interface_name_for_kind(ifname),
            "description": f"inter-switch link to {other_node.get_node_name(topology)}",
        }
        return helpers.render_template("interface.j2", data)

    def needs_artifact(self):
        """
        SROS nodes may require a YANG artifact.
        """
        return True

    def get_artifact_name(self):
        """
        Return a name for the SROS schema artifact.
        """
        normalized_version = self._normalize_version(self.version)
        return f"clab-sros-ghcr-{normalized_version}"

    def get_artifact_info(self):
        """
        Return artifact metadata for the SROS YANG schema file.
        """
        normalized_version = self._normalize_version(self.version)
        # Check if we have a supported schema for this normalized version
        if normalized_version not in self.SUPPORTED_SCHEMA_PROFILES:
            logger.warning(f"No schema profile for version {normalized_version}")
            return (None, None, None)

        artifact_name = self.get_artifact_name()
        filename = f"sros-{normalized_version}.zip"
        download_url = self.SUPPORTED_SCHEMA_PROFILES[normalized_version]
        return (artifact_name, filename, download_url)

    def get_artifact_yaml(self, artifact_name, filename, download_url):
        """
        Render the Artifact CR YAML for the SROS YANG schema.
        """
        data = {
            "artifact_name": artifact_name,
            "namespace": "eda-system",
            "artifact_filename": filename,
            "artifact_url": download_url,
        }
        return helpers.render_template("artifact.j2", data)