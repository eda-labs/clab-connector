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
        LogLevel.WARNING, "--log-level", "-l", help="Set logging level"
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

        integrator = TopologyIntegrator(eda_client)
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
        LogLevel.WARNING, "--log-level", "-l", help="Set logging level"
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

if __name__ == "__main__":
    app()
