# clab_connector/services/export/topology_exporter.py

import logging
from ipaddress import IPv4Network, IPv4Address
from clab_connector.clients.kubernetes.client import (
    list_toponodes_in_namespace,
    list_topolinks_in_namespace,
)
from clab_connector.utils.yaml_processor import YAMLProcessor


class TopologyExporter:
    """
    TopologyExporter retrieves EDA toponodes/topolinks from a namespace
    and converts them to a .clab.yaml data structure.

    Parameters
    ----------
    namespace : str
        The Kubernetes namespace that contains EDA toponodes/topolinks.
    output_file : str
        The path where the .clab.yaml file will be written.
    logger : logging.Logger
        A logger instance for output/diagnostics.
    """

    def __init__(self, namespace: str, output_file: str, logger: logging.Logger):
        self.namespace = namespace
        self.output_file = output_file
        self.logger = logger

    def run(self):
        """
        Fetch the nodes and links, build containerlab YAML, and write to output_file.
        """
        # 1. Fetch data
        try:
            node_items = list_toponodes_in_namespace(self.namespace)
            link_items = list_topolinks_in_namespace(self.namespace)
        except Exception as e:
            self.logger.error(f"Failed to list toponodes/topolinks: {e}")
            raise

        # 2. Gather mgmt IP addresses for optional mgmt subnet
        mgmt_ips = self._collect_management_ips(node_items)

        mgmt_subnet = self._derive_mgmt_subnet(mgmt_ips)

        clab_data = {
            "name": self.namespace,  # Use namespace as "lab name"
            "mgmt": {"network": f"{self.namespace}-mgmt", "ipv4-subnet": mgmt_subnet},
            "topology": {
                "nodes": {},
                "links": [],
            },
        }

        # 3. Convert each toponode into containerlab node config
        for node_item in node_items:
            node_name, node_def = self._build_node_definition(node_item)
            if node_name and node_def:
                clab_data["topology"]["nodes"][node_name] = node_def

        # 4. Convert each topolink into containerlab link config
        for link_item in link_items:
            self._build_link_definitions(link_item, clab_data["topology"]["links"])

        # 5. Write the .clab.yaml
        self._write_clab_yaml(clab_data)

    def _collect_management_ips(self, node_items):
        ips = []
        for node_item in node_items:
            spec = node_item.get("spec", {})
            status = node_item.get("status", {})
            production_addr = (
                spec.get("productionAddress") or status.get("productionAddress") or {}
            )
            mgmt_ip = production_addr.get("ipv4")

            if not mgmt_ip and "node-details" in status:
                node_details = status["node-details"]
                mgmt_ip = node_details.split(":")[0]

            if mgmt_ip:
                try:
                    ips.append(IPv4Address(mgmt_ip))
                except ValueError:
                    self.logger.warning(f"Invalid IP address found: {mgmt_ip}")
        return ips

    def _derive_mgmt_subnet(self, mgmt_ips):
        """
        Given a list of IPv4Addresses, compute a smallest common subnet.
        If none, fallback to '172.80.80.0/24'.
        """
        if not mgmt_ips:
            self.logger.warning("No valid management IPs found, using default subnet")
            return "172.80.80.0/24"

        min_ip = min(mgmt_ips)
        max_ip = max(mgmt_ips)

        min_bits = format(int(min_ip), "032b")
        max_bits = format(int(max_ip), "032b")

        common_prefix = 0
        for i in range(32):
            if min_bits[i] == max_bits[i]:
                common_prefix += 1
            else:
                break

        subnet = IPv4Network(f"{min_ip}/{common_prefix}", strict=False)
        return str(subnet)

    def _build_node_definition(self, node_item):
        """
        Convert an EDA toponode item into a containerlab 'node definition'.
        Returns (node_name, node_def) or (None, None) if skipped.
        """
        meta = node_item.get("metadata", {})
        spec = node_item.get("spec", {})
        status = node_item.get("status", {})

        node_name = meta.get("name")
        if not node_name:
            self.logger.warning("Node item missing metadata.name, skipping.")
            return None, None

        operating_system = (
            spec.get("operatingSystem") or status.get("operatingSystem") or ""
        )
        version = spec.get("version") or status.get("version") or ""

        production_addr = (
            spec.get("productionAddress") or status.get("productionAddress") or {}
        )
        mgmt_ip = production_addr.get("ipv4")

        # If no productionAddress IP, try node-details
        if not mgmt_ip and "node-details" in status:
            node_details = status["node-details"]
            mgmt_ip = node_details.split(":")[0]

        if not mgmt_ip:
            self.logger.warning(f"No mgmt IP found for node '{node_name}', skipping.")
            return None, None

        # guess 'nokia_srlinux' if operating_system is 'srl*'
        kind = "nokia_srlinux"
        if operating_system.lower().startswith("sros"):
            kind = "nokia_sros"

        node_def = {
            "kind": kind,
            "mgmt-ipv4": mgmt_ip,
        }
        if version:
            node_def["image"] = f"ghcr.io/nokia/srlinux:{version}"

        return node_name, node_def

    def _build_link_definitions(self, link_item, links_array):
        link_spec = link_item.get("spec", {})
        link_entries = link_spec.get("links", [])
        meta = link_item.get("metadata", {})
        link_name = meta.get("name", "unknown-link")

        for entry in link_entries:
            local_node = entry.get("local", {}).get("node")
            local_intf = entry.get("local", {}).get("interface")
            remote_node = entry.get("remote", {}).get("node")
            remote_intf = entry.get("remote", {}).get("interface")
            if local_node and local_intf and remote_node and remote_intf:
                links_array.append(
                    {
                        "endpoints": [
                            f"{local_node}:{local_intf}",
                            f"{remote_node}:{remote_intf}",
                        ]
                    }
                )
            else:
                self.logger.warning(
                    f"Incomplete link entry in {link_name}, skipping that entry."
                )

    def _write_clab_yaml(self, clab_data):
        """
        Save the final containerlab data structure as YAML to self.output_file.
        """
        processor = YAMLProcessor()
        try:
            processor.save_yaml(clab_data, self.output_file)
            self.logger.info(f"Exported containerlab file: {self.output_file}")
        except IOError as e:
            self.logger.error(f"Failed to write containerlab file: {e}")
            raise
