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

    # Map of node types to their line card and MDA components
    SROS_COMPONENTS = {
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
                components.append({
                    "kind": "lineCard",
                    "slot": lc["slot"],
                    "type": lc["type"]
                })

            # Add MDA component
            if "mda" in component_info:
                mda = component_info["mda"]
                components.append({
                    "kind": "mda",
                    "slot": mda["slot"],
                    "type": mda["type"]
                })

            # Add connector components
            if "connectors" in component_info:
                num_connectors = component_info["connectors"]
                for i in range(1, num_connectors + 1):
                    components.append({
                        "kind": "connector",
                        "slot": f"1-a-{i}",
                        "type": "c1-100g"  # Default connector type
                    })

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

        # Generate component information based on node type
        components = self._get_components()

        data = {
            "namespace": f"clab-{topology.name}",
            "node_name": node_name,
            "topology_name": topo_name,
            "role_value": role_value,
            "node_profile": self.get_profile_name(topology),
            "kind": self.EDA_OPERATING_SYSTEM,
            "platform": self.get_platform(),
            "sw_version": normalized_version,
            "mgmt_ip": self.mgmt_ipv4,
            "containerlab_label": "managedSros",
            "components": components  # Add component information
        }
        return helpers.render_template("toponode.j2", data)

    def get_interface_name_for_kind(self, ifname):
        """
        Convert a containerlab interface name to an SR OS EDA-compatible interface name.

        Supports all SR OS interface naming conventions:
        - 1/1/1 → ethernet-1-a-1 (first linecard, MDA 'a', port 1)
        - 2/2/1 → ethernet-2-b-1 (second linecard, MDA 'b', port 1)
        - 1/1/c1/1 → ethernet-1-1-1 (breakout port with implicit MDA)
        - 1/1/c2/1 → ethernet-1-a-2-1 (breakout port with explicit MDA 'a')
        - 1/x1/1/1 → ethernet-1-1-a-1 (XIOM MDA)
        - lo0 → loopback-0
        - lag-10 → lag-10
        - eth3 → ethernet-1-a-3-1 (containerlab format)
        - e1-1 → ethernet-1-a-1-1 (containerlab format)
        """
        # Handle native SR OS port format with slashes: "1/1/1"
        slot_mda_port = re.compile(r"^(\d+)/(\d+)/(\d+)$")
        match = slot_mda_port.match(ifname)
        if match:
            slot = match.group(1)
            mda_num = int(match.group(2))
            port = match.group(3)

            # Convert MDA number to letter (1→'a', 2→'b', etc.)
            mda_letter = chr(96 + mda_num)  # ASCII 'a' is 97
            return f"ethernet-{slot}-{mda_letter}-{port}-1"

        # Handle breakout ports with implicit MDA: "1/1/c1/1"
        breakout_implicit = re.compile(r"^(\d+)/(\d+)/c(\d+)/(\d+)$")
        match = breakout_implicit.match(ifname)
        if match and match.group(2) == "1":  # Check for implicit MDA (1)
            slot = match.group(1)
            channel = match.group(3)
            port = match.group(4)
            return f"ethernet-{slot}-{channel}-{port}"

        # Handle breakout ports with explicit MDA: "1/1/c2/1"
        breakout_explicit = re.compile(r"^(\d+)/(\d+)/c(\d+)/(\d+)$")
        match = breakout_explicit.match(ifname)
        if match:
            slot = match.group(1)
            mda_num = int(match.group(2))
            channel = match.group(3)
            port = match.group(4)

            # Convert MDA number to letter
            mda_letter = chr(96 + mda_num)  # ASCII 'a' is 97
            return f"ethernet-{slot}-{mda_letter}-{channel}-{port}"

        # Handle XIOM MDA: "1/x1/1/1"
        xiom = re.compile(r"^(\d+)/x(\d+)/(\d+)/(\d+)$")
        match = xiom.match(ifname)
        if match:
            slot = match.group(1)
            xiom_id = match.group(2)
            mda_num = int(match.group(3))
            port = match.group(4)

            # Convert MDA number to letter
            mda_letter = chr(96 + mda_num)  # ASCII 'a' is 97
            return f"ethernet-{slot}-{xiom_id}-{mda_letter}-{port}"

        # Handle ethX format (commonly used in containerlab for SR OS)
        eth_pattern = re.compile(r"^eth(\d+)$")
        match = eth_pattern.match(ifname)
        if match:
            port_num = match.group(1)
            # Map to ethernet-1-a-{port}-1 format with connector
            return f"ethernet-1-a-{port_num}-1"

        # Handle standard containerlab eX-Y format
        e_pattern = re.compile(r"^e(\d+)-(\d+)$")
        match = e_pattern.match(ifname)
        if match:
            slot = match.group(1)
            port = match.group(2)
            # Add MDA 'a' and connector number
            return f"ethernet-{slot}-a-{port}-1"

        # Handle loopback interfaces
        lo_pattern = re.compile(r"^lo(\d+)$")
        match = lo_pattern.match(ifname)
        if match:
            return f"loopback-{match.group(1)}"  # Fixed: using match instead of lo_match

        # Handle LAG interfaces (already named correctly)
        lag_pattern = re.compile(r"^lag-\d+$")
        if lag_pattern.match(ifname):
            return ifname

        # If not matching any pattern, return the original
        return ifname

    def get_topolink_interface_name(self, topology, ifname):
        """
        Generate a unique interface resource name for a link in EDA.
        Creates a valid Kubernetes resource name based on the EDA interface format.

        This normalizes complex interface names into valid resource names.
        """
        node_name = self.get_node_name(topology)
        eda_ifname = self.get_interface_name_for_kind(ifname)

        # Convert to a resource-friendly name
        # We'll use dashes instead of slashes but keep the structure
        # For resource names, we can simplify by just removing 'ethernet-' prefix
        if eda_ifname.startswith('ethernet-'):
            resource_name = eda_ifname[9:]  # Remove 'ethernet-' prefix
        else:
            resource_name = eda_ifname

        return f"{node_name}-{resource_name}"

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