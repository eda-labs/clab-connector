import logging
import re
from typing import ClassVar

from clab_connector.utils import helpers
from clab_connector.utils.constants import SUBSTEP_INDENT

from .base import Node

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
    EDA_OPERATING_SYSTEM: ClassVar[str] = "sros"

    SUPPORTED_SCHEMA_PROFILES: ClassVar[dict[str, tuple[str, str]]] = {
        "24.10.r4": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-sros-v24.10.r4/sros-24.10.r4.zip"
        ),
        "24.10.r5": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-sros-v24.10.r5/sros-24.10.r5.zip"
        ),
        "24.10.r6": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-sros-v24.10.r6/sros-24.10.r6.zip"
        ),
        "25.3.r2": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-sros-v25.3.r2/sros-25.3.r2.zip"
        ),
        "25.7.r1": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-sros-v25.7.r1/sros-25.7.r1.zip"
        ),
        "25.7.r2": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-sros-25.7.r2/sros-25.7.r2.zip"
        ),
        "25.10.r1": (
            "https://github.com/nokia-eda/schema-profiles/"
            "releases/download/nokia-sros-25.10.r1/sros-25.10.r1.zip"
        ),
    }

    # Map of node types to their line card and MDA components
    SROS_COMPONENTS: ClassVar[dict[str, dict[str, dict[str, str]] | dict[str, int]]] = {
        "sr-1": {
            "lineCard": {"slot": "1", "type": "iom-1"},
            "mda": {"slot": "1-a", "type": "me12-100gb-qsfp28"},
            "connectors": 12,  # Number of connectors
        },
        "sr-1s": {
            "lineCard": {"slot": "1", "type": "xcm-1s"},
            "mda": {"slot": "1-a", "type": "s36-100gb-qsfp28"},
            "connectors": 36,
        },
        "sr-2s": {
            "lineCard": {"slot": "1", "type": "xcm-2s"},
            "mda": {"slot": "1-a", "type": "ms8-100gb-sfpdd+2-100gb-qsfp28"},
            "connectors": 10,
        },
        "sr-7s": {
            "lineCard": {"slot": "1", "type": "xcm-7s"},
            "mda": {"slot": "1-a", "type": "s36-100gb-qsfp28"},
            "connectors": 36,
        },
    }

    def _get_components(self):
        """
        Generate component information based on the node type.

        Returns
        -------
        list
            A list of component dictionaries for the TopoNode resource.
        """
        # Default to empty component list
        components = []

        # Normalize node type for lookup
        node_type = self.node_type.lower() if self.node_type else ""

        # Check if node type is in the mapping
        if node_type in self.SROS_COMPONENTS:
            # Get component info for this node type
            component_info = self.SROS_COMPONENTS[node_type]

            # Add line card component
            if "lineCard" in component_info:
                lc = component_info["lineCard"]
                components.append(
                    {"kind": "lineCard", "slot": lc["slot"], "type": lc["type"]}
                )

            # Add MDA component
            if "mda" in component_info:
                mda = component_info["mda"]
                components.append(
                    {"kind": "mda", "slot": mda["slot"], "type": mda["type"]}
                )

            # Add connector components
            if "connectors" in component_info:
                num_connectors = component_info["connectors"]
                for i in range(1, num_connectors + 1):
                    components.append(
                        {
                            "kind": "connector",
                            "slot": f"1-a-{i}",
                            "type": "c1-100g",  # Default connector type
                        }
                    )

        return components

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
            # For SR-1, SR-7, SR-1s, etc. - preserve the exact case
            # Only uppercase the "SR" part, keep the suffix as-is
            if "-" in self.node_type:
                parts = self.node_type.split("-", 1)
                return f"7750 {parts[0].upper()}-{parts[1]}"
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
        if not version:
            self._require_version()
        normalized = version.lower()
        return normalized

    def get_profile_name(self, topology):
        """
        Generate a NodeProfile name specific to this SROS node.
        Make sure it follows Kubernetes naming conventions (lowercase)
        and includes the topology name to ensure uniqueness.
        """
        # Convert version to lowercase to comply with K8s naming rules
        self._require_version()
        normalized_version = self._normalize_version(self.version)
        # Include the topology name in the profile name for uniqueness
        return f"{topology.get_eda_safe_name()}-sros-{normalized_version}"

    def get_node_profile(self, topology):
        """
        Render the NodeProfile YAML for this SROS node.
        """
        logger.debug(f"Rendering node profile for {self.name}")
        self._require_version()
        artifact_name = self.get_artifact_name()
        normalized_version = self._normalize_version(self.version)
        filename = f"sros-{normalized_version}.zip"

        # Extract version parts for LLM path, ensure consistent formatting
        version_short = normalized_version.replace(".", "-")

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
        logger.info(f"{SUBSTEP_INDENT}Creating toponode for {self.name}")
        self._require_version()
        # default role for SROS
        role_value = "backbone"

        # Allow override from containerlab topology labels
        if isinstance(self.labels, dict) and self.labels.get("role"):
            role_value = str(self.labels["role"])

        # Labels are already sanitized in topology.py
        user_labels = self.labels

        # Ensure all values are lowercase and valid
        node_name = self.get_node_name(topology)
        topo_name = topology.get_eda_safe_name()
        normalized_version = self._normalize_version(self.version)

        # Generate component information based on node type
        components = self._get_components()

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
            "mgmt_ip": self.mgmt_ipv4,
            "containerlab_label": "managedSros",
            "components": components,
        }
        return helpers.render_template("toponode.j2", data)

    def get_interface_name_for_kind(self, ifname):
        """Convert a containerlab interface name to the SR OS EDA format.

        Supported input formats:
        - "1-2-3"           -> "ethernet-1-b-3"
        - "1-2-c3-4"        ->  "ethernet-1-b-3-4" (mda>1) |  "1-1-c3-4" -> "ethernet-1-3-4" (mda=1)
        - "1-x2-1-3"        -> "ethernet-1-2-1-3"
        - "1-x2-1-c3-1"        -> "ethernet-1-2-1-3-1"

        Args:
            ifname: Interface name in containerlab format

        Returns:
            Interface name in SR OS EDA format
        """

        def mda_to_letter(mda_num):
            """Convert MDA number to letter (1->a, 2->b, etc.)"""
            return chr(96 + int(mda_num))

        # Define patterns with their transformation logic
        kind_patterns = {
            "nokia_srsim": [
                # Pattern: "1-2-3" -> "ethernet-1-b-3"
                (
                    r"^e(\d+)-(\d+)-(\d+)$",
                    lambda m: f"ethernet-{m[0]}-{mda_to_letter(m[1])}-{m[2]}",
                ),
                # Pattern: "1-2-c3-4" -> conditional format
                (
                    r"^e(\d+)-(\d+)-c(\d+)-(\d+)$",
                    lambda m: (
                        f"ethernet-{m[0]}-{m[2]}-{m[3]}"
                        if m[2] == "1"
                        else f"ethernet-{m[0]}-{mda_to_letter(m[1])}-{m[2]}-{m[3]}"
                    ),
                ),
                # Pattern: "1-x2-1-c3-1" -> "ethernet-1-2-1-c3-1"
                (
                    r"^e(\d+)-x(\d+)-(\d+)-c(\d+)-(\d+)$",
                    lambda m: (
                        f"ethernet-{m[0]}-{m[1]}-{mda_to_letter(m[2])}-{m[3]}-{m[4]}"
                    ),
                ),
                # Pattern: "1-x2-1-3" -> "ethernet-1-2-1-3"
                (
                    r"^e(\d+)-x(\d+)-(\d+)-(\d+)$",
                    lambda m: f"ethernet-{m[0]}-{m[1]}-{mda_to_letter(m[2])}-{m[3]}",
                ),
            ],
            "nokia_sros": [
                # Pattern: "1/2/3" -> "ethernet-1-b-3-1"
                (
                    r"^(\d+)/(\d+)/(\d+)$",
                    lambda m: f"ethernet-{m[0]}-{mda_to_letter(m[1])}-{m[2]}-1",
                ),
                # Pattern: "1/2/c3/4" -> conditional format
                (
                    r"^(\d+)/(\d+)/c(\d+)/(\d+)$",
                    lambda m: (
                        f"ethernet-{m[0]}-{m[2]}-{m[3]}"
                        if m[2] == "1"
                        else f"ethernet-{m[0]}-{mda_to_letter(m[1])}-{m[2]}-{m[3]}"
                    ),
                ),
                # Pattern: "1/x2/1/c3/1" -> "ethernet-1-2-1-c3-1"
                (
                    r"^(\d+)/x(\d+)/(\d+)/c(\d+)/(\d+)$",
                    lambda m: (
                        f"ethernet-{m[0]}-{m[1]}-{mda_to_letter(m[2])}-{m[3]}-{m[4]}"
                    ),
                ),
                # Pattern: "eth1" -> "ethernet-1-a-1-1"
                (r"^eth(\d+)$", lambda m: f"ethernet-1-a-{m[0]}-1"),
                # Pattern: "e1-2" -> "ethernet-1-a-2-1"
                (r"^e(\d+)-(\d+)$", lambda m: f"ethernet-{m[0]}-a-{m[1]}-1"),
                # Pattern: "lo1" -> "loopback-1"
                (r"^lo(\d+)$", lambda m: f"loopback-{m[0]}"),
            ],
        }
        # Try each pattern; if no pattern matches, return a safe normalized
        # name derived from the original interface string. This keeps the
        # function tolerant to unexpected formats while ensuring the result
        # is a valid resource name for EDA.
        patterns = kind_patterns.get(self.kind, [])
        for pattern, transformer in patterns:
            match = re.match(pattern, ifname)
            if match:
                return transformer(match.groups())

        # Fallback: return a sanitized version of the original ifname so
        # callers get a stable, valid identifier instead of an opaque/error
        # string.
        return helpers.normalize_name(ifname)

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
        Render the Interface CR YAML for an SROS link endpoint.
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
            logger.warning(
                f"{SUBSTEP_INDENT}No schema profile for version {normalized_version}"
            )
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
