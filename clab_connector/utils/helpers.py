# clab_connector/utils/helpers.py

import os
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(PACKAGE_ROOT, "templates")

template_environment = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape()
)


def render_template(template_name: str, data: dict) -> str:
    """
    Render a Jinja2 template by name, using a data dictionary.

    Parameters
    ----------
    template_name : str
        The name of the template file (e.g., "node-profile.j2").
    data : dict
        A dictionary of values to substitute into the template.

    Returns
    -------
    str
        The rendered template as a string.
    """
    template = template_environment.get_template(template_name)
    return template.render(data)


def normalize_name(name: str) -> str:
    """
    Convert a name to a normalized, EDA-safe format.

    Parameters
    ----------
    name : str
        The original name.

    Returns
    -------
    str
        The normalized name.
    """
    safe_name = name.lower().replace("_", "-").replace(" ", "-")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in ".-").strip(".-")
    if not safe_name or not safe_name[0].isalnum():
        safe_name = "x" + safe_name
    if not safe_name[-1].isalnum():
        safe_name += "0"
    return safe_name
