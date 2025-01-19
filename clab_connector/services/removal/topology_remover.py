# clab_connector/services/removal/topology_remover.py

import logging

from clab_connector.models.topology import parse_topology_file
from clab_connector.clients.eda.client import EDAClient

logger = logging.getLogger(__name__)


class TopologyRemover:
    """
    Handles removal of EDA resources for a given containerlab topology.

    Parameters
    ----------
    eda_client : EDAClient
        A connected EDAClient used to remove resources from the EDA cluster.
    """

    def __init__(self, eda_client: EDAClient):
        self.eda_client = eda_client
        self.topology = None

    def run(self, topology_file):
        """
        Parse the topology file and remove its associated namespace.

        Parameters
        ----------
        topology_file : str or Path
            The containerlab topology JSON file.

        Returns
        -------
        None
        """
        self.topology = parse_topology_file(str(topology_file))

        print("== Removing namespace ==")
        self.remove_namespace()
        self.eda_client.commit_transaction("remove namespace")

        print("Done!")

    def remove_namespace(self):
        """
        Delete the EDA namespace corresponding to this topology.
        """
        ns = f"clab-{self.topology.name}"
        logger.info(f"Removing namespace {ns}")
        self.eda_client.add_delete_to_transaction(
            namespace="", kind="Namespace", name=ns
        )
