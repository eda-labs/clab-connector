import json
import logging
import os.path
import sys
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, select_autoescape

if TYPE_CHECKING:
    from clab_connector.core.topology import Topology

# Get the path to the package root (clab_connector directory)
PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(PACKAGE_ROOT, "templates")

# Create the Jinja2 environment with the correct template directory
template_environment = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape()
)

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
                # Initialize with empty values, will be populated by from_topology_data
                topo = Topology(
                    name=data["name"],
                    mgmt_ipv4_subnet="",
                    ssh_pub_keys=data.get(
                        "ssh-pub-keys", []
                    ),  # Get SSH keys with empty list as default
                    nodes=[],
                    links=[],
                )
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


def render_template(template_name, data):
    """
    Loads a jinja template and renders it with the data provided

    Parameters
    ----------
    template_name:  name of the template in the 'templates' folder
    data:           data to be rendered in the template

    Returns
    -------
    The rendered template, as str
    """
    template = template_environment.get_template(template_name)
    return template.render(data)


def normalize_name(name: str) -> str:
    """
    Returns a Kubernetes-compliant name by:
        - Converting to lowercase
        - Replacing underscores and spaces with hyphens
        - Removing any other invalid characters
        - Ensuring it starts and ends with alphanumeric characters
    """
    # Convert to lowercase and replace underscores/spaces with hyphens
    safe_name = name.lower().replace("_", "-").replace(" ", "-")

    # Remove any characters that aren't lowercase alphanumeric, dots or hyphens
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in ".-")

    # Ensure it starts and ends with alphanumeric character
    safe_name = safe_name.strip(".-")

    # Handle empty string or invalid result
    if not safe_name or not safe_name[0].isalnum():
        safe_name = "x" + safe_name
    if not safe_name[-1].isalnum():
        safe_name = safe_name + "0"

    return safe_name
