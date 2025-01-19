# clab_connector/clients/kubernetes/client.py

import logging
import subprocess
import time
import re
import tempfile
import os
from typing import List, Optional

logger = logging.getLogger(__name__)


def run_kubectl_command(
    cmd: List[str], check: bool = True
) -> subprocess.CompletedProcess:
    """
    Run a kubectl command and optionally check for errors.

    Parameters
    ----------
    cmd : List[str]
        The command list to execute.
    check : bool
        Whether to raise an exception on non-zero exit code.

    Returns
    -------
    subprocess.CompletedProcess
        The result of running the command.

    Raises
    ------
    subprocess.CalledProcessError
        If check is True and the command fails.
    """
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


def get_toolbox_pod() -> str:
    """
    Retrieves the name of the eda-toolbox pod in the eda-system namespace.

    Returns
    -------
    str
        The name of the toolbox pod.

    Raises
    ------
    RuntimeError
        If no toolbox pod is found.
    """
    cmd = [
        "kubectl",
        "get",
        "pods",
        "-n",
        "eda-system",
        "-l",
        "eda.nokia.com/app=eda-toolbox",
        "-o",
        "name",
    ]
    result = run_kubectl_command(cmd, check=True)
    pods = result.stdout.strip().splitlines()
    if not pods:
        raise RuntimeError("No toolbox pod found in 'eda-system' namespace.")
    return pods[0].replace("pod/", "")


def get_bsvr_pod() -> str:
    """
    Retrieves the name of the bootstrapserver pod in the eda-system namespace.

    Returns
    -------
    str
        The name of the bsvr pod.

    Raises
    ------
    RuntimeError
        If no bsvr pod is found.
    """
    cmd = [
        "kubectl",
        "get",
        "pods",
        "-n",
        "eda-system",
        "-l",
        "eda.nokia.com/app=bootstrapserver",
        "-o",
        "name",
    ]
    result = run_kubectl_command(cmd, check=True)
    pods = result.stdout.strip().splitlines()
    if not pods:
        raise RuntimeError("No bsvr pod found in 'eda-system' namespace.")
    return pods[0].replace("pod/", "")


def ping_from_bsvr(target_ip: str) -> bool:
    """
    Ping a target IP from the bsvr pod.

    Parameters
    ----------
    target_ip : str
        The IP address to ping.

    Returns
    -------
    bool
        True if ping succeeds, False otherwise.
    """
    logger.debug(f"Pinging '{target_ip}' from the bsvr pod...")
    bsvr_pod = get_bsvr_pod()
    cmd = [
        "kubectl",
        "exec",
        "-n",
        "eda-system",
        bsvr_pod,
        "--",
        "ping",
        "-c",
        "1",
        target_ip,
    ]
    result = run_kubectl_command(cmd, check=False)
    if result.returncode == 0:
        logger.info(f"Ping from bsvr to {target_ip} succeeded")
        return True
    else:
        logger.error(f"Ping from bsvr to {target_ip} failed: {result.stderr}")
        return False


def apply_manifest(yaml_str: str, namespace: str = "eda-system") -> None:
    """
    Apply a YAML manifest using kubectl.

    Parameters
    ----------
    yaml_str : str
        The YAML content to apply.
    namespace : str
        The namespace to apply the manifest in.

    Raises
    ------
    RuntimeError
        If applying the manifest fails.
    """
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
    Run 'edactl namespace bootstrap <namespace>' inside the toolbox pod.

    Parameters
    ----------
    namespace : str
        The namespace to bootstrap.

    Returns
    -------
    Optional[int]
        The transaction ID if found, None otherwise.

    Raises
    ------
    subprocess.CalledProcessError
        If the bootstrap command fails.
    """
    logger.debug(f"Bootstrapping EDA namespace '{namespace}' via 'edactl'...")
    toolbox_pod = get_toolbox_pod()
    cmd = [
        "kubectl",
        "exec",
        "-n",
        "eda-system",
        toolbox_pod,
        "--",
        "edactl",
        "namespace",
        "bootstrap",
        namespace,
    ]
    result = run_kubectl_command(cmd, check=False)
    if result.returncode != 0:
        if "already exists" in result.stderr:
            logger.info(f"Namespace {namespace} already exists, skipping bootstrap.")
            return None
        logger.error(f"Failed to bootstrap namespace: {result.stderr}")
        raise subprocess.CalledProcessError(
            returncode=result.returncode,
            cmd=cmd,
            output=result.stdout,
            stderr=result.stderr,
        )

    match = re.search(r"Transaction (\d+)", result.stdout)
    if match:
        tx_id = int(match.group(1))
        logger.info(f"Created namespace {namespace} (Transaction: {tx_id})")
        return tx_id

    logger.info(f"Created namespace {namespace}, no transaction ID found.")
    return None


def wait_for_namespace(
    namespace: str, max_retries: int = 10, retry_delay: int = 1
) -> bool:
    """
    Wait for a Kubernetes namespace to appear.

    Parameters
    ----------
    namespace : str
        The namespace to wait for.
    max_retries : int
        Maximum number of retries.
    retry_delay : int
        Delay in seconds between retries.

    Returns
    -------
    bool
        True if the namespace is found, False otherwise.

    Raises
    ------
    RuntimeError
        If the namespace is not created within the retry limit.
    """
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
    """
    Patch the namespace with a custom description using kubectl.

    Parameters
    ----------
    namespace : str
        The namespace to patch.
    description : str
        The description to apply.

    Raises
    ------
    subprocess.CalledProcessError
        If the patch command fails.
    """
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
    Revert a commit in EDA's configuration Git repository.

    Parameters
    ----------
    commit_hash : str
        The commit hash to revert.

    Returns
    -------
    bool
        True if successful, False otherwise.
    """
    logger.debug(f"Reverting EDA commit '{commit_hash}' via 'edactl'...")
    toolbox_pod = get_toolbox_pod()
    cmd = [
        "kubectl",
        "exec",
        "-n",
        "eda-system",
        toolbox_pod,
        "--",
        "edactl",
        "git",
        "revert",
        commit_hash,
    ]
    result = run_kubectl_command(cmd, check=False)
    if result.returncode == 0:
        logger.info(f"Successfully reverted commit {commit_hash}")
        return True
    else:
        logger.error(f"Failed to revert commit {commit_hash}: {result.stderr}")
        return False
