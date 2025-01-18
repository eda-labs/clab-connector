#!/usr/bin/env python3
import logging
import os
from enum import Enum
from pathlib import Path

import typer
import urllib3
from rich.logging import RichHandler
from rich import print as rprint

from clab_connector.core.integrate import IntegrateCommand
from clab_connector.core.remove import RemoveCommand

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


def setup_logging(log_level: str):
    """Configure logging with colored output"""
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )

    logger = logging.getLogger(__name__)
    logger.warning(f"Supported containerlab kinds are: {SUPPORTED_KINDS}")


def execute_command(command_class, args):
    """Execute a command with common error handling"""
    try:
        cmd = command_class()
        cmd.run(args)
    except Exception as e:
        rprint(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(code=1)


@app.command(name="integrate", help="Integrate containerlab with EDA")
def integrate_cmd(
    topology_data: Path = typer.Option(
        ...,
        "--topology-data",
        "-t",
        help="The containerlab topology data JSON file",
        exists=True,
    ),
    eda_url: str = typer.Option(
        ..., "--eda-url", "-e", help="The hostname or IP of your EDA deployment"
    ),
    eda_user: str = typer.Option(
        "admin", "--eda-user", help="The username of the EDA user"
    ),
    eda_password: str = typer.Option(
        "admin", "--eda-password", help="The password of the EDA user"
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", "-l", help="Set logging level"
    ),
    verify: bool = typer.Option(
        False, "--verify", help="Enables certificate verification for EDA"
    ),
):
    setup_logging(log_level.value)
    os.environ["no_proxy"] = eda_url

    args = type(
        "Args",
        (),
        {
            "topology_data": topology_data,
            "eda_url": eda_url,
            "eda_user": eda_user,
            "eda_password": eda_password,
            "verify": verify,
        },
    )()

    execute_command(IntegrateCommand, args)


@app.command(name="remove", help="Remove containerlab integration from EDA")
def remove_cmd(
    topology_data: Path = typer.Option(
        ...,
        "--topology-data",
        "-t",
        help="The containerlab topology data JSON file",
        exists=True,
    ),
    eda_url: str = typer.Option(
        ..., "--eda-url", "-e", help="The hostname or IP of your EDA deployment"
    ),
    eda_user: str = typer.Option(
        "admin", "--eda-user", help="The username of the EDA user"
    ),
    eda_password: str = typer.Option(
        "admin", "--eda-password", help="The password of the EDA user"
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", "-l", help="Set logging level"
    ),
    verify: bool = typer.Option(
        False, "--verify", help="Enables certificate verification for EDA"
    ),
):
    setup_logging(log_level.value)

    args = type(
        "Args",
        (),
        {
            "topology_data": topology_data,
            "eda_url": eda_url,
            "eda_user": eda_user,
            "eda_password": eda_password,
            "verify": verify,
        },
    )()

    execute_command(RemoveCommand, args)


if __name__ == "__main__":
    app()