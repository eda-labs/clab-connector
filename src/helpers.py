import os.path
import logging
import yaml
import requests
import subprocess
import tempfile

import src.topology as topology

from jinja2 import Environment, FileSystemLoader

# set up jinja2 templating engine
template_loader = FileSystemLoader(searchpath="templates")
template_environment = Environment(loader=template_loader)

# set up logging
logger = logging.getLogger(__name__)


def parse_topology(topology_file):
    """
    Parses a topology yml file

    Parameters
    ----------
    topology_file: containerlab topology file (yaml format)

    Returns
    -------
    A parsed Topology file
    """
    logger.info(f"Parsing topology file '{topology_file}'")
    if not os.path.isfile(topology_file):
        raise Exception(f"Topology file '{topology_file}' does not exist!")

    with open(topology_file, "r") as f:
        try:
            obj = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            logger.critical(f"Failed to parse yaml file '{topology_file}'")
            raise exc

    return topology.from_obj(obj)


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