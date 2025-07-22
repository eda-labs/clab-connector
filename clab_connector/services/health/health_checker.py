# clab_connector/services/health/health_checker.py

import logging
import sys
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

from clab_connector.clients.eda.client import EDAClient
from clab_connector.utils.kubernetes_utils import load_k8s_config

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status enumeration"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status for a component"""
    name: str
    status: HealthStatus
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class HealthChecker:
    """
    Health checking service for EDA connectivity and services.
    """
    
    def __init__(self, eda_client: EDAClient, include_kubernetes: bool = True):
        self.eda_client = eda_client
        self.include_kubernetes = include_kubernetes
        
        # Base checks that are always included
        base_checks = {
            'connectivity': 'EDA Connectivity',
            'authentication': 'EDA Authentication', 
            'version': 'EDA Version'
        }
        
        # Always add Kubernetes checks if requested
        if include_kubernetes:
            base_checks['kubernetes'] = 'Kubernetes Connectivity'
            base_checks['kubernetes_cluster'] = 'Kubernetes Cluster'
        
        self.check_names = base_checks
    
    def _print_health_table(self, results: Dict[str, ComponentHealth], current_check: str = None):
        """Print health check table with current status"""
        # Use simple approach: clear screen if we've already printed a table
        if hasattr(self, '_table_printed'):
            # Clear screen for clean display
            print('\033c', end='')  # Reset terminal
            print("Running comprehensive health check...\n")
        
        print("┌─────────────────────────┬──────────────┬────────────────────────────┐")
        print("│ Component               │ Status       │ Message                    │")
        print("├─────────────────────────┼──────────────┼────────────────────────────┤")
        
        for check_key, display_name in self.check_names.items():
            if check_key in results:
                result = results[check_key]
                status_color = self._get_status_color(result.status)
                message = (result.message or "")[:26]  # Truncate message to fit
                print(f"│ {display_name:<23} │ {status_color}{result.status.value.upper():<12}\033[0m │ {message:<26} │")
            elif check_key == current_check:
                print(f"│ {display_name:<23} │ \033[93mCHECKING...\033[0m   │ {'Running check...':<26} │")
            else:
                print(f"│ {display_name:<23} │ \033[90mPENDING\033[0m      │ {'Waiting...':<26} │")
        
        print("└─────────────────────────┴──────────────┴────────────────────────────┘")
        sys.stdout.flush()
        self._table_printed = True
    
    def _get_status_color(self, status: HealthStatus) -> str:
        """Get ANSI color code for status"""
        colors = {
            HealthStatus.HEALTHY: '\033[92m',    # Green
            HealthStatus.DEGRADED: '\033[93m',   # Yellow  
            HealthStatus.UNHEALTHY: '\033[91m',  # Red
            HealthStatus.UNKNOWN: '\033[90m'     # Gray
        }
        return colors.get(status, '\033[0m')
    
    def check_eda_connectivity(self) -> ComponentHealth:
        """Check basic EDA connectivity"""
        try:
            if self.eda_client.is_up():
                return ComponentHealth(
                    name="EDA Connectivity",
                    status=HealthStatus.HEALTHY,
                    message="EDA is reachable"
                )
            else:
                return ComponentHealth(
                    name="EDA Connectivity", 
                    status=HealthStatus.UNHEALTHY,
                    message="EDA is not reachable"
                )
        except Exception as e:
            return ComponentHealth(
                name="EDA Connectivity",
                status=HealthStatus.UNHEALTHY,
                message=f"Connection failed: {str(e)}"
            )
    
    def check_eda_authentication(self) -> ComponentHealth:
        """Check EDA authentication"""
        try:
            if self.eda_client.is_authenticated():
                return ComponentHealth(
                    name="EDA Authentication",
                    status=HealthStatus.HEALTHY,
                    message="Authentication successful"
                )
            else:
                return ComponentHealth(
                    name="EDA Authentication",
                    status=HealthStatus.UNHEALTHY,
                    message="Authentication failed"
                )
        except Exception as e:
            return ComponentHealth(
                name="EDA Authentication",
                status=HealthStatus.UNHEALTHY,
                message=f"Authentication error: {str(e)}"
            )
    
    def check_eda_version(self) -> ComponentHealth:
        """Check EDA version compatibility"""
        try:
            version = self.eda_client.get_version()
            
            # Check for supported versions - handle version strings that start with 'v'
            supported_major_versions = ["24", "25", "26"]
            
            # Remove 'v' prefix if present and split
            clean_version = version.lstrip('v')
            version_parts = clean_version.split(".")
            major_version = version_parts[0] if version_parts else "0"
            
            if major_version in supported_major_versions:
                return ComponentHealth(
                    name="EDA Version",
                    status=HealthStatus.HEALTHY,
                    message=f"Version {version} is supported",
                    details={"version": version, "major": major_version}
                )
            else:
                return ComponentHealth(
                    name="EDA Version",
                    status=HealthStatus.DEGRADED,
                    message=f"Version {version} may not be fully supported",
                    details={"version": version, "major": major_version}
                )
                
        except Exception as e:
            return ComponentHealth(
                name="EDA Version",
                status=HealthStatus.UNHEALTHY,
                message=f"Version check failed: {str(e)}"
            )
    
    def check_kubernetes_connectivity(self) -> ComponentHealth:
        """Check Kubernetes connectivity"""
        try:
            from kubernetes import client, config
            
            # Try to load Kubernetes configuration
            try:
                load_k8s_config()
            except Exception as e:
                return ComponentHealth(
                    name="Kubernetes Connectivity",
                    status=HealthStatus.UNHEALTHY,
                    message="No Kubernetes config found"
                )
            
            # Test connectivity with a simple API call
            v1 = client.CoreV1Api()
            v1.list_namespace(limit=1)
            
            return ComponentHealth(
                name="Kubernetes Connectivity",
                status=HealthStatus.HEALTHY,
                message="Kubernetes API is reachable"
            )
            
        except ImportError:
            return ComponentHealth(
                name="Kubernetes Connectivity",
                status=HealthStatus.DEGRADED,
                message="Kubernetes client not available"
            )
        except Exception as e:
            # Check if it's a connection error vs other error
            error_msg = str(e)
            if "Connection refused" in error_msg or "Max retries exceeded" in error_msg:
                return ComponentHealth(
                    name="Kubernetes Connectivity",
                    status=HealthStatus.UNHEALTHY,
                    message="Kubernetes API unreachable"
                )
            else:
                return ComponentHealth(
                    name="Kubernetes Connectivity",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Kubernetes error: {error_msg[:50]}..."
                )
    
    def check_kubernetes_cluster(self) -> ComponentHealth:
        """Check Kubernetes cluster health"""
        try:
            from kubernetes import client, config
            
            # Try to load Kubernetes configuration
            try:
                load_k8s_config()
            except Exception as e:
                return ComponentHealth(
                    name="Kubernetes Cluster",
                    status=HealthStatus.UNHEALTHY,
                    message="No Kubernetes config found"
                )
            
            # Check cluster health
            v1 = client.CoreV1Api()
            
            # Get node status
            try:
                nodes = v1.list_node()
                total_nodes = len(nodes.items)
                ready_nodes = 0
                
                for node in nodes.items:
                    for condition in node.status.conditions:
                        if condition.type == "Ready" and condition.status == "True":
                            ready_nodes += 1
                            break
                
                if ready_nodes == 0:
                    return ComponentHealth(
                        name="Kubernetes Cluster",
                        status=HealthStatus.UNHEALTHY,
                        message="No nodes are ready",
                        details={"total_nodes": total_nodes, "ready_nodes": ready_nodes}
                    )
                elif ready_nodes < total_nodes:
                    return ComponentHealth(
                        name="Kubernetes Cluster",
                        status=HealthStatus.DEGRADED,
                        message=f"{ready_nodes}/{total_nodes} nodes ready",
                        details={"total_nodes": total_nodes, "ready_nodes": ready_nodes}
                    )
                else:
                    return ComponentHealth(
                        name="Kubernetes Cluster",
                        status=HealthStatus.HEALTHY,
                        message=f"All {total_nodes} nodes ready",
                        details={"total_nodes": total_nodes, "ready_nodes": ready_nodes}
                    )
                    
            except Exception as e:
                return ComponentHealth(
                    name="Kubernetes Cluster",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Node check failed: {str(e)[:30]}..."
                )
            
        except ImportError:
            return ComponentHealth(
                name="Kubernetes Cluster",
                status=HealthStatus.DEGRADED,
                message="Kubernetes client not available"
            )
        except Exception as e:
            error_msg = str(e)
            return ComponentHealth(
                name="Kubernetes Cluster",
                status=HealthStatus.UNHEALTHY,
                message=f"Cluster check failed: {error_msg[:30]}..."
            )
    
    def run_full_health_check(self) -> Dict[str, ComponentHealth]:
        """Run a comprehensive health check with dynamic table updates"""
        print("Running comprehensive health check...\n")
        
        # Base checks that are always included
        checks = {
            'connectivity': self.check_eda_connectivity,
            'authentication': self.check_eda_authentication,
            'version': self.check_eda_version,
        }
        
        # Add Kubernetes checks if they're included
        if self.include_kubernetes:
            if 'kubernetes' in self.check_names:
                checks['kubernetes'] = self.check_kubernetes_connectivity
            if 'kubernetes_cluster' in self.check_names:
                checks['kubernetes_cluster'] = self.check_kubernetes_cluster
        
        results = {}
        
        # Show initial table
        self._print_health_table(results)
        
        for check_name, check_func in checks.items():
            # Show current check in progress
            self._print_health_table(results, current_check=check_name)
            time.sleep(0.2)  # Brief pause to show checking status
            
            try:
                results[check_name] = check_func()
            except Exception as e:
                logger.error(f"Health check '{check_name}' failed: {e}")
                results[check_name] = ComponentHealth(
                    name=self.check_names[check_name],
                    status=HealthStatus.UNKNOWN,
                    message=f"Check failed: {str(e)}"
                )
            
            # Show updated results
            self._print_health_table(results)
            time.sleep(0.3)  # Brief pause before next check
        
        print()  # Add final newline
        return results
    
    def get_overall_health_status(self, component_results: Dict[str, ComponentHealth]) -> HealthStatus:
        """Determine overall health from component results"""
        if not component_results:
            return HealthStatus.UNKNOWN
        
        statuses = [comp.status for comp in component_results.values()]
        
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses or HealthStatus.UNKNOWN in statuses:
            return HealthStatus.DEGRADED
        elif all(status == HealthStatus.HEALTHY for status in statuses):
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN
