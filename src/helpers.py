import os.path
import logging
import yaml

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
