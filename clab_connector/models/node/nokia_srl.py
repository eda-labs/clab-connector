# clab_connector/models/node/nokia_srl.py

import logging
import re

from .base import Node
from clab_connector.utils import helpers

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

    # Mapping for EDA operating system
    EDA_OPERATING_SYSTEM = "srl"

    SUPPORTED_SCHEMA_PROFILES = {
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
        )
    }

    def get_default_node_type(self):
        """
        Return the default node type for an SR Linux node.

        Returns
        -------
        str
            The default node type (e.g., "ixrd3l").
        """
        return "ixrd3l"

    def get_platform(self):
        """
        Return the platform name based on node type.

        Returns
        -------
        str
            The platform name (e.g. '7220 IXR-D3L').
        """
        t = self.node_type.replace("ixr", "")
        return f"7220 IXR-{t.upper()}"

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
        return f"{topology.get_eda_safe_name()}-{self.NODE_TYPE}-{self.version}"

    def get_node_profile(self, topology):
        """
        Render the NodeProfile YAML for this SR Linux node.

        Parameters
        ----------
        topology : Topology
            The topology object.

        Returns
        -------
        str
            The rendered NodeProfile YAML.
        """
        logger.info(f"Rendering node profile for {self.name}")
        artifact_name = self.get_artifact_name()
        filename = f"srlinux-{self.version}.zip"

        data = {
            "namespace": f"clab-{topology.name}",
            "profile_name": self.get_profile_name(topology),
            "sw_version": self.version,
            "gnmi_port": self.GNMI_PORT,
            "operating_system": self.EDA_OPERATING_SYSTEM,
            "version_path": self.VERSION_PATH,
            "version_match": "v{}.*".format(self.version.replace(".", "\.")),
            "yang_path": self.YANG_PATH.format(
                artifact_name=artifact_name, filename=filename
            ),
            "node_user": self.SRL_USERNAME,
            "onboarding_password": self.SRL_PASSWORD,
            "onboarding_username": self.SRL_USERNAME,
            "sw_image": self.SRL_IMAGE.format(version=self.version),
            "sw_image_md5": self.SRL_IMAGE_MD5.format(version=self.version),
        }
        return helpers.render_template("node-profile.j2", data)

    def get_toponode(self, topology):
        """
        Render the TopoNode YAML for this SR Linux node.

        Parameters
        ----------
        topology : Topology
            The topology object.

        Returns
        -------
        str
            The rendered TopoNode YAML.
        """
        logger.info(f"Creating toponode for {self.name}")
        role_value = "leaf"
        nl = self.name.lower()
        if "spine" in nl:
            role_value = "spine"
        elif "borderleaf" in nl or "bl" in nl:
            role_value = "borderleaf"
        elif "dcgw" in nl:
            role_value = "dcgw"

        data = {
            "namespace": f"clab-{topology.name}",
            "node_name": self.get_node_name(topology),
            "topology_name": topology.get_eda_safe_name(),
            "role_value": role_value,
            "node_profile": self.get_profile_name(topology),
            "kind": self.EDA_OPERATING_SYSTEM,
            "platform": self.get_platform(),
            "sw_version": self.version,
            "mgmt_ip": self.mgmt_ipv4,
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

    def get_topolink_interface(self, topology, ifname, other_node):
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
            logger.warning(f"No schema profile for version {self.version}")
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
