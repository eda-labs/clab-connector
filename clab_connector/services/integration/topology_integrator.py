# clab_connector/services/integration/topology_integrator.py (updated)

import logging
import time

from clab_connector.clients.eda.client import EDAClient
from clab_connector.clients.kubernetes.client import (
    apply_manifest,
    edactl_namespace_bootstrap,
    update_namespace_description,
    wait_for_namespace,
)
from clab_connector.models.topology import parse_topology_file
from clab_connector.services.integration.ceos_post_integration import prepare_ceos_node
from clab_connector.services.integration.sros_post_integration import prepare_sros_node
from clab_connector.services.status.node_sync_checker import NodeSyncChecker
from clab_connector.utils import helpers
from clab_connector.utils.constants import SUBSTEP_INDENT
from clab_connector.utils.exceptions import ClabConnectorError, EDAConnectionError

logger = logging.getLogger(__name__)


class TopologyIntegrator:
    """
    Handles creation of EDA resources for a given containerlab topology.

    Parameters
    ----------
    eda_client : EDAClient
        A connected EDAClient used to submit resources to the EDA cluster.
    """

    def __init__(
        self,
        eda_client: EDAClient,
        enable_sync_checking: bool = True,
        sync_timeout: int = 90,
    ):
        self.eda_client = eda_client
        self.topology = None
        self.enable_sync_checking = enable_sync_checking
        self.sync_timeout = sync_timeout

    def run(
        self,
        topology_file,
        skip_edge_intfs: bool = False,
        namespace_override: str | None = None,
    ):
        """
        Parse the topology, run connectivity checks, and create EDA resources.

        Parameters
        ----------
        topology_file : str or Path
            Path to the containerlab topology JSON file.
        skip_edge_intfs : bool
            When True, omit edge link resources and their interfaces from the
            integration.
        namespace_override : str | None
            Optional namespace override to use instead of the derived name.

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
        self.topology = parse_topology_file(
            str(topology_file), namespace=namespace_override
        )

        logger.info(
            f"Using namespace: '{self.topology.namespace}'"
            + (
                " (overridden)"
                if self.topology.namespace_overridden
                else " (from topology)"
            )
        )

        logger.info("== Running pre-checks ==")
        self.prechecks()

        # Verify connectivity to each node's management interface
        self.topology.check_connectivity()

        logger.info("== Creating namespace ==")
        self.create_namespace()

        logger.info("== Creating artifacts ==")
        self.create_artifacts()

        logger.info("== Creating init ==")
        self.create_init()
        self.commit_transaction("create init (bootstrap)")

        logger.info("== Creating node security profile ==")
        self.create_node_security_profile()

        logger.info("== Creating node users ==")
        self.create_node_user_groups()
        self.create_node_users()
        self.commit_transaction("create node users and groups")

        logger.info("== Creating node profiles ==")
        self.create_node_profiles()
        self.commit_transaction("create node profiles")

        logger.info("== Onboarding nodes ==")
        self.create_toponodes()
        # Nodes are committed in batches within create_toponodes method

        logger.info("== Adding topolink interfaces ==")
        self.create_topolink_interfaces(skip_edge_intfs)
        # Only commit if there are transactions
        if self.eda_client.transactions:
            self.commit_transaction("create topolink interfaces")
        else:
            logger.info(f"{SUBSTEP_INDENT}No topolink interfaces to create, skipping.")

        logger.info("== Creating topolinks ==")
        self.create_topolinks(skip_edge_intfs)
        # Only commit if there are transactions
        if self.eda_client.transactions:
            self.commit_transaction("create topolinks")
        else:
            logger.info(f"{SUBSTEP_INDENT}No topolinks to create, skipping.")

        logger.info("== Running post-integration steps ==")
        self.run_post_integration()

        # Check node synchronization if enabled
        if self.enable_sync_checking:
            logger.info("== Checking node synchronization ==")
            self.check_node_synchronization()

        logger.info("Done!")

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
        ns = self.topology.namespace
        try:
            edactl_namespace_bootstrap(ns)
            wait_for_namespace(ns)
            desc = f"Containerlab {self.topology.name}: {self.topology.clab_file_path}"
            success = update_namespace_description(ns, desc)
            if not success:
                logger.warning(
                    f"{SUBSTEP_INDENT}Created namespace '{ns}' but could not update its description. Continuing with integration."
                )
        except Exception as e:
            # If namespace creation itself fails, we should stop the process
            logger.error(f"Failed to create namespace '{ns}': {e}")
            raise

    def create_artifacts(self):
        """
        Create Artifact resources for nodes that need them.

        Skips creation if already exists or no artifact data is available.
        """
        logger.info(f"{SUBSTEP_INDENT}Creating artifacts for nodes that need them")
        nodes_by_artifact = {}
        for node in self.topology.nodes:
            if not node.needs_artifact():
                continue
            artifact_name, filename, download_url = node.get_artifact_info()
            if not artifact_name or not filename or not download_url:
                logger.warning(
                    f"{SUBSTEP_INDENT}No artifact info for node {node.name}; skipping."
                )
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
                f"{SUBSTEP_INDENT}Creating YANG artifact for node: {first_node} (version={info['version']})"
            )
            artifact_yaml = self.topology.nodes[0].get_artifact_yaml(
                artifact_name, info["filename"], info["download_url"]
            )
            if not artifact_yaml:
                logger.warning(
                    f"{SUBSTEP_INDENT}Could not generate artifact YAML for {first_node}"
                )
                continue
            try:
                apply_manifest(artifact_yaml, namespace="eda-system")
                logger.info(f"{SUBSTEP_INDENT}Artifact '{artifact_name}' created.")
                other_nodes = info["nodes"][1:]
                if other_nodes:
                    logger.info(
                        f"{SUBSTEP_INDENT}Using same artifact for nodes: {', '.join(other_nodes)}"
                    )
            except RuntimeError as ex:
                if "AlreadyExists" in str(ex):
                    logger.info(
                        f"{SUBSTEP_INDENT}Artifact '{artifact_name}' already exists."
                    )
                else:
                    logger.error(f"Error creating artifact '{artifact_name}': {ex}")

    def commit_transaction(self, description: str):
        """Commit a transaction"""
        return self.eda_client.commit_transaction(description)

    def create_init(self):
        """
        Create an Init resource in the namespace to bootstrap additional resources.
        """
        data = {
            "name": "init-base",
            "namespace": self.topology.namespace,
            "nodeselectors": ["containerlab=managedSrl", "containerlab=managedSros"],
        }
        yml = helpers.render_template("init.yaml.j2", data)
        item = self.eda_client.add_replace_to_transaction(yml)
        if not self.eda_client.is_transaction_item_valid(item):
            raise ClabConnectorError("Validation error for init resource")

        ceos_data = {
            "name": "init-base-ceos",
            "namespace": self.topology.namespace,
            "gateway": self.topology.mgmt_ipv4_gw,
            "nodeselectors": ["containerlab=managedEos"],
        }
        ceos_yml = helpers.render_template("init.yaml.j2", ceos_data)
        ceos_item = self.eda_client.add_replace_to_transaction(ceos_yml)
        if not self.eda_client.is_transaction_item_valid(ceos_item):
            raise ClabConnectorError("Validation error for cEOS init resource")

    def create_node_security_profile(self):
        """
        Create a NodeSecurityProfile resource that references an EDA node issuer.
        """
        data = {"namespace": self.topology.namespace}
        yaml_str = helpers.render_template("nodesecurityprofile.yaml.j2", data)
        try:
            apply_manifest(yaml_str, namespace=self.topology.namespace)
            logger.info(f"{SUBSTEP_INDENT}Node security profile created.")
        except RuntimeError as ex:
            if "AlreadyExists" in str(ex):
                logger.info(
                    f"{SUBSTEP_INDENT}Node security profile already exists, skipping."
                )
            else:
                raise

    def create_node_user_groups(self):
        """
        Create a NodeGroup resource for user groups (like 'sudo').
        """
        data = {"namespace": self.topology.namespace}
        node_user_group = helpers.render_template("node-user-group.yaml.j2", data)
        item = self.eda_client.add_replace_to_transaction(node_user_group)
        if not self.eda_client.is_transaction_item_valid(item):
            raise ClabConnectorError("Validation error for node user group")

    def create_node_users(self):
        """
        Create NodeUser resources with SSH pub keys for SRL and SROS nodes.
        """
        ssh_pub_keys = getattr(self.topology, "ssh_pub_keys", [])
        if not ssh_pub_keys:
            logger.warning(
                f"{SUBSTEP_INDENT}No SSH public keys found. Proceeding with an empty key list."
            )

        # Create SRL node user
        srl_data = {
            "namespace": self.topology.namespace,
            "node_user": "admin",
            "username": "admin",
            "password": "NokiaSrl1!",
            "ssh_pub_keys": ssh_pub_keys,
            "node_selector": "containerlab=managedSrl",
        }
        srl_node_user = helpers.render_template("node-user.j2", srl_data)
        item_srl = self.eda_client.add_replace_to_transaction(srl_node_user)
        if not self.eda_client.is_transaction_item_valid(item_srl):
            raise ClabConnectorError("Validation error for SRL node user")

        # Create SROS node user
        sros_data = {
            "namespace": self.topology.namespace,
            "node_user": "admin-sros",
            "username": "admin",
            "password": "NokiaSros1!",
            "ssh_pub_keys": ssh_pub_keys,
            "node_selector": "containerlab=managedSros",
        }
        sros_node_user = helpers.render_template("node-user.j2", sros_data)
        item_sros = self.eda_client.add_replace_to_transaction(sros_node_user)
        if not self.eda_client.is_transaction_item_valid(item_sros):
            raise ClabConnectorError("Validation error for SROS node user")

        # Create cEOS node user
        ceos_data = {
            "namespace": self.topology.namespace,
            "node_user": "admin-ceos",
            "username": "admin",
            "password": "admin",
            "ssh_pub_keys": ssh_pub_keys,
            "node_selector": "containerlab=managedEos",
        }
        ceos_node_user = helpers.render_template("node-user.j2", ceos_data)
        item_ceos = self.eda_client.add_replace_to_transaction(ceos_node_user)
        if not self.eda_client.is_transaction_item_valid(item_ceos):
            raise ClabConnectorError("Validation error for cEOS node user")

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
        """Create TopoNode resources for each node in batches."""

        tnodes = self.topology.get_toponodes()
        if not tnodes:
            logger.info(f"{SUBSTEP_INDENT}No TopoNodes to create")
            return

        # Process nodes in smaller batches
        batch_size = 3  # Process 3 nodes at a time
        batch_delay = 2  # Wait 2 seconds between batches

        logger.info(
            f"{SUBSTEP_INDENT}Creating {len(tnodes)} TopoNodes in batches of {batch_size}"
        )

        for i in range(0, len(tnodes), batch_size):
            batch = tnodes[i : i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(tnodes) + batch_size - 1) // batch_size

            logger.info(
                f"{SUBSTEP_INDENT}Processing batch {batch_num}/{total_batches} ({len(batch)} nodes)..."
            )

            # Clear any existing transactions for this batch
            if hasattr(self.eda_client, "transactions"):
                self.eda_client.transactions = []

            # Add nodes in this batch to transaction
            for node_yaml in batch:
                item = self.eda_client.add_replace_to_transaction(node_yaml)
                if not self.eda_client.is_transaction_item_valid(item):
                    raise ClabConnectorError("Validation error creating toponode")

            # Commit this batch
            try:
                self.commit_transaction(f"create nodes batch {batch_num}")
                logger.info(
                    f"{SUBSTEP_INDENT}Batch {batch_num}/{total_batches} committed successfully"
                )
            except Exception as e:
                logger.error(f"Failed to commit batch {batch_num}/{total_batches}: {e}")
                raise

            # Wait between batches (except for the last batch)
            if i + batch_size < len(tnodes):
                logger.debug(
                    f"{SUBSTEP_INDENT}Waiting {batch_delay}s before next batch..."
                )
                time.sleep(batch_delay)

    def create_topolink_interfaces(self, skip_edge_intfs: bool = False):
        """
        Create Interface resources for each link endpoint in the topology.
        """
        interfaces = self.topology.get_topolink_interfaces(
            skip_edge_link_interfaces=skip_edge_intfs
        )
        for intf_yaml in interfaces:
            item = self.eda_client.add_replace_to_transaction(intf_yaml)
            if not self.eda_client.is_transaction_item_valid(item):
                raise ClabConnectorError("Validation error creating topolink interface")

    def create_topolinks(self, skip_edge_links: bool = False):
        """Create TopoLink resources for each EDA-supported link in the topology.

        Parameters
        ----------
        skip_edge_links : bool, optional
            When True, omit TopoLink resources for edge links. Defaults to False.
        """
        links = self.topology.get_topolinks(skip_edge_links=skip_edge_links)
        for l_yaml in links:
            item = self.eda_client.add_replace_to_transaction(l_yaml)
            if not self.eda_client.is_transaction_item_valid(item):
                raise ClabConnectorError("Validation error creating topolink")

    def run_sros_post_integration(self, node, namespace, normalized_version, quiet):
        """Run SROS post-integration"""
        password = "NokiaSros1!"
        if node.kind == "nokia_sros":
            password = "admin"
        return prepare_sros_node(
            node_name=node.get_node_name(self.topology),
            namespace=namespace,
            version=normalized_version,
            mgmt_ip=node.mgmt_ipv4,
            username="admin",
            password=password,
            node_type=node.kind,
            quiet=quiet,
        )

    def run_ceos_post_integration(self, node, namespace, normalized_version, quiet):
        """Run CEOS post-integration"""
        password = "admin"
        return prepare_ceos_node(
            node_name=node.get_node_name(self.topology),
            namespace=namespace,
            version=normalized_version,
            mgmt_ip=node.mgmt_ipv4,
            username="admin",
            password=password,
            quiet=quiet,
        )

    def run_post_integration(self):
        """
        Run any post-integration steps required for specific node types.
        """
        namespace = self.topology.namespace
        # Determine if we should be quiet based on the current log level
        quiet = logging.getLogger().getEffectiveLevel() > logging.INFO

        # Look for SROS nodes and run post-integration for them
        for node in self.topology.nodes:
            if node.kind in {"nokia_sros", "nokia_srsim"}:
                logger.info(
                    f"{SUBSTEP_INDENT}Running SROS post-integration for node {node.name} kind {node.kind}"
                )
                try:
                    # Get normalized version from the node
                    normalized_version = node._normalize_version(node.version)
                    success = self.run_sros_post_integration(
                        node, namespace, normalized_version, quiet
                    )
                    if success:
                        logger.info(
                            f"{SUBSTEP_INDENT}SROS post-integration for {node.name} completed successfully"
                        )
                    else:
                        logger.error(f"SROS post-integration for {node.name} failed")
                except Exception as e:
                    logger.error(
                        f"Error during SROS post-integration for {node.name}: {e}"
                    )
            elif node.kind in {"arista_ceos"}:
                logger.info(
                    f"{SUBSTEP_INDENT}Running cEOS post-integration for node {node.name} kind {node.kind}"
                )
                try:
                    # Get normalized version from the node
                    normalized_version = node._normalize_version(node.version)
                    success = self.run_ceos_post_integration(
                        node, namespace, normalized_version, quiet
                    )
                    if success:
                        logger.info(
                            f"{SUBSTEP_INDENT}cEOS post-integration for {node.name} completed successfully"
                        )
                    else:
                        logger.error(f"cEOS post-integration for {node.name} failed")
                except Exception as e:
                    logger.error(
                        f"Error during cEOS post-integration for {node.name}: {e}"
                    )

    def check_node_synchronization(self):
        """Check that all nodes are properly synchronized in EDA (simplified, no retries)"""
        if not self.topology or not self.topology.nodes:
            logger.warning("No nodes to check for synchronization")
            return

        namespace = self.topology.namespace
        node_names = [node.get_node_name(self.topology) for node in self.topology.nodes]

        sync_checker = NodeSyncChecker(self.eda_client, namespace)

        # Simple wait for nodes to be ready
        if sync_checker.wait_for_nodes_ready(
            node_names, timeout=self.sync_timeout, use_log_view=True
        ):
            logger.info(f"{SUBSTEP_INDENT}All nodes synchronized successfully!")
        else:
            # Just report the final status without retrying
            final_summary = sync_checker.get_sync_summary(node_names)
            logger.info("Node synchronization completed:")
            logger.info(
                f"  Ready: {final_summary['ready_nodes']}/{final_summary['total_nodes']}"
            )
            if final_summary["error_nodes"] > 0:
                logger.info(f"  Errors: {final_summary['error_nodes']}")
            if final_summary["pending_nodes"] > 0:
                logger.info(f"  Pending: {final_summary['pending_nodes']}")
            if final_summary["unknown_nodes"] > 0:
                logger.info(f"  Unknown: {final_summary['unknown_nodes']}")
            if final_summary["syncing_nodes"] > 0:
                logger.info(f"  Syncing: {final_summary['syncing_nodes']}")

            # Log details for non-ready nodes
            for node_name, details in final_summary["node_details"].items():
                if details["status"] != "ready":
                    status_msg = f"  {node_name}: {details['status']}"
                    if details.get("error_message"):
                        status_msg += f" - {details['error_message']}"
                    logger.info(status_msg)

        logger.info("Continuing with topology integration...")
