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
    Applies the given YAML string in the specified namespace via 'kubectl apply'.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".yaml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(yaml_str)

        cmd = ["kubectl", "apply", "-n", namespace, "-f", tmp_path]
        logger.info(f"Applying manifest with: {cmd}")

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to apply manifest:\nstdout={result.stdout}\nstderr={result.stderr}"
            )
        else:
            logger.info(f"Successfully applied manifest:\n{result.stdout}")
    finally:
        os.remove(tmp_path)

def get_srlinux_artifact_from_github(version: str):
    """
    Queries the GitHub Releases API for 'nokia/srlinux-yang-models' at tag 'v<version>'.
    Returns a tuple (artifact_filename, artifact_url).
    Returns (None, None) if no suitable asset is found.
    """
    tag = f"v{version}"  # e.g. "v24.10.1"
    api_url = f"https://api.github.com/repos/nokia/srlinux-yang-models/releases/tags/{tag}"

    resp = requests.get(api_url)
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch release info for {tag}: HTTP {resp.status_code} - {resp.text}")

    data = resp.json()
    assets = data.get("assets", [])

    for asset in assets:
        # e.g. "srlinux-24.10.1-492.zip", "Source code (zip)", "Source code (tar.gz)"
        name = asset.get("name", "")
        download_url = asset.get("browser_download_url", "")
        if "Source code" in name:
            # skip the built-in source code assets
            continue
        if name.endswith(".zip") and name.startswith("srlinux-"):
            # likely our main artifact, e.g. "srlinux-24.10.1-492.zip"
            
            logger.info(name)
            logger.info(download_url)
            return (name, download_url)

    # If we didn't find a matching asset
    return (None, None)
