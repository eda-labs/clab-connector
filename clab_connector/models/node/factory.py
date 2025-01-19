# clab_connector/models/node/factory.py

import logging
from .base import Node
from .nokia_srl import NokiaSRLinuxNode

logger = logging.getLogger(__name__)

KIND_MAPPING = {
    "nokia_srlinux": NokiaSRLinuxNode,
}


def create_node(name: str, config: dict) -> Node:
    kind = config.get("kind")
    if not kind:
        logger.error(f"No 'kind' in config for node '{name}'")
        return None

    cls = KIND_MAPPING.get(kind)
    if cls is None:
        logger.warning(f"Unsupported kind '{kind}' for node '{name}'")
        return None

    return cls(
        name=name,
        kind=kind,
        node_type=config.get("type"),
        version=config.get("version"),
        mgmt_ipv4=config.get("mgmt_ipv4"),
    )
