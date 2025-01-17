import json
import logging
import os.path
import sys
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from clab_connector.core.topology import Topology

# set up jinja2 templating engine
template_loader = FileSystemLoader(searchpath="templates")
template_environment = Environment(loader=template_loader)

# set up logging
logger = logging.getLogger(__name__)


def parse_topology(topology_file) -> "Topology":
    """
    Parses a topology file from JSON

    Parameters
    ----------
    topology_file: topology-data file (json format)

    Returns
    -------
    A parsed Topology object
    """
    from clab_connector.core.topology import (
        Topology,
    )  # Import here to avoid circular import

    logger.info(f"Parsing topology file '{topology_file}'")
    if not os.path.isfile(topology_file):
        logger.critical(f"Topology file '{topology_file}' does not exist!")
        sys.exit(1)

    try:
        with open(topology_file, "r") as f:
            data = json.load(f)
            # Check if this is a topology-data.json file
            if "type" in data and data["type"] == "clab":
                topo = Topology(data["name"], "", [], [])
                topo = topo.from_topology_data(data)
                # Sanitize the topology name after parsing
                original_name = topo.name
                topo.name = topo.get_eda_safe_name()
                logger.info(
                    f"Sanitized topology name from '{original_name}' to '{topo.name}'"
                )
                return topo
            # If not a topology-data.json file, error our
            raise Exception("Not a valid topology data file provided")
    except json.JSONDecodeError:
        logger.critical(
            f"File '{topology_file}' is not supported. Please provide a valid JSON topology file."
        )
        sys.exit(1)
