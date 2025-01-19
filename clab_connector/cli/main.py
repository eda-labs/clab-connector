# clab_connector/cli/main.py

import logging
import os
from enum import Enum
from pathlib import Path
from typing import List

import typer
import urllib3
from rich.logging import RichHandler
from rich import print as rprint
from typing_extensions import Annotated

from clab_connector.services.integration.topology_integrator import TopologyIntegrator
from clab_connector.services.removal.topology_remover import TopologyRemover
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
    current = Path(incomplete) if incomplete else Path.cwd()
    if not current.is_dir():
        current = current.parent
    return [str(path) for path in current.glob("*.json") if incomplete in str(path)]


def complete_eda_url(
    ctx: typer.Context, param: typer.Option, incomplete: str
) -> List[str]:
    if not incomplete:
        return ["https://"]
    if not incomplete.startswith("https://"):
        return ["https://" + incomplete]
    return []


def setup_logging(log_level: str):
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )
    logger = logging.getLogger(__name__)
    logger.warning(f"Supported containerlab kinds are: {SUPPORTED_KINDS}")


def execute_integration(args):
    # Build the EDA client here
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
    verify: bool = typer.Option(
        False, "--verify", help="Enables certificate verification for EDA"
    ),
):
    setup_logging(log_level.value)
    os.environ["no_proxy"] = eda_url

    # Build an args object
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
    verify: bool = typer.Option(False, "--verify", help="Verify EDA certs"),
):
    setup_logging(log_level.value)
    os.environ["no_proxy"] = eda_url

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
