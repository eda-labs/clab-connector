import json
import logging
import os.path
import subprocess
import sys
import tempfile

import urllib3
from jinja2 import Environment, FileSystemLoader

import src.topology as topology

# set up jinja2 templating engine
template_loader = FileSystemLoader(searchpath="templates")
template_environment = Environment(loader=template_loader)

# set up logging
logger = logging.getLogger(__name__)

# Create a global urllib3 pool manager
http = urllib3.PoolManager(
    retries=urllib3.Retry(3)
)

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
    Applies the given resource via `kubectl apply -f` in the specified namespace.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".yaml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(yaml_str)

        cmd = ["kubectl", "apply", "-n", namespace, "-f", tmp_path]
        logger.debug(f"Running command: {cmd}")

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Raise an error so the caller can parse if it's "AlreadyExists" or some other error
            raise RuntimeError(
                f"kubectl create failed:\nstdout={result.stdout}\nstderr={result.stderr}"
            )
        else:
            logger.info(f"kubectl apply succeeded:\n{result.stdout}")
    finally:
        os.remove(tmp_path)


def get_artifact_from_github(owner: str, repo: str, version: str, asset_filter=None):
    """
    Queries GitHub for a specific release artifact using urllib3.

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

    # Log proxy environment
    logger.info(f"HTTP_PROXY: {os.environ.get('HTTP_PROXY', 'not set')}")
    logger.info(f"HTTPS_PROXY: {os.environ.get('HTTPS_PROXY', 'not set')}")
    logger.info(f"NO_PROXY: {os.environ.get('NO_PROXY', 'not set')}")
    
    # Log request details
    logger.info(f"Making request to: {url}")
    logger.info(f"Using pool manager type: {type(http).__name__}")
    
    try:
        response = http.request('GET', url)
        logger.info(f"Response status: {response.status}")
        logger.info(f"Response headers: {response.headers}")
        
        if response.status != 200:
            logger.info(f"Failed to fetch release for {tag}, status={response.status}")
            logger.info(f"Response data: {response.data.decode('utf-8')}")
            return None, None

        data = json.loads(response.data.decode('utf-8'))
        assets = data.get("assets", [])
        logger.info(f"Found {len(assets)} assets in release")

        for asset in assets:
            name = asset.get("name", "")
            logger.info(f"Checking asset: {name}")
            if asset_filter is None or asset_filter(name):
                download_url = asset.get("browser_download_url")
                logger.info(f"Found matching asset: {name} with URL: {download_url}")
                return name, download_url
            else:
                logger.info(f"Asset {name} did not match filter")

    except urllib3.exceptions.HTTPError as e:
        logger.info(f"HTTP error occurred: {e}")
        logger.info(f"Error details: {str(e)}")
    except json.JSONDecodeError as e:
        logger.info(f"JSON decode error: {e}")
        logger.info(f"Raw response: {response.data.decode('utf-8')}")
    except Exception as e:
        logger.info(f"Unexpected error: {e}")
        logger.info(f"Error type: {type(e).__name__}")
        logger.info(f"Error details: {str(e)}")

    # No matching asset found
    logger.info("No matching asset found")
    return None, None


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
