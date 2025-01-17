#!/usr/bin/env python3
import logging
from enum import Enum
from typing import Optional

import typer
from rich.logging import RichHandler

from clab_connector.cli import integrate, remove

SUPPORTED_KINDS = ["nokia_srlinux"]

app = typer.Typer(
    help="Integrate containerlab topology with EDA (Event-Driven Automation)",
    no_args_is_help=True,
)

# Add subcommands
app.add_typer(integrate.app, name="integrate")
app.add_typer(remove.app, name="remove")

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

def setup_logging(log_level: str) -> None:
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

@app.callback()
def common(
    ctx: typer.Context,
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING,
        "--log-level",
        help="Set logging level"
    ),
    verify: bool = typer.Option(
        False,
        "--verify",
        help="Enables certificate verification for EDA"
    ),
):
    """Common parameters and initialization."""
    ctx.ensure_object(dict)
    ctx.obj["verify"] = verify
    setup_logging(log_level.value)
    logging.debug(f"Supported containerlab kinds: {SUPPORTED_KINDS}")

if __name__ == "__main__":
    app()