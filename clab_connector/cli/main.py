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


if __name__ == "__main__":
    app()
