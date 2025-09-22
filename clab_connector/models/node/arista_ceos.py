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
            "releases/download/v0.0.1-test1/eos-4.33.2f.zip"
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
        role_value = "leaf"
        nl = self.name.lower()
        if "spine" in nl:
            role_value = "spine"
        elif "borderleaf" in nl or "bl" in nl:
            role_value = "borderleaf"
        elif "dcgw" in nl:
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
        # Accept both ethX_Y/etX_Y and short ethX/etX, mapping to ethernet-X-Y
        # Examples:
        #   eth1_1 -> ethernet-1-1
        #   et2_3  -> ethernet-2-3
        #   eth5   -> ethernet-5-1 (default breakout '1')
        #   et7    -> ethernet-7-1
        # Already EDA style (ethernet-1-1) is returned as-is
        m = re.match(r"^ethernet-(\d+)-(\d+)$", ifname, flags=re.IGNORECASE)
        if m:
            return f"ethernet-{m.group(1)}-{m.group(2)}"

        m = re.match(r"^[a-zA-Z]+(\d+)_(\d+)$", ifname)
        if m:
            return f"ethernet-{m.group(1)}-{m.group(2)}"

        m = re.match(r"^(?:eth|et)(\d+)$", ifname, flags=re.IGNORECASE)
        if m:
            return f"ethernet-{m.group(1)}-1"

        return ifname

    def get_link_name_interface_token(self, ifname: str) -> str:
        """
        Normalize interface token used in TopoLink resource name so that
        short-form names (e.g., 'eth1') resolve to the same token as
        long-form names (e.g., 'eth1_1'). This keeps manifests identical
        regardless of which form the topology used.

        We deliberately keep the token in containerlab style (ethX_Y) to
        preserve existing link names where 'ethX_Y' was used.
        """
        # ethX_Y or etX_Y -> keep as-is
        if re.match(r"^(?:eth|et)\d+_\d+$", ifname, flags=re.IGNORECASE):
            return ifname

        # ethX or etX -> normalize to ethX_1 / etX_1
        m = re.match(r"^(eth|et)(\d+)$", ifname, flags=re.IGNORECASE)
        if m:
            return f"{m.group(1)}{m.group(2)}_1"

        # If already in EDA style, convert to ethX_Y token for stability
        m = re.match(r"^ethernet-(\d+)-(\d+)$", ifname, flags=re.IGNORECASE)
        if m:
            return f"eth{m.group(1)}_{m.group(2)}"

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

    def get_topolink_interface(self, topology, ifname, other_node):
        """
        Render the Interface CR YAML for an cEOS link endpoint.
        """
        logger.debug(f"{SUBSTEP_INDENT}Creating topolink interface for {self.name}")
        role = "interSwitch"
        if other_node is None or not other_node.is_eda_supported():
            role = "edge"
        data = {
            "namespace": f"clab-{topology.name}",
            "interface_name": self.get_topolink_interface_name(topology, ifname),
            "label_key": "eda.nokia.com/role",
            "label_value": role,
            "encap_type": "'null'",
            "node_name": self.get_node_name(topology),
            "interface": self.get_interface_name_for_kind(ifname),
            "description": f"{role} link to {other_node.get_node_name(topology)}",
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
