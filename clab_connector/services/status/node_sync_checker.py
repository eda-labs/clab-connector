# clab_connector/services/status/node_sync_checker.py

import logging
import sys
import time
from typing import List, Dict, Optional, Any
from enum import Enum
from dataclasses import dataclass
from clab_connector.clients.eda.client import EDAClient

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
    """Status information for a single node"""
    name: str
    status: NodeSyncStatus
    last_sync: Optional[str] = None
    error_message: Optional[str] = None
    connectivity_status: Optional[str] = None
    config_status: Optional[str] = None
    certificates_status: Optional[str] = None
    
    def is_ready(self) -> bool:
        return self.status == NodeSyncStatus.READY
    
    def has_error(self) -> bool:
        return self.status == NodeSyncStatus.ERROR
    
    def add_debug_info(self, api_source: str, raw_data: Dict[str, Any]) -> None:
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
        
    def _print_node_status_table(self, statuses: List[NodeStatus], current_check: str = None, elapsed: float = 0, timeout: int = 90):
        """Print node status table with current status"""
        # Use simple approach: clear screen for clean display
        if hasattr(self, '_table_printed'):
            # Clear screen completely for clean display
            print('\033c', end='')
        
        # Header with progress
        progress = f"Elapsed: {elapsed:.1f}s / {timeout}s"
        if current_check:
            progress += f" | Checking: {current_check}"
            
        print(f"Node Synchronization Status - {progress}")
        print("┌──────────────────────────────┬──────────────┬───────────────────────────────┐")
        print("│ Node                         │ Status       │ Details                       │")
        print("├──────────────────────────────┼──────────────┼───────────────────────────────┤")
        
        for status in statuses:
            # Determine color based on status
            status_color = self._get_node_status_color(status.status)
            
            # Truncate name and message to fit
            name = status.name[:28] if len(status.name) > 28 else status.name
            
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
                print(f"│ {name:<28} │ \033[93mCHECKING...\033[0m   │ {'Updating status...':<29} │")
            else:
                print(f"│ {name:<28} │ {status_color}{status.status.value.upper():<12}\033[0m │ {details:<29} │")
        
        print("└──────────────────────────────┴──────────────┴───────────────────────────────┘")
        
        # Summary
        ready_nodes = len([s for s in statuses if s.is_ready()])
        error_nodes = len([s for s in statuses if s.has_error()])
        syncing_nodes = len([s for s in statuses if s.status == NodeSyncStatus.SYNCING])
        pending_nodes = len([s for s in statuses if s.status == NodeSyncStatus.PENDING])
        
        print(f"Summary: {ready_nodes}/{len(statuses)} ready, {syncing_nodes} syncing, {pending_nodes} pending, {error_nodes} errors")
        
        sys.stdout.flush()
        self._table_printed = True
        
    def _get_node_status_color(self, status: NodeSyncStatus) -> str:
        """Get ANSI color code for node status"""
        colors = {
            NodeSyncStatus.READY: '\033[92m',     # Green
            NodeSyncStatus.SYNCING: '\033[93m',   # Yellow
            NodeSyncStatus.PENDING: '\033[94m',   # Blue
            NodeSyncStatus.ERROR: '\033[91m',     # Red
            NodeSyncStatus.TIMEOUT: '\033[91m',   # Red
            NodeSyncStatus.UNKNOWN: '\033[90m'    # Gray
        }
        return colors.get(status, '\033[0m')
        
    def _get_toponode_status(self, node_name: str) -> tuple[Dict[str, Any], str]:
        """
        Get the status of a toponode from EDA API
        
        Returns:
            tuple: (data, api_source) where data is the resource data and 
                  api_source indicates which API was used to get the data
        """
        # Try EDA API endpoints for TopoNode resources
        eda_endpoints = [
            f"apps/core.eda.nokia.com/v1/namespaces/{self.namespace}/toponodes/{node_name}",
            # Fallback endpoints in case the API structure varies
            f"core/topology/v1/namespaces/{self.namespace}/toponodes/{node_name}",
            f"api/core/v1/namespaces/{self.namespace}/toponodes/{node_name}",
        ]
        
        for endpoint in eda_endpoints:
            try:
                response = self.eda_client.get(endpoint)
                if response.status == 200:
                    import json
                    data = json.loads(response.data.decode('utf-8'))
                    logger.debug(f"Successfully got TopoNode {node_name} via EDA API endpoint: {endpoint}")
                    
                    # Enhanced debugging for unknown node issues
                    if logger.getEffectiveLevel() <= logging.DEBUG:
                        logger.debug(f"Raw API response for {node_name}: {json.dumps(data, indent=2)}")
                    
                    return data, f"EDA API ({endpoint})"
                else:
                    logger.debug(f"API call to {endpoint} returned status {response.status}")
            except Exception as e:
                logger.debug(f"Error trying EDA API endpoint {endpoint}: {e}")
        
        logger.warning(f"Failed to get TopoNode {node_name} from any EDA API endpoint")
        logger.debug(f"All EDA API endpoints failed for {node_name}:")
        for endpoint in [
            f"apps/core.eda.nokia.com/v1/namespaces/{self.namespace}/toponodes/{node_name}",
            f"core/topology/v1/namespaces/{self.namespace}/toponodes/{node_name}",
            f"api/core/v1/namespaces/{self.namespace}/toponodes/{node_name}",
        ]:
            logger.debug(f"  - {endpoint}")
        return {}, "EDA API (failed)"
    
    def _determine_node_status(self, node_name: str, data: Dict) -> NodeStatus:
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
                error_message="No data available"
            )
        
        # Debug: log the structure of the data we received
        logger.debug(f"Processing status for {node_name}: data keys = {list(data.keys())}")
        
        # Check TopoNode status based on the schema you provided
        node_status_data = data.get("status", {})
        if node_status_data:
            # Log the status data for debugging
            logger.debug(f"Status data for {node_name}: {node_status_data}")
            
            # Map EDA TopoNode status fields to our status (using the correct field names)
            node_state = node_status_data.get("node-state")    # e.g., "Synced"
            npp_state = node_status_data.get("npp-state")      # e.g., "Connected"
            npp_details = node_status_data.get("npp-details")
            node_details = node_status_data.get("node-details")
            
            logger.debug(f"Node {node_name} states: node-state={node_state}, npp-state={npp_state}")
            
            # Determine status based on the actual node states from the schema
            # Schema states: TryingToConnect, WaitingForInitialCfg, Committing, RetryingCommit, Synced, Standby, NoIpAddress
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
                # Any other node state we don't recognize
                status = NodeSyncStatus.PENDING
                logger.debug(f"Node {node_name} has unrecognized node-state: {node_state}, treating as PENDING")
            elif npp_state == "Connected":
                # Have NPP state but no node state
                status = NodeSyncStatus.SYNCING
            elif npp_state:
                status = NodeSyncStatus.PENDING
            else:
                status = NodeSyncStatus.UNKNOWN
                logger.debug(f"Node {node_name} has no node-state or npp-state, keeping as UNKNOWN")
            
            # Set status details
            connectivity_status = npp_state
            config_status = node_state
            
            # Check for error conditions in details
            if "error" in str(node_details).lower() or "error" in str(npp_details).lower():
                status = NodeSyncStatus.ERROR
                error_message = f"Node details: {node_details}, NPP details: {npp_details}"
        else:
            logger.debug(f"No status data found for node {node_name}")
        
        # Check spec for additional status info if we still don't have status
        if status == NodeSyncStatus.UNKNOWN and data.get("spec"):
            spec_data = data.get("spec", {})
            if spec_data.get("state") == "active":
                status = NodeSyncStatus.SYNCING
                logger.debug(f"Node {node_name} has active spec state, treating as SYNCING")
        
        return NodeStatus(
            name=node_name,
            status=status,
            last_sync=last_sync,
            error_message=error_message,
            connectivity_status=connectivity_status,
            config_status=config_status,
            certificates_status=certificates_status
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
    
    def check_all_nodes_status(self, node_names: List[str]) -> List[NodeStatus]:
        """Check the synchronization status of all nodes in the topology"""
        logger.info(f"Checking synchronization status for {len(node_names)} nodes")
        
        statuses = []
        for node_name in node_names:
            try:
                node_status = self.check_node_status(node_name)
                statuses.append(node_status)
            except Exception as e:
                logger.error(f"Failed to check status for node {node_name}: {e}")
                statuses.append(NodeStatus(
                    name=node_name,
                    status=NodeSyncStatus.ERROR,
                    error_message=str(e)
                ))
        
        return statuses
    
    def wait_for_nodes_ready(
        self, 
        node_names: List[str], 
        timeout: int = 90,
        check_interval: int = 10,
        verbose: bool = False
    ) -> bool:
        """
        Wait for all nodes to reach ready status with dynamic table updates.
        
        Args:
            node_names: List of node names to check
            timeout: Maximum time to wait in seconds
            check_interval: Time between checks in seconds
            verbose: If True, display verbose status information
            
        Returns:
            True if all nodes are ready, False if timeout or errors
        """
        logger.info(f"Waiting for {len(node_names)} nodes to be ready (timeout: {timeout}s)\n")
        
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
                self._print_node_status_table(statuses, current_check=node_name, elapsed=elapsed_time, timeout=timeout)
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
                                error_message=str(e)
                            )
                            break
                
                # Show updated results
                self._print_node_status_table(statuses, elapsed=elapsed_time, timeout=timeout)
                time.sleep(0.2)  # Brief pause before next node
            
            # Check if all nodes are ready
            ready_nodes = [s for s in statuses if s.is_ready()]
            error_nodes = [s for s in statuses if s.has_error()]
            
            if len(ready_nodes) == len(node_names):
                print("\n✅ All nodes are ready!")
                return True
            
            # Check if we have unrecoverable errors
            if error_nodes:
                logger.warning(f"{len(error_nodes)} nodes have errors, continuing to wait...")
            
            remaining = timeout - elapsed_time
            if remaining <= 0:
                break
                
            # Wait for next check
            next_check = min(check_interval, remaining)
            print(f"\n⏳ Waiting {next_check:.1f}s for next check... (Press Ctrl+C to abort)")
            time.sleep(next_check)
            print()  # Add newline for next table
        
        print(f"\n❌ Timeout waiting for nodes to be ready after {timeout}s")
        return False
    
    def get_sync_summary(self, node_names: List[str]) -> Dict[str, Any]:
        """Get a summary of node synchronization status"""
        statuses = self.check_all_nodes_status(node_names)
        
        summary = {
            "total_nodes": len(node_names),
            "ready_nodes": len([s for s in statuses if s.is_ready()]),
            "error_nodes": len([s for s in statuses if s.has_error()]),
            "pending_nodes": len([s for s in statuses if s.status == NodeSyncStatus.PENDING]),
            "syncing_nodes": len([s for s in statuses if s.status == NodeSyncStatus.SYNCING]),
            "unknown_nodes": len([s for s in statuses if s.status == NodeSyncStatus.UNKNOWN]),
            "node_details": {s.name: {
                "status": s.status.value,
                "last_sync": s.last_sync,
                "error_message": s.error_message,
                "connectivity": s.connectivity_status,
                "config": s.config_status,
                "certificates": s.certificates_status
            } for s in statuses}
        }
        
        return summary
    
    def list_available_namespaces(self) -> List[str]:
        """List all available namespaces that start with 'clab-' via EDA API"""
        try:
            # Try EDA API endpoints for namespaces
            namespace_endpoints = [
                "apps/core.eda.nokia.com/v1/namespaces",
                "api/v1/namespaces",  # Fallback
            ]
            
            for endpoint in namespace_endpoints:
                try:
                    response = self.eda_client.get(endpoint)
                    
                    if response.status == 200:
                        import json
                        data = json.loads(response.data.decode('utf-8'))
                        namespaces = []
                        
                        # Extract namespace names from the response
                        if isinstance(data, dict) and 'items' in data:
                            for item in data['items']:
                                if isinstance(item, dict) and 'metadata' in item:
                                    name = item['metadata'].get('name', '')
                                    if name.startswith('clab-'):
                                        namespaces.append(name)
                        elif isinstance(data, list):
                            # Handle case where response is directly a list
                            for item in data:
                                if isinstance(item, str) and item.startswith('clab-'):
                                    namespaces.append(item)
                                elif isinstance(item, dict):
                                    name = item.get('name', '') or item.get('metadata', {}).get('name', '')
                                    if name.startswith('clab-'):
                                        namespaces.append(name)
                        
                        return namespaces
                except Exception as e:
                    logger.info(f"Error trying EDA API endpoint {endpoint}: {e}")
            
            logger.warning("Failed to list namespaces via any EDA API endpoint")
            return []
            
        except Exception as e:
            logger.error(f"Error listing namespaces via EDA API: {e}")
            return []
    
    def suggest_correct_namespace(self, expected_namespace: str) -> Optional[str]:
        """Suggest the correct namespace if the expected one doesn't exist"""
        available_namespaces = self.list_available_namespaces()
        
        if not available_namespaces:
            return None
            
        # Look for close matches
        expected_clean = expected_namespace.replace('clab-', '').lower()
        
        for ns in available_namespaces:
            ns_clean = ns.replace('clab-', '').lower()
            # Simple similarity check
            if expected_clean in ns_clean or ns_clean in expected_clean:
                return ns
                
        # Return the first available namespace as a fallback
        return available_namespaces[0] if available_namespaces else None
    
    def check_namespace_and_resources(self) -> Dict[str, Any]:
        """Check if namespace exists and what resources are in it via EDA API"""
        try:
            # Check what TopoNodes are available in the namespace via EDA API
            toponodes = self.list_toponodes_in_namespace()
            
            return {
                "namespace_exists": len(toponodes) > 0,  # Assume namespace exists if we find TopoNodes
                "toponodes_found": len(toponodes),
                "toponode_names": toponodes[:10],  # First 10 names
                "method": "EDA API only"
            }
            
        except Exception as e:
            logger.error(f"Error checking namespace and resources via EDA API: {e}")
            return {
                "namespace_exists": False,
                "toponodes_found": 0,
                "toponode_names": [],
                "error": str(e),
                "method": "EDA API only"
            }
        
    def display_detailed_status(self, node_names: List[str], verbose: bool = False) -> None:
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
                statuses.append(NodeStatus(
                    name=node_name,
                    status=NodeSyncStatus.ERROR,
                    error_message=str(e)
                ))
            
            # Show updated results
            self._print_node_status_table(statuses)
            time.sleep(0.2)
        
        print()  # Final newline
        
        # Print verbose information if requested
        if verbose:
            print("\n" + "="*80)
            print("DETAILED STATUS INFORMATION")
            print("="*80)
            
            for status in statuses:
                print(f"\n🔍 {status.name}:")
                print(f"   Status: {status.status.value}")
                if status.error_message:
                    print(f"   Error: {status.error_message}")
                
                # Show raw data if available
                if hasattr(status, '_raw_data') and status._raw_data:
                    node_data = status._raw_data
                    node_status = node_data.get('status', {})
                    
                    if node_status:
                        print(f"   NPP State: {node_status.get('npp-state', 'N/A')}")
                        print(f"   Node State: {node_status.get('node-state', 'N/A')}")
                        print(f"   Version: {node_status.get('version', 'N/A')}")
                        print(f"   Platform: {node_status.get('platform', 'N/A')}")
                
                if hasattr(status, '_api_source'):
                    print(f"   API Source: {status._api_source}")
                    
            print("\n" + "="*80)
            print("Note: Using EDA API only for status checks")
            print("="*80)
    
    def list_toponodes_in_namespace(self) -> List[str]:
        """List all TopoNodes in the current namespace via EDA API"""
        try:
            # Try EDA API endpoints for listing TopoNodes
            endpoints = [
                f"apps/core.eda.nokia.com/v1/namespaces/{self.namespace}/toponodes",
                f"core/topology/v1/namespaces/{self.namespace}/toponodes",
                f"api/core/v1/namespaces/{self.namespace}/toponodes",
            ]
            
            for endpoint in endpoints:
                try:
                    response = self.eda_client.get(endpoint)
                    
                    if response.status == 200:
                        import json
                        data = json.loads(response.data.decode('utf-8'))
                        toponodes = []
                        
                        # Extract TopoNode names from the response
                        if isinstance(data, dict) and 'items' in data:
                            for item in data['items']:
                                if isinstance(item, dict) and 'metadata' in item:
                                    name = item['metadata'].get('name', '')
                                    if name:
                                        toponodes.append(name)
                        elif isinstance(data, list):
                            # Handle case where response is directly a list
                            for item in data:
                                if isinstance(item, dict):
                                    name = item.get('metadata', {}).get('name', '') or item.get('name', '')
                                    if name:
                                        toponodes.append(name)
                        
                        logger.info(f"Found {len(toponodes)} TopoNodes in namespace {self.namespace} via EDA API endpoint: {endpoint}")
                        return toponodes
                except Exception as e:
                    logger.info(f"Error trying EDA API endpoint {endpoint}: {e}")
            
            logger.warning(f"Failed to list TopoNodes in namespace {self.namespace} via any EDA API endpoint")
            return []
            
        except Exception as e:
            logger.error(f"Error listing TopoNodes in namespace {self.namespace}: {e}")
            return []
