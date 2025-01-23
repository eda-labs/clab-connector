# clab_connector/cli/main.py

from enum import Enum
from pathlib import Path
from typing import List, Optional

import typer
import urllib3
from rich import print as rprint
from typing_extensions import Annotated

# Disable urllib3 warnings at the top (optional)
urllib3.disable_warnings()

SUPPORTED_KINDS = ["nokia_srlinux"]


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


app = typer.Typer(
    name="clab-connector",
    help="Integrate or remove an existing containerlab topology with EDA (Event-Driven Automation)",
    add_completion=True,
)


def complete_json_files(
    ctx: typer.Context, param: typer.Option, incomplete: str
) -> List[str]:
    """
    Complete JSON file paths for CLI autocomplete.
    """
    current = Path(incomplete) if incomplete else Path.cwd()
    if not current.is_dir():
        current = current.parent
    return [str(path) for path in current.glob("*.json") if incomplete in str(path)]


def complete_eda_url(
    ctx: typer.Context, param: typer.Option, incomplete: str
) -> List[str]:
    """
    Complete EDA URL for CLI autocomplete.
    """
    if not incomplete:
        return ["https://"]
    if not incomplete.startswith("https://"):
        return ["https://" + incomplete]
    return []


@app.command(name="integrate", help="Integrate containerlab with EDA")
def integrate_cmd(
    topology_data: Annotated[
        Path,
        typer.Option(
            "--topology-data",
            "-t",
            help="Path to containerlab topology JSON file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            shell_complete=complete_json_files,
        ),
    ],
    eda_url: Annotated[
        str,
        typer.Option(
            "--eda-url",
            "-e",
            help="EDA deployment URL (hostname or IP)",
            shell_complete=complete_eda_url,
        ),
    ],
    eda_user: str = typer.Option(
        "admin", "--eda-user", help="EDA username (realm='eda')"
    ),
    eda_password: str = typer.Option(
        "admin", "--eda-password", help="EDA user password"
    ),
    client_secret: Optional[str] = typer.Option(
        None,
        "--client-secret",
        help="Keycloak client secret for 'eda' client (optional)",
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", "-l", help="Set logging level"
    ),
    log_file: Optional[str] = typer.Option(
        None, "--log-file", "-f", help="Optional log file path"
    ),
    verify: bool = typer.Option(False, "--verify", help="Enable TLS cert verification"),
):
    """
    CLI command to integrate a containerlab topology with EDA.
    """
    # --- MOVE heavy imports here ---
    import logging
    from clab_connector.utils.logging_config import setup_logging
    from clab_connector.clients.eda.client import EDAClient
    from clab_connector.services.integration.topology_integrator import (
        TopologyIntegrator,
    )

    # Set up logging now
    setup_logging(log_level.value, log_file)
    logger = logging.getLogger(__name__)
    logger.warning(f"Supported containerlab kinds are: {SUPPORTED_KINDS}")

    # Construct a small Args-like object to pass around (optional)
    class Args:
        pass

    args = Args()
    args.topology_data = topology_data
    args.eda_url = eda_url
    args.eda_user = eda_user
    args.eda_password = eda_password
    args.client_secret = client_secret
    args.verify = verify

    # Define the logic inline or in a small helper function
    def execute_integration(a):
        eda_client = EDAClient(
            hostname=a.eda_url,
            username=a.eda_user,
            password=a.eda_password,
            verify=a.verify,
            client_secret=a.client_secret,
        )
        integrator = TopologyIntegrator(eda_client)
        integrator.run(
            topology_file=a.topology_data,
            eda_url=a.eda_url,
            eda_user=a.eda_user,
            eda_password=a.eda_password,
            verify=a.verify,
        )

    try:
        execute_integration(args)
    except Exception as e:
        rprint(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(code=1)


@app.command(name="remove", help="Remove containerlab integration from EDA")
def remove_cmd(
    topology_data: Annotated[
        Path,
        typer.Option(
            "--topology-data",
            "-t",
            help="Path to containerlab topology JSON file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            shell_complete=complete_json_files,
        ),
    ],
    eda_url: str = typer.Option(..., "--eda-url", "-e", help="EDA deployment hostname"),
    eda_user: str = typer.Option(
        "admin", "--eda-user", help="EDA username (realm='eda')"
    ),
    eda_password: str = typer.Option(
        "admin", "--eda-password", help="EDA user password"
    ),
    client_secret: Optional[str] = typer.Option(
        None,
        "--client-secret",
        help="Keycloak client secret for 'eda' client (optional)",
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", "-l", help="Set logging level"
    ),
    log_file: Optional[str] = typer.Option(
        None, "--log-file", "-f", help="Optional log file path"
    ),
    verify: bool = typer.Option(False, "--verify", help="Enable TLS cert verification"),
):
    """
    CLI command to remove EDA integration (delete the namespace).
    """
    import logging
    from clab_connector.utils.logging_config import setup_logging
    from clab_connector.clients.eda.client import EDAClient
    from clab_connector.services.removal.topology_remover import TopologyRemover

    # Set up logging
    setup_logging(log_level.value, log_file)
    logger = logging.getLogger(__name__)

    class Args:
        pass

    args = Args()
    args.topology_data = topology_data
    args.eda_url = eda_url
    args.eda_user = eda_user
    args.eda_password = eda_password
    args.client_secret = client_secret
    args.verify = verify

    def execute_removal(a):
        eda_client = EDAClient(
            hostname=a.eda_url,
            username=a.eda_user,
            password=a.eda_password,
            verify=a.verify,
            client_secret=a.client_secret,
        )
        remover = TopologyRemover(eda_client)
        remover.run(topology_file=a.topology_data)

    try:
        execute_removal(args)
    except Exception as e:
        rprint(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(code=1)


@app.command(
    name="export-lab",
    help="Export an EDA-managed topology from a namespace to a .clab.yaml file",
)
def export_lab_cmd(
    namespace: str = typer.Option(
        ...,
        "--namespace",
        "-n",
        help="Kubernetes namespace containing toponodes/topolinks",
    ),
    output_file: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output .clab.yaml file path"
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", help="Logging level"
    ),
    log_file: Optional[str] = typer.Option(
        None, "--log-file", help="Optional log file path"
    ),
):
    """
    Fetch EDA toponodes & topolinks from the specified namespace
    and convert them to a containerlab .clab.yaml file.

    Example:
      clab-connector export-lab -n clab-my-topo --output clab-my-topo.clab.yaml
    """
    import logging
    from clab_connector.utils.logging_config import setup_logging
    from ipaddress import IPv4Network, IPv4Address
    from clab_connector.clients.kubernetes.client import (
        list_toponodes_in_namespace,
        list_topolinks_in_namespace,
    )
    from clab_connector.utils.yaml_processor import YAMLProcessor

    setup_logging(log_level.value, log_file)
    logger = logging.getLogger(__name__)

    if not output_file:
        output_file = f"{namespace}.clab.yaml"

    try:
        node_items = list_toponodes_in_namespace(namespace)
        link_items = list_topolinks_in_namespace(namespace)
    except Exception as e:
        logger.error(f"Failed to list toponodes/topolinks: {e}")
        raise typer.Exit(code=1)

    # Collect all management IPs
    mgmt_ips = []
    for node_item in node_items:
        spec = node_item.get("spec", {})
        status = node_item.get("status", {})
        production_addr = (
            spec.get("productionAddress") or status.get("productionAddress") or {}
        )
        mgmt_ip = production_addr.get("ipv4")
        if mgmt_ip:
            try:
                mgmt_ips.append(IPv4Address(mgmt_ip))
            except ValueError:
                logger.warning(f"Invalid IP address found: {mgmt_ip}")

    # Determine the subnet that encompasses all management IPs
    if mgmt_ips:
        # Find the minimum and maximum IPs
        min_ip = min(mgmt_ips)
        max_ip = max(mgmt_ips)

        # Convert to binary and find the common prefix
        min_ip_bits = format(int(min_ip), "032b")
        max_ip_bits = format(int(max_ip), "032b")

        # Find where the bits start to differ
        common_prefix = 0
        for i in range(32):
            if min_ip_bits[i] == max_ip_bits[i]:
                common_prefix += 1
            else:
                break

        # Use the common prefix to create a subnet that includes all IPs
        subnet = IPv4Network(f"{min_ip}/{common_prefix}", strict=False)
        mgmt_subnet = str(subnet)
    else:
        # Fallback to a default subnet if no valid IPs are found
        mgmt_subnet = "172.80.80.0/24"
        logger.warning("No valid management IPs found, using default subnet")

    clab_data = {
        "name": namespace,  # Use namespace as "lab name"
        "mgmt": {"network": f"{namespace}_mgmt", "ipv4-subnet": mgmt_subnet},
        "topology": {
            "nodes": {},
            "links": [],
        },
    }

    for node_item in node_items:
        meta = node_item.get("metadata", {})
        spec = node_item.get("spec", {})
        status = node_item.get("status", {})
        node_name = meta.get("name")

        operating_system = (
            spec.get("operatingSystem") or status.get("operatingSystem") or ""
        )
        version = spec.get("version") or status.get("version") or ""
        mgmt_ip = None
        # EDA typically stores mgmt IP in .status.productionAddress.ipv4 or .spec.productionAddress.ipv4
        production_addr = (
            spec.get("productionAddress") or status.get("productionAddress") or {}
        )
        mgmt_ip = production_addr.get("ipv4")

        # If we can't find an IP, skip or log a warning
        if not mgmt_ip:
            logger.warning(f"No mgmt IP found for node '{node_name}', skipping.")
            continue

        kind = "nokia_srlinux"
        if operating_system.lower().startswith("srl"):
            kind = "nokia_srlinux"
        if operating_system.lower().startswith("sros"):
            kind = "nokia_sros"

        # Build node definition
        node_def = {
            "kind": kind,
            "mgmt-ipv4": mgmt_ip,
        }

        if version:
            node_def["image"] = f"ghcr.io/nokia/srlinux:{version}"

        clab_data["topology"]["nodes"][node_name] = node_def

    # Convert topolinks into "links: endpoints: [ nodeA:iface, nodeB:iface ]"
    for link_item in link_items:
        link_spec = link_item.get("spec", {})
        link_entries = link_spec.get("links", [])
        for entry in link_entries:
            local_node = entry.get("local", {}).get("node")
            local_intf = entry.get("local", {}).get("interface")
            remote_node = entry.get("remote", {}).get("node")
            remote_intf = entry.get("remote", {}).get("interface")
            if local_node and local_intf and remote_node and remote_intf:
                clab_data["topology"]["links"].append(
                    {
                        "endpoints": [
                            f"{local_node}:{local_intf}",
                            f"{remote_node}:{remote_intf}",
                        ]
                    }
                )
            else:
                logger.warning(
                    f"Incomplete link entry in {link_item['metadata']['name']} - skipping."
                )

    # Write the .clab.yaml to disk
    processor = YAMLProcessor()
    try:
        processor.save_yaml(clab_data, output_file)
        logger.info(f"Exported containerlab file: {output_file}")
    except IOError as e:
        logger.error(f"Failed to write containerlab file: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
