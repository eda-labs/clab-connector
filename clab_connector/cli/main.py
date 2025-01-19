# clab_connector/cli/main.py

import logging
from enum import Enum
from typing import Optional
from pathlib import Path
from typing import List

import typer
import urllib3
from rich import print as rprint
from typing_extensions import Annotated

from clab_connector.services.integration.topology_integrator import TopologyIntegrator
from clab_connector.services.removal.topology_remover import TopologyRemover
from clab_connector.utils.logging_config import setup_logging
from clab_connector.clients.eda.client import EDAClient

# Disable urllib3 warnings
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
    help="Integrate an existing containerlab topology with EDA (Event-Driven Automation)",
    add_completion=True,
)


def complete_json_files(
    ctx: typer.Context, param: typer.Option, incomplete: str
) -> List[str]:
    """
    Complete JSON file paths for CLI autocomplete.

    Parameters
    ----------
    ctx : typer.Context
        The Typer context object.
    param : typer.Option
        The option that is being completed.
    incomplete : str
        The partial input from the user.

    Returns
    -------
    List[str]
        A list of matching .json file paths.
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

    Parameters
    ----------
    ctx : typer.Context
        The Typer context object.
    param : typer.Option
        The option that is being completed.
    incomplete : str
        The partial input from the user.

    Returns
    -------
    List[str]
        A list containing suggestions such as 'https://'.
    """
    if not incomplete:
        return ["https://"]
    if not incomplete.startswith("https://"):
        return ["https://" + incomplete]
    return []


def execute_integration(args):
    """
    Execute integration logic by creating the EDAClient and calling the TopologyIntegrator.

    Parameters
    ----------
    args : object
        A generic object with integration arguments (topology_data, eda_url, etc.).

    Returns
    -------
    None
    """
    eda_client = EDAClient(
        hostname=args.eda_url,
        username=args.eda_user,
        password=args.eda_password,
        verify=args.verify,
    )
    integrator = TopologyIntegrator(eda_client)
    integrator.run(
        topology_file=args.topology_data,
        eda_url=args.eda_url,
        eda_user=args.eda_user,
        eda_password=args.eda_password,
        verify=args.verify,
    )


def execute_removal(args):
    """
    Execute removal logic by creating the EDAClient and calling the TopologyRemover.

    Parameters
    ----------
    args : object
        A generic object with removal arguments (topology_data, eda_url, etc.).

    Returns
    -------
    None
    """
    eda_client = EDAClient(
        hostname=args.eda_url,
        username=args.eda_user,
        password=args.eda_password,
        verify=args.verify,
    )
    remover = TopologyRemover(eda_client)
    remover.run(topology_file=args.topology_data)


@app.command(name="integrate", help="Integrate containerlab with EDA")
def integrate_cmd(
    topology_data: Annotated[
        Path,
        typer.Option(
            "--topology-data",
            "-t",
            help="The containerlab topology data JSON file",
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
            help="The hostname or IP of your EDA deployment",
            shell_complete=complete_eda_url,
        ),
    ],
    eda_user: str = typer.Option("admin", "--eda-user", help="EDA username"),
    eda_password: str = typer.Option("admin", "--eda-password", help="EDA password"),
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", "-l", help="Set logging level"
    ),
    log_file: Optional[str] = typer.Option(
        None,
        "--log-file",
        "-f",
        help="Optional log file path",
    ),
    verify: bool = typer.Option(
        False, "--verify", help="Enables certificate verification for EDA"
    ),
):
    """
    CLI command to integrate a containerlab topology with EDA.

    Parameters
    ----------
    topology_data : Path
        Path to the containerlab topology JSON file.
    eda_url : str
        The hostname or IP of the EDA deployment.
    eda_user : str
        The EDA username.
    eda_password : str
        The EDA password.
    log_level : LogLevel
        Logging level to use.
    log_file : Optional[str]
        Path to an optional log file.
    verify : bool
        Whether to enable certificate verification.

    Returns
    -------
    None
    """
    setup_logging(log_level.value, log_file)
    logger = logging.getLogger(__name__)
    logger.warning(f"Supported containerlab kinds are: {SUPPORTED_KINDS}")

    Args = type("Args", (), {})
    args = Args()
    args.topology_data = topology_data
    args.eda_url = eda_url
    args.eda_user = eda_user
    args.eda_password = eda_password
    args.verify = verify

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
            help="The containerlab topology data JSON file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            shell_complete=complete_json_files,
        ),
    ],
    eda_url: str = typer.Option(..., "--eda-url", "-e", help="EDA deployment hostname"),
    eda_user: str = typer.Option("admin", "--eda-user", help="EDA username"),
    eda_password: str = typer.Option("admin", "--eda-password", help="EDA password"),
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", "-l", help="Set logging level"
    ),
    log_file: Optional[str] = typer.Option(
        None,
        "--log-file",
        "-f",
        help="Optional log file path",
    ),
    verify: bool = typer.Option(False, "--verify", help="Verify EDA certs"),
):
    """
    CLI command to remove an existing containerlab-EDA integration.

    Parameters
    ----------
    topology_data : Path
        Path to the containerlab topology JSON file.
    eda_url : str
        The EDA hostname/IP address.
    eda_user : str
        The EDA username.
    eda_password : str
        The EDA password.
    log_level : LogLevel
        Logging level to use.
    log_file : Optional[str]
        Path to an optional log file.
    verify : bool
        Whether to enable certificate verification.

    Returns
    -------
    None
    """
    setup_logging(log_level.value, log_file)
    logger = logging.getLogger(__name__)

    Args = type("Args", (), {})
    args = Args()
    args.topology_data = topology_data
    args.eda_url = eda_url
    args.eda_user = eda_user
    args.eda_password = eda_password
    args.verify = verify

    try:
        execute_removal(args)
    except Exception as e:
        rprint(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
