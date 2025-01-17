import logging
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint

from clab_connector.core.eda import EDA
from clab_connector.core.topology import Topology

app = typer.Typer(help="Integrate containerlab with EDA")

@app.command()
def main(
    ctx: typer.Context,
    topology_data: Path = typer.Option(
        ...,
        "--topology-data",
        help="The containerlab topology data JSON file",
        exists=True,
    ),
    eda_url: str = typer.Option(
        ...,
        "--eda-url",
        help="The hostname or IP of your EDA deployment"
    ),
    eda_user: str = typer.Option(
        ...,
        "--eda-user",
        help="The username of the EDA user"
    ),
    eda_password: str = typer.Option(
        ...,
        "--eda-password",
        help="The password of the EDA user",
        prompt=True,
        hide_input=True
    ),
):
    """Integrate a containerlab topology with EDA."""
    try:
        # Initialize EDA client
        eda = EDA(
            url=eda_url,
            username=eda_user,
            password=eda_password,
            verify=ctx.obj.get("verify", False)
        )

        # Load and process topology
        topology = Topology(topology_data)
        topology.integrate_with_eda(eda)

        rprint("[green]Successfully integrated topology with EDA![/green]")
    except Exception as e:
        logging.error(f"Failed to integrate topology: {str(e)}")
        raise typer.Exit(1)