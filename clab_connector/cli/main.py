# clab_connector/cli/main.py

from enum import Enum
from pathlib import Path
from typing import List, Optional

import typer
import urllib3
from rich import print as rprint
from typing_extensions import Annotated

# Disable urllib3 warnings (optional)
urllib3.disable_warnings()

SUPPORTED_KINDS = ["nokia_srlinux", "nokia_sros"]


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
    from pathlib import Path

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
        "admin", "--eda-password", help="EDA user password (realm='eda')"
    ),
    kc_user: str = typer.Option(
        "admin", "--kc-user", help="Keycloak master realm admin user (default: admin)"
    ),
    kc_password: str = typer.Option(
        "admin",
        "--kc-password",
        help="Keycloak master realm admin password (default: admin)",
    ),
    kc_secret: Optional[str] = typer.Option(
        None,
        "--kc-secret",
        help="If given, use this as the EDA client secret and skip Keycloak admin flow",
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.INFO, "--log-level", "-l", help="Set logging level"
    ),
    log_file: Optional[str] = typer.Option(
        None, "--log-file", "-f", help="Optional log file path"
    ),
    verify: bool = typer.Option(False, "--verify", help="Enable TLS cert verification"),
    skip_edge_intfs: bool = typer.Option(
        False,
        "--skip-edge-intfs",
        help="Skip creation of edge links and their interfaces",
    ),
    enable_sync_check: bool = typer.Option(
        True,
        "--enable-sync-check/--disable-sync-check",
        help="Enable/disable node synchronization checking after integration",
    ),
    sync_timeout: int = typer.Option(
        90,
        "--sync-timeout",
        help="Timeout for node synchronization check in seconds",
    ),
):
    """
    CLI command to integrate a containerlab topology with EDA.
    """
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
    args.kc_user = kc_user
    args.kc_password = kc_password
    args.kc_secret = kc_secret
    args.verify = verify
    args.skip_edge_intfs = skip_edge_intfs
    args.enable_sync_check = enable_sync_check
    args.sync_timeout = sync_timeout

    def execute_integration(a):
        eda_client = EDAClient(
            hostname=a.eda_url,
            eda_user=a.eda_user,
            eda_password=a.eda_password,
            kc_secret=a.kc_secret,  # If set, skip admin flow
            kc_user=a.kc_user,
            kc_password=a.kc_password,
            verify=a.verify,
        )

        integrator = TopologyIntegrator(eda_client, enable_sync_checking=a.enable_sync_check, sync_timeout=a.sync_timeout)
        integrator.run(
            topology_file=a.topology_data,
            eda_url=a.eda_url,
            eda_user=a.eda_user,
            eda_password=a.eda_password,
            verify=a.verify,
            skip_edge_intfs=a.skip_edge_intfs,
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
        "admin", "--eda-password", help="EDA user password (realm='eda')"
    ),
    # Keycloak options
    kc_user: str = typer.Option(
        "admin", "--kc-user", help="Keycloak master realm admin user (default: admin)"
    ),
    kc_password: str = typer.Option(
        "admin",
        "--kc-password",
        help="Keycloak master realm admin password (default: admin)",
    ),
    kc_secret: Optional[str] = typer.Option(
        None,
        "--kc-secret",
        help="If given, use this as the EDA client secret and skip Keycloak admin flow",
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.INFO, "--log-level", "-l", help="Set logging level"
    ),
    log_file: Optional[str] = typer.Option(
        None, "--log-file", "-f", help="Optional log file path"
    ),
    verify: bool = typer.Option(False, "--verify", help="Enable TLS cert verification"),
):
    """
    CLI command to remove EDA integration (delete the namespace).
    """
    from clab_connector.utils.logging_config import setup_logging
    from clab_connector.clients.eda.client import EDAClient
    from clab_connector.services.removal.topology_remover import TopologyRemover

    # Set up logging
    setup_logging(log_level.value, log_file)
    class Args:
        pass

    args = Args()
    args.topology_data = topology_data
    args.eda_url = eda_url
    args.eda_user = eda_user
    args.eda_password = eda_password
    args.kc_user = kc_user
    args.kc_password = kc_password
    args.kc_secret = kc_secret
    args.verify = verify

    def execute_removal(a):
        eda_client = EDAClient(
            hostname=a.eda_url,
            eda_user=a.eda_user,
            eda_password=a.eda_password,
            kc_secret=a.kc_secret,
            kc_user=a.kc_user,
            kc_password=a.kc_password,
            verify=a.verify,
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
        LogLevel.INFO, "--log-level", help="Logging level"
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
    from clab_connector.services.export.topology_exporter import TopologyExporter

    setup_logging(log_level.value, log_file)
    logger = logging.getLogger(__name__)

    if not output_file:
        output_file = f"{namespace}.clab.yaml"

    exporter = TopologyExporter(namespace, output_file, logger)
    try:
        exporter.run()
    except Exception as e:
        logger.error(f"Failed to export lab from namespace '{namespace}': {e}")
        raise typer.Exit(code=1)

@app.command(
    name="generate-crs",
    help="Generate CR YAML manifests from a containerlab topology without applying them to EDA."
)
def generate_crs_cmd(
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
    output_file: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path for a combined manifest; if --separate is used, this is the output directory"
    ),
    separate: bool = typer.Option(
        False, "--separate", help="Generate separate YAML files for each CR instead of one combined file"
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.INFO, "--log-level", "-l", help="Set logging level"
    ),
    log_file: Optional[str] = typer.Option(
        None, "--log-file", "-f", help="Optional log file path"
    ),
    skip_edge_intfs: bool = typer.Option(
        False,
        "--skip-edge-intfs",
        help="Skip creation of edge links and their interfaces",
    ),
):
    """
    Generate the CR YAML manifests (artifacts, init, node security profile,
    node user group/user, node profiles, toponodes, topolink interfaces, and topolinks)
    from the given containerlab topology file.

    The manifests can be written as one combined YAML file (default) or as separate files
    (if --separate is specified).
    """
    from clab_connector.services.manifest.manifest_generator import ManifestGenerator
    from clab_connector.utils.logging_config import setup_logging

    setup_logging(log_level.value, log_file)

    try:
        generator = ManifestGenerator(
            str(topology_data),
            output=output_file,
            separate=separate,
            skip_edge_intfs=skip_edge_intfs,
        )
        generator.generate()
        generator.output_manifests()
    except Exception as e:
        rprint(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(code=1)


@app.command(
    name="check-sync",
    help="Check synchronization status of nodes in EDA"
)
def check_sync_cmd(
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
        "admin", "--eda-password", help="EDA user password (realm='eda')"
    ),
    kc_user: str = typer.Option(
        "admin", "--kc-user", help="Keycloak master realm admin user (default: admin)"
    ),
    kc_password: str = typer.Option(
        "admin",
        "--kc-password",
        help="Keycloak master realm admin password (default: admin)",
    ),
    kc_secret: Optional[str] = typer.Option(
        None,
        "--kc-secret",
        help="If given, use this as the EDA client secret and skip Keycloak admin flow",
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.INFO, "--log-level", "-l", help="Set logging level"
    ),
    log_file: Optional[str] = typer.Option(
        None, "--log-file", "-f", help="Optional log file path"
    ),
    verify: bool = typer.Option(False, "--verify", help="Enable TLS cert verification"),
    wait: bool = typer.Option(
        False, "--wait", help="Wait for all nodes to be ready"
    ),
    timeout: int = typer.Option(
        90, "--timeout", help="Timeout for waiting (seconds)"
    ),
    namespace_override: Optional[str] = typer.Option(
        None, "--namespace", help="Override the namespace (instead of deriving from topology)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", 
        help="Show detailed information about node status, API sources, and more"
    ),
):
    """
    Check the synchronization status of nodes in EDA.
    """
    import logging
    import json
    from clab_connector.utils.logging_config import setup_logging
    from clab_connector.clients.eda.client import EDAClient
    from clab_connector.services.status.node_sync_checker import NodeSyncChecker
    from clab_connector.models.topology import parse_topology_file

    # Set up logging
    setup_logging(log_level.value, log_file)
    logger = logging.getLogger(__name__)

    try:
        # Parse topology to get node names
        topology = parse_topology_file(str(topology_data))
        node_names = [node.get_node_name(topology) for node in topology.nodes]
        namespace = namespace_override or f"clab-{topology.name}"
        
        logger.info(f"Topology name: '{topology.name}'")
        logger.info(f"Using namespace: '{namespace}'" + (" (overridden)" if namespace_override else " (from topology)"))
        logger.info(f"Node names: {node_names[:5]}{'...' if len(node_names) > 5 else ''}")

        # Create EDA client
        eda_client = EDAClient(
            hostname=eda_url,
            eda_user=eda_user,
            eda_password=eda_password,
            kc_secret=kc_secret,
            kc_user=kc_user,
            kc_password=kc_password,
            verify=verify,
        )

        # Create sync checker
        sync_checker = NodeSyncChecker(eda_client, namespace)
        
        # Check if any nodes are found and suggest alternatives if not
        if wait:
            logger.info(f"Waiting for {len(node_names)} nodes to be ready (timeout: {timeout}s)")
            success = sync_checker.wait_for_nodes_ready(node_names, timeout=timeout, verbose=verbose)
            if not success:
                raise typer.Exit(code=1)
        else:
            # Use the new detailed status display method instead of the older approach
            sync_checker.display_detailed_status(node_names, verbose)
            
            # Get summary for exit code handling
            summary = sync_checker.get_sync_summary(node_names)
            
            # If all nodes are unknown, suggest namespace alternatives
            if summary['unknown_nodes'] == summary['total_nodes']:
                available_namespaces = sync_checker.list_available_namespaces()
                if available_namespaces:
                    suggested_namespace = sync_checker.suggest_correct_namespace(namespace)
                    rprint(f"\n[yellow]Warning: All nodes are unknown. This might indicate the wrong namespace.[/yellow]")
                    rprint(f"Current namespace: [dim]{namespace}[/dim]")
                    rprint(f"Available clab namespaces: [dim]{', '.join(available_namespaces)}[/dim]")
                    if suggested_namespace and suggested_namespace != namespace:
                        rprint(f"Suggested namespace: [green]{suggested_namespace}[/green]")
                        rprint(f"\nTry: [dim]clab-connector check-sync -t {topology_data} -e {eda_url} --namespace {suggested_namespace}[/dim]")
                else:
                    rprint(f"\n[yellow]Warning: All nodes are unknown and no clab namespaces found via EDA API.[/yellow]")
                    rprint(f"Check if the EDA connection is working and the namespace exists.")
            
            # Set exit code based on status
            if summary['error_nodes'] > 0:
                raise typer.Exit(code=1)
            elif summary['ready_nodes'] < summary['total_nodes']:
                raise typer.Exit(code=2)  # Some nodes not ready yet

    except Exception as e:
        rprint(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(code=1)

@app.command(
    name="health-check",
    help="Check health of EDA connectivity and services"
)
def health_check_cmd(
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
        "admin", "--eda-password", help="EDA user password (realm='eda')"
    ),
    kc_user: str = typer.Option(
        "admin", "--kc-user", help="Keycloak master realm admin user (default: admin)"
    ),
    kc_password: str = typer.Option(
        "admin",
        "--kc-password",
        help="Keycloak master realm admin password (default: admin)",
    ),
    kc_secret: Optional[str] = typer.Option(
        None,
        "--kc-secret",
        help="If given, use this as the EDA client secret and skip Keycloak admin flow",
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.INFO, "--log-level", "-l", help="Set logging level"
    ),
    log_file: Optional[str] = typer.Option(
        None, "--log-file", "-f", help="Optional log file path"
    ),
    verify: bool = typer.Option(False, "--verify", help="Enable TLS cert verification"),
):
    """
    Check the health of EDA connectivity and services.
    """
    import logging
    from clab_connector.utils.logging_config import setup_logging
    from clab_connector.clients.eda.client import EDAClient
    from clab_connector.services.health.health_checker import HealthChecker, HealthStatus

    # Set up logging
    setup_logging(log_level.value, log_file)
    logger = logging.getLogger(__name__)

    try:
        # Create EDA client
        eda_client = EDAClient(
            hostname=eda_url,
            eda_user=eda_user,
            eda_password=eda_password,
            kc_secret=kc_secret,
            kc_user=kc_user,
            kc_password=kc_password,
            verify=verify,
        )

        # Create health checker
        health_checker = HealthChecker(eda_client)
        
        # Run health checks
        results = health_checker.run_full_health_check()
        overall_status = health_checker.get_overall_health_status(results)
        
        # Print results
        rprint(f"\n[bold]EDA Health Check Results[/bold]")
        rprint(f"Overall Status: ", end="")
        
        if overall_status == HealthStatus.HEALTHY:
            rprint("[green]HEALTHY[/green]")
        elif overall_status == HealthStatus.DEGRADED:
            rprint("[yellow]DEGRADED[/yellow]")
        elif overall_status == HealthStatus.UNHEALTHY:
            rprint("[red]UNHEALTHY[/red]")
        else:
            rprint("[dim]UNKNOWN[/dim]")
        
        rprint("\n[bold]Component Details:[/bold]")
        for check_name, result in results.items():
            status_color = {
                HealthStatus.HEALTHY: "green",
                HealthStatus.DEGRADED: "yellow", 
                HealthStatus.UNHEALTHY: "red",
                HealthStatus.UNKNOWN: "dim"
            }.get(result.status, "dim")
            
            rprint(f"  {result.name}: [{status_color}]{result.status.value.upper()}[/{status_color}] - {result.message}")
            
            if result.details:
                for key, value in result.details.items():
                    rprint(f"    {key}: {value}")
        
        # Set exit code based on overall health
        if overall_status == HealthStatus.UNHEALTHY:
            raise typer.Exit(code=1)
        elif overall_status == HealthStatus.DEGRADED:
            raise typer.Exit(code=2)

    except Exception as e:
        rprint(f"[red]Error during health check: {str(e)}[/red]")
        raise typer.Exit(code=1)

@app.command(
    name="debug-eda", 
    help="Debug EDA connectivity and list available resources"
)
def debug_eda_cmd(
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
        "admin", "--eda-password", help="EDA user password (realm='eda')"
    ),
    kc_user: str = typer.Option(
        "admin", "--kc-user", help="Keycloak master realm admin user (default: admin)"
    ),
    kc_password: str = typer.Option(
        "admin",
        "--kc-password",
        help="Keycloak master realm admin password (default: admin)",
    ),
    kc_secret: Optional[str] = typer.Option(
        None,
        "--kc-secret",
        help="If given, use this as the EDA client secret and skip Keycloak admin flow",
    ),
    namespace: Optional[str] = typer.Option(
        None, "--namespace", help="Check specific namespace for TopoNodes"
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.INFO, "--log-level", "-l", help="Set logging level"
    ),
    log_file: Optional[str] = typer.Option(
        None, "--log-file", "-f", help="Optional log file path"
    ),
    verify: bool = typer.Option(False, "--verify", help="Enable TLS cert verification"),
):
    """
    Debug EDA connectivity and list available resources.
    """
    import logging
    from clab_connector.utils.logging_config import setup_logging
    from clab_connector.clients.eda.client import EDAClient
    from clab_connector.services.status.node_sync_checker import NodeSyncChecker

    # Set up logging
    setup_logging(log_level.value, log_file)
    logger = logging.getLogger(__name__)

    try:
        # Create EDA client
        eda_client = EDAClient(
            hostname=eda_url,
            eda_user=eda_user,
            eda_password=eda_password,
            kc_secret=kc_secret,
            kc_user=kc_user,
            kc_password=kc_password,
            verify=verify,
        )

        rprint(f"[bold]EDA Debug Information[/bold]")
        rprint(f"EDA URL: {eda_url}")
        
        # Test basic connectivity
        try:
            # Try to get EDA version or basic info
            response = eda_client.get("health")
            if response.status == 200:
                rprint(f"✅ EDA API connectivity: [green]OK[/green]")
            else:
                rprint(f"⚠️  EDA API connectivity: [yellow]HTTP {response.status}[/yellow]")
        except Exception as e:
            rprint(f"❌ EDA API connectivity: [red]Failed - {e}[/red]")
        
        # List available namespaces
        sync_checker = NodeSyncChecker(eda_client, namespace or "default")
        available_namespaces = sync_checker.list_available_namespaces()
        
        if available_namespaces:
            rprint(f"\n[bold]Available clab namespaces ({len(available_namespaces)}):[/bold]")
            for ns in available_namespaces:
                rprint(f"  • {ns}")
        else:
            rprint(f"\n[yellow]No clab namespaces found[/yellow]")
            
        # If specific namespace provided, check TopoNodes
        if namespace:
            rprint(f"\n[bold]Checking namespace: {namespace}[/bold]")
            sync_checker = NodeSyncChecker(eda_client, namespace)
            toponodes = sync_checker.list_toponodes_in_namespace()
            
            if toponodes:
                rprint(f"Found {len(toponodes)} TopoNodes:")
                for node in toponodes[:20]:  # Show first 20
                    rprint(f"  • {node}")
                if len(toponodes) > 20:
                    rprint(f"  ... and {len(toponodes) - 20} more")
            else:
                rprint(f"[yellow]No TopoNodes found in namespace {namespace}[/yellow]")
                
                # Check namespace status
                namespace_info = sync_checker.check_namespace_and_resources()
                if not namespace_info.get("namespace_exists", False):
                    rprint(f"[red]Namespace {namespace} does not exist[/red]")
                else:
                    rprint(f"[yellow]Namespace {namespace} exists but contains no TopoNodes[/yellow]")

    except Exception as e:
        rprint(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
