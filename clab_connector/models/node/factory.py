# clab_connector/models/node/factory.py

import logging

from .base import Node
from .nokia_srl import NokiaSRLinuxNode

logger = logging.getLogger(__name__)

KIND_MAPPING = {
    "nokia_srlinux": NokiaSRLinuxNode,
    # later we can add "sonic": SonicNode, etc.
}

def create_node(name: str, config: dict) -> Node:
    """
    Minimal factory function, replacing the old approach.
    config e.g. {
      "kind": "nokia_srlinux",
      "type": "ixrd3l",
      "version": "24.10.1",
      "mgmt_ipv4": "10.1.1.10"
    }
    """
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
