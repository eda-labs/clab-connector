# clab_connector/services/integration/topology_integrator.py

import logging

from clab_connector.models.topology import parse_topology_file
from clab_connector.clients.eda.client import EDAClient
from clab_connector.clients.kubernetes.client import (
    apply_manifest,
    edactl_namespace_bootstrap,
    wait_for_namespace,
    update_namespace_description,
)
from clab_connector.utils import helpers
from clab_connector.utils.exceptions import EDAConnectionError, ClabConnectorError

logger = logging.getLogger(__name__)


class TopologyIntegrator:
    """
    Handles creation of EDA resources for a given containerlab topology.

    Parameters
    ----------
    eda_client : EDAClient
        A connected EDAClient used to submit resources to the EDA cluster.
    """

    def __init__(self, eda_client: EDAClient):
        self.eda_client = eda_client
        self.topology = None

    def run(self, topology_file, eda_url, eda_user, eda_password, verify):
        """
        Parse the topology, run connectivity checks, and create EDA resources.

        Parameters
        ----------
        topology_file : str or Path
            Path to the containerlab topology JSON file.
        eda_url : str
            EDA hostname/IP.
        eda_user : str
            EDA username.
        eda_password : str
            EDA password.
        verify : bool
            Certificate verification flag.

        Returns
        -------
        None

        Raises
        ------
        EDAConnectionError
            If EDA is unreachable or credentials are invalid.
        ClabConnectorError
            If any resource fails validation.
        """
        logger.info("Parsing topology for integration")
        self.topology = parse_topology_file(str(topology_file))
        self.topology.check_connectivity()

        print("== Running pre-checks ==")
        self.prechecks()

        print("== Creating namespace ==")
        self.create_namespace()

        print("== Creating artifacts ==")
        self.create_artifacts()

        print("== Creating init ==")
        self.create_init()
        self.eda_client.commit_transaction("create init (bootstrap)")

        print("== Creating node security profile ==")
        self.create_node_security_profile()

        print("== Creating node users ==")
        self.create_node_user_groups()
        self.create_node_users()
        self.eda_client.commit_transaction("create node users and groups")

        print("== Creating node profiles ==")
        self.create_node_profiles()
        self.eda_client.commit_transaction("create node profiles")

        print("== Onboarding nodes ==")
        self.create_toponodes()
        self.eda_client.commit_transaction("create nodes")

        print("== Adding topolink interfaces ==")
        self.create_topolink_interfaces()
        self.eda_client.commit_transaction("create topolink interfaces")

        print("== Creating topolinks ==")
        self.create_topolinks()
        self.eda_client.commit_transaction("create topolinks")

        print("Done!")

    def prechecks(self):
        """
        Verify that EDA is up and credentials are valid.

        Raises
        ------
        EDAConnectionError
            If EDA is not reachable or not authenticated.
        """
        if not self.eda_client.is_up():
            raise EDAConnectionError("EDA not up or unreachable")
        if not self.eda_client.is_authenticated():
            raise EDAConnectionError("EDA credentials invalid")

    def create_namespace(self):
        """
        Create and bootstrap a namespace for the topology in EDA.
        """
        ns = f"clab-{self.topology.name}"
        edactl_namespace_bootstrap(ns)
        wait_for_namespace(ns)
        desc = f"Containerlab {self.topology.name}: {self.topology.clab_file_path}"
        update_namespace_description(ns, desc)

    def create_artifacts(self):
        """
        Create Artifact resources for nodes that need them.

        Skips creation if already exists or no artifact data is available.
        """
        logger.info("Creating artifacts for nodes that need them")
        nodes_by_artifact = {}
        for node in self.topology.nodes:
            if not node.needs_artifact():
                continue
            artifact_name, filename, download_url = node.get_artifact_info()
            if not artifact_name or not filename or not download_url:
                logger.warning(f"No artifact info for node {node.name}; skipping.")
                continue
            if artifact_name not in nodes_by_artifact:
                nodes_by_artifact[artifact_name] = {
                    "nodes": [],
                    "filename": filename,
                    "download_url": download_url,
                    "version": node.version,
                }
            nodes_by_artifact[artifact_name]["nodes"].append(node.name)

        for artifact_name, info in nodes_by_artifact.items():
            first_node = info["nodes"][0]
            logger.info(
                f"Creating YANG artifact for node: {first_node} (version={info['version']})"
            )
            artifact_yaml = self.topology.nodes[0].get_artifact_yaml(
                artifact_name, info["filename"], info["download_url"]
            )
            if not artifact_yaml:
                logger.warning(f"Could not generate artifact YAML for {first_node}")
                continue
            try:
                apply_manifest(artifact_yaml, namespace="eda-system")
                logger.info(f"Artifact '{artifact_name}' created.")
                other_nodes = info["nodes"][1:]
                if other_nodes:
                    logger.info(
                        f"Using same artifact for nodes: {', '.join(other_nodes)}"
                    )
            except RuntimeError as ex:
                if "AlreadyExists" in str(ex):
                    logger.info(f"Artifact '{artifact_name}' already exists.")
                else:
                    logger.error(f"Error creating artifact '{artifact_name}': {ex}")

    def create_init(self):
        """
        Create an Init resource in the namespace to bootstrap additional resources.
        """
        data = {"namespace": f"clab-{self.topology.name}"}
        yml = helpers.render_template("init.yaml.j2", data)
        item = self.eda_client.add_replace_to_transaction(yml)
        if not self.eda_client.is_transaction_item_valid(item):
            raise ClabConnectorError("Validation error for init resource")

    def create_node_security_profile(self):
        """
        Create a NodeSecurityProfile resource that references an EDA node issuer.
        """
        data = {"namespace": f"clab-{self.topology.name}"}
        yaml_str = helpers.render_template("nodesecurityprofile.yaml.j2", data)
        try:
            apply_manifest(yaml_str, namespace=f"clab-{self.topology.name}")
            logger.info("Node security profile created.")
        except RuntimeError as ex:
            if "AlreadyExists" in str(ex):
                logger.info("Node security profile already exists, skipping.")
            else:
                raise

    def create_node_user_groups(self):
        """
        Create a NodeGroup resource for user groups (like 'sudo').
        """
        data = {"namespace": f"clab-{self.topology.name}"}
        node_user_group = helpers.render_template("node-user-group.yaml.j2", data)
        item = self.eda_client.add_replace_to_transaction(node_user_group)
        if not self.eda_client.is_transaction_item_valid(item):
            raise ClabConnectorError("Validation error for node user group")

    def create_node_users(self):
        """
        Create a NodeUser resource with SSH pub keys, if any.
        """
        data = {
            "namespace": f"clab-{self.topology.name}",
            "node_user": "admin",
            "username": "admin",
            "password": "NokiaSrl1!",
            "ssh_pub_keys": getattr(self.topology, "ssh_pub_keys", []),
        }
        node_user = helpers.render_template("node-user.j2", data)
        item = self.eda_client.add_replace_to_transaction(node_user)
        if not self.eda_client.is_transaction_item_valid(item):
            raise ClabConnectorError("Validation error for node user")

    def create_node_profiles(self):
        """
        Create NodeProfile resources for each EDA-supported node version-kind combo.
        """
        profiles = self.topology.get_node_profiles()
        for prof_yaml in profiles:
            item = self.eda_client.add_replace_to_transaction(prof_yaml)
            if not self.eda_client.is_transaction_item_valid(item):
                raise ClabConnectorError("Validation error creating node profile")

    def create_toponodes(self):
        """
        Create TopoNode resources for each node.
        """
        tnodes = self.topology.get_toponodes()
        for node_yaml in tnodes:
            item = self.eda_client.add_replace_to_transaction(node_yaml)
            if not self.eda_client.is_transaction_item_valid(item):
                raise ClabConnectorError("Validation error creating toponode")

    def create_topolink_interfaces(self):
        """
        Create Interface resources for each link endpoint in the topology.
        """
        interfaces = self.topology.get_topolink_interfaces()
        for intf_yaml in interfaces:
            item = self.eda_client.add_replace_to_transaction(intf_yaml)
            if not self.eda_client.is_transaction_item_valid(item):
                raise ClabConnectorError("Validation error creating topolink interface")

    def create_topolinks(self):
        """
        Create TopoLink resources for each EDA-supported link in the topology.
        """
        links = self.topology.get_topolinks()
        for l_yaml in links:
            item = self.eda_client.add_replace_to_transaction(l_yaml)
            if not self.eda_client.is_transaction_item_valid(item):
                raise ClabConnectorError("Validation error creating topolink")
