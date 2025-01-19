# clab_connector/models/node/nokia_srl.py

import logging
import re
import socket

from paramiko import (
    SSHClient,
    AutoAddPolicy,
    AuthenticationException,
    BadHostKeyException,
    SSHException,
)

from .base import Node
from clab_connector.utils import helpers

logger = logging.getLogger(__name__)


class NokiaSRLinuxNode(Node):
    SRL_USERNAME = "admin"
    SRL_PASSWORD = "NokiaSrl1!"
    NODE_TYPE = "srlinux"
    GNMI_PORT = "57410"
    VERSION_PATH = ".system.information.version"
    YANG_PATH = "https://eda-asvr.eda-system.svc/eda-system/clab-schemaprofiles/{artifact_name}/{filename}"
    SRL_IMAGE = "eda-system/srlimages/srlinux-{version}-bin/srlinux.bin"
    SRL_IMAGE_MD5 = "eda-system/srlimages/srlinux-{version}-bin/srlinux.bin.md5"

    SUPPORTED_SCHEMA_PROFILES = {
        "24.10.1": (
            "https://github.com/nokia/srlinux-yang-models/"
            "releases/download/v24.10.1/srlinux-24.10.1-492.zip"
        )
    }

    def test_ssh(self):
        logger.debug(f"Testing SSH for node '{self.name}' IP {self.mgmt_ipv4}")
        ssh = SSHClient()
        ssh.set_missing_host_key_policy(AutoAddPolicy())
        try:
            ssh.connect(
                hostname=self.mgmt_ipv4,
                username=self.SRL_USERNAME,
                password=self.SRL_PASSWORD,
                allow_agent=False,
            )
            logger.info(f"SSH to {self.name} succeeded")
            return True
        except (
            BadHostKeyException,
            AuthenticationException,
            SSHException,
            socket.error,
        ) as exc:
            logger.error(f"SSH to node {self.name} failed: {exc}")
            raise

    def get_default_node_type(self):
        return "ixrd3l"

    def get_platform(self):
        t = self.node_type.replace("ixr", "")
        return f"7220 IXR-{t.upper()}"

    def is_eda_supported(self):
        return True

    def get_profile_name(self, topology):
        return f"{topology.get_eda_safe_name()}-{self.NODE_TYPE}-{self.version}"

    def get_node_profile(self, topology):
        logger.info(f"Rendering node profile for {self.name}")
        artifact_name = self.get_artifact_name()
        filename = f"srlinux-{self.version}.zip"

        data = {
            "namespace": f"clab-{topology.name}",
            "profile_name": self.get_profile_name(topology),
            "sw_version": self.version,
            "gnmi_port": self.GNMI_PORT,
            "operating_system": self.kind,
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
            "kind": self.kind,
            "platform": self.get_platform(),
            "sw_version": self.version,
            "mgmt_ip": self.mgmt_ipv4,
        }
        return helpers.render_template("toponode.j2", data)

    def get_interface_name_for_kind(self, ifname):
        pattern = re.compile(r"^e(\d+)-(\d+)$")
        match = pattern.match(ifname)
        if match:
            return f"ethernet-{match.group(1)}-{match.group(2)}"
        return ifname

    def get_topolink_interface(self, topology, ifname, other_node):
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
        return True

    def get_artifact_name(self):
        return f"clab-srlinux-{self.version}"

    def get_artifact_info(self):
        if self.version not in self.SUPPORTED_SCHEMA_PROFILES:
            logger.warning(f"No schema profile for version {self.version}")
            return (None, None, None)
        artifact_name = self.get_artifact_name()
        filename = f"srlinux-{self.version}.zip"
        download_url = self.SUPPORTED_SCHEMA_PROFILES[self.version]
        return (artifact_name, filename, download_url)

    def get_artifact_yaml(self, artifact_name, filename, download_url):
        data = {
            "artifact_name": artifact_name,
            "namespace": "eda-system",
            "artifact_filename": filename,
            "artifact_url": download_url,
        }
        return helpers.render_template("artifact.j2", data)
