import json
import logging
import os.path
import subprocess
import sys
import tempfile

import requests
from jinja2 import Environment, FileSystemLoader

import src.topology as topology

# set up jinja2 templating engine
template_loader = FileSystemLoader(searchpath="templates")
template_environment = Environment(loader=template_loader)

# set up logging
logger = logging.getLogger(__name__)


def parse_topology(topology_file) -> topology.Topology:
    """
    Parses a topology file from JSON

    Parameters
    ----------
    topology_file: topology-data file (json format)

    Returns
    -------
    A parsed Topology object
    """
    logger.info(f"Parsing topology file '{topology_file}'")
    if not os.path.isfile(topology_file):
        logger.critical(f"Topology file '{topology_file}' does not exist!")
        sys.exit(1)

    try:
        with open(topology_file, "r") as f:
            data = json.load(f)
            # Check if this is a topology-data.json file
            if "type" in data and data["type"] == "clab":
                topo = topology.Topology(data["name"], "", [], [])
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


def apply_manifest_via_kubectl(yaml_str: str, namespace: str = "eda-system"):
    """
    Creates the given resource via `kubectl create -f` in the specified namespace.
    If the resource already exists, 'AlreadyExists' will appear in stderr,
    and we raise RuntimeError so the caller can decide what to do.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".yaml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(yaml_str)

        cmd = ["kubectl", "create", "-n", namespace, "-f", tmp_path, "--save-config"]
        logger.debug(f"Running command: {cmd}")

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Raise an error so the caller can parse if it's "AlreadyExists" or some other error
            raise RuntimeError(
                f"kubectl create failed:\nstdout={result.stdout}\nstderr={result.stderr}"
            )
        else:
            logger.info(f"kubectl create succeeded:\n{result.stdout}")
    finally:
        os.remove(tmp_path)


def get_artifact_from_github(owner: str, repo: str, version: str, asset_filter=None):
    """
    Queries GitHub for a specific release artifact.

    Parameters
    ----------
    owner:          GitHub repository owner
    repo:           GitHub repository name
    version:        Version tag to search for (without 'v' prefix)
    asset_filter:   Optional function(asset_name) -> bool to filter assets

    Returns
    -------
    Tuple of (filename, download_url) or (None, None) if not found
    """
    tag = f"v{version}"  # Assume GitHub tags are prefixed with 'v'
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"

    logger.info(f"Querying GitHub release {tag} from {owner}/{repo}")
    resp = requests.get(url)

    if resp.status_code != 200:
        logger.warning(f"Failed to fetch release for {tag}, status={resp.status_code}")
        return None, None

    data = resp.json()
    assets = data.get("assets", [])

    for asset in assets:
        name = asset.get("name", "")
        if asset_filter is None or asset_filter(name):
            return name, asset.get("browser_download_url")

    # No matching asset found
    return None, None
