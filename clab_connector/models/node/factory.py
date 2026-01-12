# clab_connector/models/node/factory.py

import logging

from .arista_ceos import AristaCEOSNode
from .base import Node
from .nokia_srl import NokiaSRLinuxNode
from .nokia_sros import NokiaSROSNode

logger = logging.getLogger(__name__)

KIND_MAPPING = {
    "nokia_srlinux": NokiaSRLinuxNode,
    "nokia_sros": NokiaSROSNode,
    "nokia_srsim": NokiaSROSNode,
    "arista_ceos": AristaCEOSNode,
}


def create_node(name: str, config: dict) -> Node:
    """
    Create a node instance based on the kind specified in config.

    Parameters
    ----------
    name : str
        The name of the node.
    config : dict
        A dictionary containing 'kind', 'type', 'version', 'mgmt_ipv4', etc.

    Returns
    -------
    Node or None
        An appropriate Node subclass instance if supported; otherwise None.
    """
    kind = config.get("kind")
    if not kind:
        logger.error(f"No 'kind' in config for node '{name}'")
        return None

    cls = KIND_MAPPING.get(kind)
    if cls is None:
        logger.info(f"Unsupported kind '{kind}' for node '{name}'")
        return None

    return cls(
        name=name,
        kind=kind,
        node_type=config.get("type"),
        version=config.get("version"),
        mgmt_ipv4=config.get("mgmt_ipv4"),
        mgmt_ipv4_prefix_length=config.get("mgmt_ipv4_prefix_length"),
        labels=config.get("labels"),
    )
