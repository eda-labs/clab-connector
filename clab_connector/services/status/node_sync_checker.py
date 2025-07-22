# clab_connector/services/status/node_sync_checker.py

import json
import logging
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from clab_connector.utils.api_utils import extract_k8s_names, try_api_endpoints

logger = logging.getLogger(__name__)


class NodeSyncStatus(Enum):
    """Node synchronization status"""

    UNKNOWN = "unknown"
    PENDING = "pending"
    SYNCING = "syncing"
    READY = "ready"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class NodeStatus:
    """Status information for a single node."""

    name: str
    status: NodeSyncStatus
    last_sync: str | None = None
    error_message: str | None = None
    connectivity_status: str | None = None
    config_status: str | None = None
    certificates_status: str | None = None

    def is_ready(self) -> bool:
        return self.status == NodeSyncStatus.READY

    def has_error(self) -> bool:
        return self.status == NodeSyncStatus.ERROR

    def add_debug_info(self, api_source: str, raw_data: dict[str, Any]) -> None:
        """Add debugging information to the status"""
        self._api_source = api_source
        self._raw_data = raw_data


class NodeSyncChecker:
    """Check synchronization status of nodes"""

    def __init__(self, eda_client, namespace: str):
        """
        Initialize the NodeSyncChecker.

        Parameters
        ----------
        eda_client : EDAClient
            EDA client for API calls
        namespace : str
            The namespace to check nodes in
        """
        self.eda_client = eda_client
        self.namespace = namespace

    def _print_node_status_table(
        self,
        statuses: list[NodeStatus],
        current_check: str | None = None,
        elapsed: float = 0,
        timeout: int = 90,
    ):
        """Print node status table with current status"""
        # Use simple approach: clear screen for clean display
        if hasattr(self, "_table_printed"):
            # Clear screen completely for clean display
            print("\033c", end="")

        # Header with progress
        progress = f"Elapsed: {elapsed:.1f}s / {timeout}s"
        if current_check:
            progress += f" | Checking: {current_check}"

        print(f"Node Synchronization Status - {progress}")
        print(
            "┌──────────────────────────────┬──────────────┬───────────────────────────────┐"
        )
        print(
            "│ Node                         │ Status       │ Details                       │"
        )
        print(
            "├──────────────────────────────┼──────────────┼───────────────────────────────┤"
        )

        for status in statuses:
            # Determine color based on status
            status_color = self._get_node_status_color(status.status)

            # Truncate name and message to fit
            max_col_width = 28
            name = (
                status.name[:max_col_width]
                if len(status.name) > max_col_width
                else status.name
            )

            # Build details message
            if status.error_message:
                details = status.error_message[:29]
            elif status.status == NodeSyncStatus.READY:
                details = "Node synced successfully"
            elif status.status == NodeSyncStatus.SYNCING:
                details = "Configuration sync in progress"
            elif status.status == NodeSyncStatus.PENDING:
                details = "Waiting for sync to start"
            else:
                details = "Status unknown"

            details = details[:29]  # Truncate to fit

            if current_check == name:
                print(
                    f"│ {name:<28} │ \033[93mCHECKING...\033[0m   │ {'Updating status...':<29} │"
                )
            else:
                print(
                    f"│ {name:<28} │ {status_color}{status.status.value.upper():<12}\033[0m │ {details:<29} │"
                )

        print(
            "└──────────────────────────────┴──────────────┴───────────────────────────────┘"
        )

        # Summary
        ready_nodes = len([s for s in statuses if s.is_ready()])
        error_nodes = len([s for s in statuses if s.has_error()])
        syncing_nodes = len([s for s in statuses if s.status == NodeSyncStatus.SYNCING])
        pending_nodes = len([s for s in statuses if s.status == NodeSyncStatus.PENDING])

        print(
            f"Summary: {ready_nodes}/{len(statuses)} ready, {syncing_nodes} syncing, {pending_nodes} pending, {error_nodes} errors"
        )

        sys.stdout.flush()
        self._table_printed = True

    def _get_node_status_color(self, status: NodeSyncStatus) -> str:
        """Get ANSI color code for node status"""
        colors = {
            NodeSyncStatus.READY: "\033[92m",  # Green
            NodeSyncStatus.SYNCING: "\033[93m",  # Yellow
            NodeSyncStatus.PENDING: "\033[94m",  # Blue
            NodeSyncStatus.ERROR: "\033[91m",  # Red
            NodeSyncStatus.TIMEOUT: "\033[91m",  # Red
            NodeSyncStatus.UNKNOWN: "\033[90m",  # Gray
        }
        return colors.get(status, "\033[0m")

    def _get_toponode_status(self, node_name: str) -> tuple[dict[str, Any], str]:
        """
        Get the status of a toponode from EDA API

        Returns:
            tuple: (data, api_source) where data is the resource data and
                  api_source indicates which API was used to get the data
        """
        # Try EDA API endpoints for TopoNode resources
        eda_endpoints = [
            f"apps/core.eda.nokia.com/v1/namespaces/{self.namespace}/toponodes/{node_name}",
            f"core/topology/v1/namespaces/{self.namespace}/toponodes/{node_name}",
            f"api/core/v1/namespaces/{self.namespace}/toponodes/{node_name}",
        ]

        data, endpoint = try_api_endpoints(
            self.eda_client, eda_endpoints, f"TopoNode {node_name}"
        )

        if data:
            # Enhanced debugging for unknown node issues
            if logger.getEffectiveLevel() <= logging.DEBUG:
                logger.debug(
                    f"Raw API response for {node_name}: {json.dumps(data, indent=2)}"
                )
            return data, f"EDA API ({endpoint})"

        return {}, "EDA API (failed)"

    def _evaluate_states(
        self,
        node_name: str,
        node_state: str | None,
        npp_state: str | None,
        node_details: str | None,
        npp_details: str | None,
    ) -> tuple[NodeSyncStatus, str | None]:
        """Map raw node states to a NodeSyncStatus and optional error message."""
        status = NodeSyncStatus.UNKNOWN
        error_message = None

        if node_state == "Synced":
            status = NodeSyncStatus.READY
        elif node_state in ["Committing", "RetryingCommit"]:
            status = NodeSyncStatus.SYNCING
        elif node_state in ["TryingToConnect", "WaitingForInitialCfg"]:
            status = NodeSyncStatus.PENDING
        elif node_state == "Standby":
            status = NodeSyncStatus.PENDING
            error_message = "Node in standby mode"
        elif node_state == "NoIpAddress":
            status = NodeSyncStatus.ERROR
            error_message = "No IP address available"
        elif node_state:
            status = NodeSyncStatus.PENDING
            logger.debug(
                f"Node {node_name} has unrecognized node-state: {node_state}, treating as PENDING"
            )
        elif npp_state == "Connected":
            status = NodeSyncStatus.SYNCING
        elif npp_state:
            status = NodeSyncStatus.PENDING
        else:
            logger.debug(
                f"Node {node_name} has no node-state or npp-state, keeping as UNKNOWN"
            )

        if "error" in str(node_details).lower() or "error" in str(npp_details).lower():
            status = NodeSyncStatus.ERROR
            error_message = f"Node details: {node_details}, NPP details: {npp_details}"

        return status, error_message

    def _determine_node_status(self, node_name: str, data: dict) -> NodeStatus:
        """Determine the overall status of a node based on TopoNode data"""

        # Start with unknown status
        status = NodeSyncStatus.UNKNOWN
        error_message = None
        last_sync = None
        connectivity_status = None
        config_status = None
        certificates_status = None

        # Check if we have data
        if not data:
            logger.debug(f"No data available for node {node_name}")
            return NodeStatus(
                name=node_name,
                status=NodeSyncStatus.UNKNOWN,
                error_message="No data available",
            )

        # Debug: log the structure of the data we received
        logger.debug(
            f"Processing status for {node_name}: data keys = {list(data.keys())}"
        )

        # Check TopoNode status based on the schema you provided
        node_status_data = data.get("status", {})
        if node_status_data:
            logger.debug(f"Status data for {node_name}: {node_status_data}")

            node_state = node_status_data.get("node-state")
            npp_state = node_status_data.get("npp-state")
            npp_details = node_status_data.get("npp-details")
            node_details = node_status_data.get("node-details")

            logger.debug(
                f"Node {node_name} states: node-state={node_state}, npp-state={npp_state}"
            )

            status, error_message = self._evaluate_states(
                node_name, node_state, npp_state, node_details, npp_details
            )

            connectivity_status = npp_state
            config_status = node_state
        else:
            logger.debug(f"No status data found for node {node_name}")

        # Check spec for additional status info if we still don't have status
        if status == NodeSyncStatus.UNKNOWN and data.get("spec"):
            spec_data = data.get("spec", {})
            if spec_data.get("state") == "active":
                status = NodeSyncStatus.SYNCING
                logger.debug(
                    f"Node {node_name} has active spec state, treating as SYNCING"
                )

        return NodeStatus(
            name=node_name,
            status=status,
            last_sync=last_sync,
            error_message=error_message,
            connectivity_status=connectivity_status,
            config_status=config_status,
            certificates_status=certificates_status,
        )

    def check_node_status(self, node_name: str) -> NodeStatus:
        """Check the synchronization status of a single node"""

        # Get data from EDA API only
        node_data, api_source = self._get_toponode_status(node_name)

        # Determine node status based on the data
        status = self._determine_node_status(node_name, node_data)

        # Add debug information to the status
        status.add_debug_info(api_source, node_data)

        return status

    def check_all_nodes_status(self, node_names: list[str]) -> list[NodeStatus]:
        """Check the synchronization status of all nodes in the topology"""
        logger.info(f"Checking synchronization status for {len(node_names)} nodes")

        statuses = []
        for node_name in node_names:
            try:
                node_status = self.check_node_status(node_name)
                statuses.append(node_status)
            except Exception as e:
                logger.error(f"Failed to check status for node {node_name}: {e}")
                statuses.append(
                    NodeStatus(
                        name=node_name,
                        status=NodeSyncStatus.ERROR,
                        error_message=str(e),
                    )
                )

        return statuses

    def wait_for_nodes_ready(
        self,
        node_names: list[str],
        timeout: int = 90,
        check_interval: int = 10,
        verbose: bool = False,
        use_log_view: bool = True,
    ) -> bool:
        """
        Wait for all nodes to reach ready status.

        Args:
            node_names: List of node names to check
            timeout: Maximum time to wait in seconds
            check_interval: Time between checks in seconds
            verbose: If True, display verbose status information
            use_log_view: If True, use log messages instead of table (for integration)

        Returns:
            True if all nodes are ready, False if timeout or errors
        """
        if use_log_view:
            return self._wait_for_nodes_ready_log_view(
                node_names, timeout, check_interval
            )
        else:
            return self._wait_for_nodes_ready_table_view(
                node_names, timeout, check_interval, verbose
            )

    def _wait_for_nodes_ready_log_view(
        self, node_names: list[str], timeout: int = 90, check_interval: int = 10
    ) -> bool:
        """
        Wait for nodes to be ready using log messages (for integration).
        """
        logger.info(f"Waiting for {len(node_names)} nodes to synchronize...")

        start_time = time.time()
        previous_statuses = {}
        nodes_reported_ready = set()

        while time.time() - start_time < timeout:
            elapsed_time = time.time() - start_time

            # Check all nodes
            statuses = self.check_all_nodes_status(node_names)

            # Report changes in status
            for status in statuses:
                prev_status = previous_statuses.get(status.name)

                # Report when a node becomes ready for the first time
                if status.is_ready() and status.name not in nodes_reported_ready:
                    logger.info(f"  ✓ Node {status.name} is ready")
                    nodes_reported_ready.add(status.name)
                # Report when status changes (except to ready which is already reported)
                elif (
                    prev_status
                    and prev_status.status != status.status
                    and not status.is_ready()
                ):
                    if status.status == NodeSyncStatus.SYNCING:
                        logger.info(f"  • Node {status.name} is syncing...")
                    elif status.status == NodeSyncStatus.ERROR:
                        logger.error(
                            f"  ✗ Node {status.name} error: {status.error_message}"
                        )
                    elif status.status == NodeSyncStatus.PENDING:
                        logger.info(f"  • Node {status.name} is pending...")

                previous_statuses[status.name] = status

            # Check if all nodes are ready
            ready_nodes = [s for s in statuses if s.is_ready()]

            if len(ready_nodes) == len(node_names):
                return True

            # Check timeout
            remaining = timeout - elapsed_time
            if remaining <= 0:
                break

            # Wait for next check
            time.sleep(min(check_interval, remaining))

        # Timeout reached
        return False

    def _wait_for_nodes_ready_table_view(
        self,
        node_names: list[str],
        timeout: int = 90,
        check_interval: int = 10,
        _verbose: bool = False,
    ) -> bool:
        """
        Wait for nodes to be ready using table view (for check-sync command).
        """
        logger.info(
            f"Waiting for {len(node_names)} nodes to be ready (timeout: {timeout}s)\n"
        )

        start_time = time.time()
        iteration = 0

        # Initial status check and display
        statuses = self.check_all_nodes_status(node_names)
        self._print_node_status_table(statuses, elapsed=0, timeout=timeout)

        while time.time() - start_time < timeout:
            iteration += 1
            elapsed_time = time.time() - start_time

            # Check each node individually with dynamic updates
            for node_name in node_names:
                # Show checking status for current node
                self._print_node_status_table(
                    statuses,
                    current_check=node_name,
                    elapsed=elapsed_time,
                    timeout=timeout,
                )
                time.sleep(0.1)  # Brief pause to show checking status

                # Update status for this node
                try:
                    new_status = self.check_node_status(node_name)
                    # Find and update the status in the list
                    for i, status in enumerate(statuses):
                        if status.name == node_name:
                            statuses[i] = new_status
                            break
                    else:
                        # Node not in list, add it
                        statuses.append(new_status)
                except Exception as e:
                    logger.error(f"Failed to check status for node {node_name}: {e}")
                    # Update with error status
                    for i, status in enumerate(statuses):
                        if status.name == node_name:
                            statuses[i] = NodeStatus(
                                name=node_name,
                                status=NodeSyncStatus.ERROR,
                                error_message=str(e),
                            )
                            break

                # Show updated results
                self._print_node_status_table(
                    statuses, elapsed=elapsed_time, timeout=timeout
                )
                time.sleep(0.2)  # Brief pause before next node

            # Check if all nodes are ready
            ready_nodes = [s for s in statuses if s.is_ready()]
            error_nodes = [s for s in statuses if s.has_error()]

            if len(ready_nodes) == len(node_names):
                print("\n✅ All nodes are ready!")
                return True

            # Check if we have unrecoverable errors
            if error_nodes:
                logger.warning(
                    f"{len(error_nodes)} nodes have errors, continuing to wait..."
                )

            remaining = timeout - elapsed_time
            if remaining <= 0:
                break

            # Wait for next check
            next_check = min(check_interval, remaining)
            print(
                f"\n⏳ Waiting {next_check:.1f}s for next check... (Press Ctrl+C to abort)"
            )
            time.sleep(next_check)
            print()  # Add newline for next table

        print(f"\n❌ Timeout waiting for nodes to be ready after {timeout}s")
        return False

    def get_sync_summary(self, node_names: list[str]) -> dict[str, Any]:
        """Get a summary of node synchronization status"""
        statuses = self.check_all_nodes_status(node_names)

        summary = {
            "total_nodes": len(node_names),
            "ready_nodes": len([s for s in statuses if s.is_ready()]),
            "error_nodes": len([s for s in statuses if s.has_error()]),
            "pending_nodes": len(
                [s for s in statuses if s.status == NodeSyncStatus.PENDING]
            ),
            "syncing_nodes": len(
                [s for s in statuses if s.status == NodeSyncStatus.SYNCING]
            ),
            "unknown_nodes": len(
                [s for s in statuses if s.status == NodeSyncStatus.UNKNOWN]
            ),
            "node_details": {
                s.name: {
                    "status": s.status.value,
                    "last_sync": s.last_sync,
                    "error_message": s.error_message,
                    "connectivity": s.connectivity_status,
                    "config": s.config_status,
                    "certificates": s.certificates_status,
                }
                for s in statuses
            },
        }

        return summary

    def list_available_namespaces(self) -> list[str]:
        """List all available namespaces that start with 'clab-' via EDA API"""
        try:
            # Try EDA API endpoints for namespaces
            namespace_endpoints = [
                "apps/core.eda.nokia.com/v1/namespaces",
                "api/v1/namespaces",  # Fallback
            ]

            data, endpoint = try_api_endpoints(
                self.eda_client, namespace_endpoints, "namespaces"
            )

            if data:
                return extract_k8s_names(data, lambda name: name.startswith("clab-"))

            return []

        except Exception as e:
            logger.error(f"Error listing namespaces via EDA API: {e}")
            return []

    def suggest_correct_namespace(self, expected_namespace: str) -> str | None:
        """Suggest the correct namespace if the expected one doesn't exist"""
        available_namespaces = self.list_available_namespaces()

        if not available_namespaces:
            return None

        # Look for close matches
        expected_clean = expected_namespace.replace("clab-", "").lower()

        for ns in available_namespaces:
            ns_clean = ns.replace("clab-", "").lower()
            # Simple similarity check
            if expected_clean in ns_clean or ns_clean in expected_clean:
                return ns

        # Return the first available namespace as a fallback
        return available_namespaces[0] if available_namespaces else None

    def check_namespace_and_resources(self) -> dict[str, Any]:
        """Check if namespace exists and what resources are in it via EDA API"""
        try:
            # Check what TopoNodes are available in the namespace via EDA API
            toponodes = self.list_toponodes_in_namespace()

            return {
                "namespace_exists": len(toponodes)
                > 0,  # Assume namespace exists if we find TopoNodes
                "toponodes_found": len(toponodes),
                "toponode_names": toponodes[:10],  # First 10 names
                "method": "EDA API only",
            }

        except Exception as e:
            logger.error(f"Error checking namespace and resources via EDA API: {e}")
            return {
                "namespace_exists": False,
                "toponodes_found": 0,
                "toponode_names": [],
                "error": str(e),
                "method": "EDA API only",
            }

    def display_detailed_status(
        self, node_names: list[str], verbose: bool = False
    ) -> None:
        """
        Display detailed status information for all nodes using dynamic table.

        Parameters
        ----------
        node_names : List[str]
            List of node names to check.
        verbose : bool
            If True, display verbose debug information.
        """
        print("Checking node synchronization status...\n")

        # Get the status for all nodes with dynamic updates
        statuses = []

        # Show initial table
        self._print_node_status_table([], elapsed=0, timeout=0)

        for node_name in node_names:
            # Show checking status for current node
            self._print_node_status_table(statuses, current_check=node_name)
            time.sleep(0.1)

            try:
                status = self.check_node_status(node_name)
                statuses.append(status)
            except Exception as e:
                logger.error(f"Failed to check status for node {node_name}: {e}")
                statuses.append(
                    NodeStatus(
                        name=node_name,
                        status=NodeSyncStatus.ERROR,
                        error_message=str(e),
                    )
                )

            # Show updated results
            self._print_node_status_table(statuses)
            time.sleep(0.2)

        print()  # Final newline

        # Print verbose information if requested
        if verbose:
            print("\n" + "=" * 80)
            print("DETAILED STATUS INFORMATION")
            print("=" * 80)

            for status in statuses:
                print(f"\n🔍 {status.name}:")
                print(f"   Status: {status.status.value}")
                if status.error_message:
                    print(f"   Error: {status.error_message}")

                # Show raw data if available
                if hasattr(status, "_raw_data") and status._raw_data:
                    node_data = status._raw_data
                    node_status = node_data.get("status", {})

                    if node_status:
                        print(f"   NPP State: {node_status.get('npp-state', 'N/A')}")
                        print(f"   Node State: {node_status.get('node-state', 'N/A')}")
                        print(f"   Version: {node_status.get('version', 'N/A')}")
                        print(f"   Platform: {node_status.get('platform', 'N/A')}")

                if hasattr(status, "_api_source"):
                    print(f"   API Source: {status._api_source}")

            print("\n" + "=" * 80)
            print("Note: Using EDA API only for status checks")
            print("=" * 80)

    def list_toponodes_in_namespace(self) -> list[str]:
        """List all TopoNodes in the current namespace via EDA API"""
        try:
            # Try EDA API endpoints for listing TopoNodes
            endpoints = [
                f"apps/core.eda.nokia.com/v1/namespaces/{self.namespace}/toponodes",
                f"core/topology/v1/namespaces/{self.namespace}/toponodes",
                f"api/core/v1/namespaces/{self.namespace}/toponodes",
            ]

            data, endpoint = try_api_endpoints(
                self.eda_client, endpoints, f"TopoNodes in {self.namespace}"
            )

            if data:
                toponodes = extract_k8s_names(data)
                logger.info(
                    f"Found {len(toponodes)} TopoNodes in namespace {self.namespace} via EDA API endpoint: {endpoint}"
                )
                return toponodes

            return []

        except Exception as e:
            logger.error(f"Error listing TopoNodes in namespace {self.namespace}: {e}")
            return []
