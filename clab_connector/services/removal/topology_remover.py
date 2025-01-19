# clab_connector/services/removal/topology_remover.py

import logging
from clab_connector.models.topology import parse_topology_file
from clab_connector.clients.eda.client import EDA

logger = logging.getLogger(__name__)


class RemoveCommand:
    PARSER_NAME = "remove"
    PARSER_ALIASES = [PARSER_NAME, "r"]

    def run(self, args):
        self.args = args
        self.topology = parse_topology_file(str(self.args.topology_data))
        self.eda = EDA(
            hostname=args.eda_url,
            username=args.eda_user,
            password=args.eda_password,
            verify=args.verify,
        )

        print("== Removing namespace ==")
        self.remove_namespace()
        self.eda.commit_transaction("remove namespace")
        print("Done!")

    def remove_namespace(self):
        ns = f"clab-{self.topology.name}"
        logger.info(f"Removing namespace {ns}")
        self.eda.add_delete_to_transaction(namespace="", kind="Namespace", name=ns)
