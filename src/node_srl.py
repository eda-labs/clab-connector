import logging
import re
import socket

from paramiko import (
    AuthenticationException,
    AutoAddPolicy,
    BadHostKeyException,
    SSHClient,
    SSHException,
)

import src.helpers as helpers
from src.node import Node

# set up logging
logger = logging.getLogger(__name__)


class SRLNode(Node):
    SRL_USERNAME = "admin"
    SRL_PASSWORD = "NokiaSrl1!"
    NODE_TYPE = "srlinux"
    GNMI_PORT = "57410"
    VERSION_PATH = ".system.information.version"
    YANG_PATH = "https://eda-asvr.eda-system.svc/eda-system/clab-schemaprofiles/{artifact_name}/{filename}"
    SRL_IMAGE = "eda-system/srlimages/srlinux-{version}-bin/srlinux.bin"
    SRL_IMAGE_MD5 = "eda-system/srlimages/srlinux-{version}-bin/srlinux.bin.md5"

    def __init__(self, name, kind, node_type, version, mgmt_ipv4):
        super().__init__(name, kind, node_type, version, mgmt_ipv4)
        # Add cache for artifact info
        self._artifact_info = None

    def test_ssh(self):
        """
        Tests the SSH connectivity to the node

        Returns
        -------
        True if the SSH was successful, False otherwise
        """
        logger.debug(
            f"Testing whether SSH works for node '{self.name}' with IP {self.mgmt_ipv4}"
        )
        ssh = SSHClient()
        ssh.set_missing_host_key_policy(AutoAddPolicy())

        try:
            ssh.connect(
                self.mgmt_ipv4,
                username=self.SRL_USERNAME,
                password=self.SRL_PASSWORD,
                allow_agent=False,
            )
            logger.info(
                f"SSH test to {self.kind} node '{self.name}' with IP {self.mgmt_ipv4} was successful"
            )
            return True
        except (
            BadHostKeyException,
            AuthenticationException,
            SSHException,
            socket.error,
        ) as e:
            logger.critical(f"Could not connect to node {self}, exception: {e}")
            raise e

    def get_default_node_type(self):
        """
        Allows to override the default node type, if no type was provided
        """
        return "ixrd3l"

    def get_platform(self):
        """
        Platform name to be used in the toponode resource
        """
        t = self.node_type.replace("ixr", "")
        return f"7220 IXR-{t.upper()}"

    def get_profile_name(self, topology):
        """
        Returns an EDA-safe name for a node profile
        """
        return f"{topology.get_eda_safe_name()}-{self.NODE_TYPE}-{self.version}"

    def is_eda_supported(self):
        """
        Returns True if this node is supported as part of an EDA topology
        """
        return True

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
        pattern = re.compile("^e([0-9])-([0-9]+)$")

        if pattern.match(ifname):
            match = pattern.search(ifname)
            return f"ethernet-{match.group(1)}-{match.group(2)}"

        return ifname

    def get_node_profile(self, topology):
        """
        Creates a node profile for this node kind & version
        """
        logger.info(f"Rendering node profile for {self}")

        artifact_name, filename = self.get_artifact_metadata()

        data = {
            "namespace": f"clab-{topology.name}",
            "profile_name": self.get_profile_name(topology),
            "sw_version": self.version,
            "gnmi_port": self.GNMI_PORT,
            "operating_system": self.kind,
            "version_path": self.VERSION_PATH,
            # below evaluates to something like v24\.7\.1.*
            "version_match": "v{}.*".format(self.version.replace(".", "\.")),
            "yang_path": self.YANG_PATH.format(
                artifact_name=artifact_name, filename=filename
            ),
            "node_user": "admin",
            "onboarding_password": self.SRL_PASSWORD,
            "onboarding_username": self.SRL_USERNAME,
            "sw_image": self.SRL_IMAGE.format(version=self.version),
            "sw_image_md5": self.SRL_IMAGE_MD5.format(version=self.version),
        }

        return helpers.render_template("node-profile.j2", data)

    def get_toponode(self, topology):
        """
        Creates a topo node for this node

        Returns
        -------
        the rendered toponode jinja template
        """
        logger.info(f"Creating toponode node for {self}")

        role_value = "leaf"
        if "leaf" in self.name:
            role_value = "leaf"
        elif "spine" in self.name:
            role_value = "spine"
        elif "borderleaf" in self.name or "bl" in self.name:
            role_value = "borderleaf"
        elif "dcgw" in self.name:
            role_value = "dcgw"
        else:
            logger.debug(
                f"Could not determine role of node {self}, defaulting to eda.nokia.com/role=leaf"
            )

        data = {
            "namespace": f"clab-{topology.name}",
            "node_name": self.get_node_name(topology),
            "topology_name": topology.get_eda_safe_name(),
            "role_value": role_value,
            "node_profile": self.get_profile_name(topology),
            "kind": self.kind,
            "platform": self.get_platform(),
            "sw_version": self.version,
            "mgmt_ip": self.mgmt_ipv4,
        }

        return helpers.render_template("toponode.j2", data)

    def get_topolink_interface_name(self, topology, ifname):
        """
        Returns the name of this node's topolink with given interface
        """
        return (
            f"{self.get_node_name(topology)}-{self.get_interface_name_for_kind(ifname)}"
        )

    def get_topolink_interface(self, topology, ifname, other_node):
        """
        Creates a topolink interface for this node and interface

        Parameters
        ----------
        topology:   the parsed Topology
        ifname:     name of the topolink interface
        other_node: node at the other end of the topolink (used for description)

        Returns
        -------
        The rendered interface jinja template
        """
        logger.info(f"Creating topolink interface for {self}")

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
        SR Linux nodes need YANG model artifacts
        """
        return True

    def get_artifact_name(self):
        """
        Returns the standardized artifact name for this SR Linux version
        """
        return f"clab-srlinux-{self.version}"

    def get_artifact_info(self):
        """
        Gets SR Linux YANG models artifact information from GitHub.
        """
        # Return cached info if available
        if self._artifact_info is not None:
            return self._artifact_info

        def srlinux_filter(name):
            return (
                name.endswith(".zip")
                and name.startswith("srlinux-")
                and "Source code" not in name
            )

        artifact_name = self.get_artifact_name()
        filename, download_url = helpers.get_artifact_from_github(
            owner="nokia",
            repo="srlinux-yang-models",
            version=self.version,
            asset_filter=srlinux_filter,
        )

        # Cache the result
        self._artifact_info = (artifact_name, filename, download_url)
        return self._artifact_info

    def get_artifact_metadata(self):
        """
        Returns just the artifact name and filename without making API calls.
        Used when we don't need the download URL.
        """
        if self._artifact_info is not None:
            # Return cached info if available
            artifact_name, filename, _ = self._artifact_info
            return artifact_name, filename

        # If not cached, return basic info without API call
        artifact_name = self.get_artifact_name()
        filename = f"srlinux-{self.version}.zip"  # Assume standard naming
        return artifact_name, filename

    def get_artifact_yaml(self, artifact_name, filename, download_url):
        """
        Renders the artifact YAML for SR Linux YANG models
        """
        data = {
            "artifact_name": artifact_name,
            "namespace": "eda-system",
            "artifact_filename": filename,
            "artifact_url": download_url,
        }
        return helpers.render_template("artifact.j2", data)
