# clab_connector/services/removal/topology_remover.py

import logging

from clab_connector.models.topology import parse_topology_file
from clab_connector.clients.eda.client import EDAClient

logger = logging.getLogger(__name__)


class TopologyRemover:
    """
    Formerly RemoveCommand
    Demonstrates EDAClient injection for removal
    """

    def __init__(self, eda_client: EDAClient):
        self.eda_client = eda_client
        self.topology = None

    def run(self, topology_file):
        self.topology = parse_topology_file(str(topology_file))

        print("== Removing namespace ==")
        self.remove_namespace()
        self.eda_client.commit_transaction("remove namespace")

        print("Done!")

    def remove_namespace(self):
        ns = f"clab-{self.topology.name}"
        logger.info(f"Removing namespace {ns}")
        self.eda_client.add_delete_to_transaction(
            namespace="", kind="Namespace", name=ns
        )
