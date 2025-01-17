#!/usr/bin/env python3
import logging
import os
from enum import Enum
from typing import Optional

import typer
import urllib3
from rich.console import Console
from rich.logging import RichHandler

from src.integrate import IntegrateCommand
from src.remove import RemoveCommand

# Initialize Typer app
app = typer.Typer(
    help="Integrate an existing containerlab topology with EDA (Event-Driven Automation)",
    pretty_exceptions_show_locals=False,
)

console = Console()

# Define supported kinds
SUPPORTED_KINDS = ["nokia_srlinux"]


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def setup_logging(log_level: LogLevel):
    """Configure logging with Rich handler"""
    logging.basicConfig(
        level=log_level.value,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )


def version_callback(value: bool):
    """Callback for --version flag"""
    if value:
        console.print("Containerlab EDA Connector v0.1.0")
        raise typer.Exit()


@app.callback()
def common(
    ctx: typer.Context,
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", "-l", help="Set logging level"
    ),
    verify: bool = typer.Option(
        False, "--verify", help="Enables certificate verification for EDA"
    ),
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
):
    """Common parameters and initialization"""
    # Store configuration in context
    ctx.ensure_object(dict)
    ctx.obj["verify"] = verify

    # Set up logging
    setup_logging(log_level)

    # Configure urllib3
    urllib3.disable_warnings()

    # Log supported kinds
    logging.warning(f"Supported containerlab kinds are: {SUPPORTED_KINDS}")


@app.command(name="integrate", help="Integrate containerlab with EDA")
def integrate(
    ctx: typer.Context,
    topology_data: str = typer.Option(
        ..., "--topology-data", "-t", help="The containerlab topology data JSON file"
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
):
    """Integrate containerlab with EDA"""
    # Set no_proxy environment variable
    os.environ["no_proxy"] = eda_url

    # Create command instance with context parameters
    cmd = IntegrateCommand()

    # Create args object with all parameters
    args = typer.Context.with_defaults(
        topology_data=topology_data,
        eda_url=eda_url,
        eda_user=eda_user,
        eda_password=eda_password,
        verify=ctx.obj["verify"],
    )

    # Run the command
    cmd.run(args)


@app.command(name="remove", help="Remove containerlab integration from EDA")
def remove(
    ctx: typer.Context,
    topology_data: str = typer.Option(
        ..., "--topology-data", "-t", help="The containerlab topology data JSON file"
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
):
    """Remove containerlab integration from EDA"""
    # Set no_proxy environment variable
    os.environ["no_proxy"] = eda_url

    # Create command instance with context parameters
    cmd = RemoveCommand()

    # Create args object with all parameters
    args = typer.Context.with_defaults(
        topology_data=topology_data,
        eda_url=eda_url,
        eda_user=eda_user,
        eda_password=eda_password,
        verify=ctx.obj["verify"],
    )

    # Run the command
    cmd.run(args)


if __name__ == "__main__":
    app(obj={})
