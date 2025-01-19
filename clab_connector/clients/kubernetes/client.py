# clab_connector/clients/kubernetes/client.py

import logging
import subprocess
import time
import re
import tempfile
import os
from typing import List, Optional

logger = logging.getLogger(__name__)


def ping_from_bsvr(target_ip: str) -> bool:
    """
    Example placeholder: old logic used 'get_bsvr_pod()' & 'kubectl exec ... ping -c 1 <IP>'.
    """
    # ...
    logger.debug(f"Simulate ping from bsvr to {target_ip}")
    return True  # or False if you detect a failure


def run_kubectl_command(
    cmd: List[str], check: bool = True
) -> subprocess.CompletedProcess:
    logger.debug(f"Running command: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        if result.returncode != 0:
            logger.debug(
                f"Command returned error code {result.returncode}:\n{result.stderr}"
            )
        else:
            logger.debug(f"Command stdout:\n{result.stdout}")
        return result
    except subprocess.CalledProcessError as e:
        logger.error(f"Kubectl command failed: {e.stderr}")
        raise


def apply_manifest(yaml_str: str, namespace: str = "eda-system") -> None:
    fd, tmp_path = tempfile.mkstemp(suffix=".yaml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(yaml_str)
        cmd = ["kubectl", "apply", "-n", namespace, "-f", tmp_path]
        run_kubectl_command(cmd)
    except Exception as e:
        raise RuntimeError(f"Failed to apply manifest: {e}")
    finally:
        os.remove(tmp_path)


def edactl_namespace_bootstrap(namespace: str) -> Optional[int]:
    """
    Example placeholder logic for 'edactl namespace bootstrap <ns>'
    via some 'kubectl exec <toolbox-pod> -- edactl namespace bootstrap <ns>'
    """
    logger.debug(f"Simulate 'edactl namespace bootstrap {namespace}'")
    return None


def wait_for_namespace(
    namespace: str, max_retries: int = 10, retry_delay: int = 1
) -> bool:
    for i in range(max_retries):
        cmd = ["kubectl", "get", "namespace", namespace]
        result = run_kubectl_command(cmd, check=False)
        if result.returncode == 0:
            logger.info(f"Namespace {namespace} is available")
            return True
        logger.debug(
            f"Waiting for namespace {namespace} (attempt {i + 1}/{max_retries})"
        )
        time.sleep(retry_delay)
    raise RuntimeError(f"Timed out waiting for namespace {namespace}")


def update_namespace_description(namespace: str, description: str) -> None:
    patch_data = f'{{"spec":{{"description":"{description}"}}}}'
    cmd = [
        "kubectl",
        "patch",
        "namespace.core.eda.nokia.com",
        namespace,
        "-n",
        "eda-system",
        "--type=merge",
        "-p",
        patch_data,
    ]
    run_kubectl_command(cmd)


def edactl_revert_commit(commit_hash: str) -> bool:
    """
    Example placeholder
    """
    logger.debug(f"Simulate edactl revert commit {commit_hash}")
    return True
