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
    Run a kubectl command and return the result

    Parameters
    ----------
    cmd: List[str]
        The kubectl command to run as a list of strings
    check: bool
        Whether to raise an exception on non-zero return code

    Returns
    -------
    subprocess.CompletedProcess
        The completed process result
    """
    logger.debug(f"Running command: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        if result.returncode == 0:
            if result.stdout.strip():
                logger.info(f"Command succeeded:\n{result.stdout}")
        else:
            logger.debug(
                f"Command failed:\nstdout={result.stdout}\nstderr={result.stderr}"
            )
        return result
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed:\nstdout={e.stdout}\nstderr={e.stderr}")
        raise


def get_pod_by_label(label: str, namespace: str = "eda-system") -> str:
    """
    Get pod name by label selector

    Parameters
    ----------
    label: str
        The label selector to match pods
    namespace: str
        The namespace to search in

    Returns
    -------
    str
        The name of the first matching pod

    Raises
    ------
    Exception
        If no pod is found or kubectl command fails
    """
    cmd = ["kubectl", "get", "pods", "-n", namespace, "-l", label, "-o", "name"]
    try:
        result = run_kubectl_command(cmd)
        pod_name = result.stdout.strip().replace("pod/", "")
        if not pod_name:
            raise Exception(f"Could not find pod with label {label}")
        return pod_name
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get pod name: {e}")


def get_toolbox_pod() -> str:
    """
    Gets the name of the eda-toolbox pod

    Returns
    -------
    str
        The name of the eda-toolbox pod

    Raises
    ------
    Exception
        If pod cannot be found
    """
    return get_pod_by_label("eda.nokia.com/app=eda-toolbox")


def get_bsvr_pod() -> str:
    """
    Gets the name of the eda-bsvr pod

    Returns
    -------
    str
        The name of the eda-bsvr pod

    Raises
    ------
    Exception
        If pod cannot be found
    """
    return get_pod_by_label("eda.nokia.com/app=bootstrapserver")


def exec_in_pod(
    pod_name: str, namespace: str, command: List[str], check: bool = True
) -> subprocess.CompletedProcess:
    """
    Execute a command in a pod

    Parameters
    ----------
    pod_name: str
        Name of the pod to execute in
    namespace: str
        Namespace of the pod
    command: List[str]
        Command to execute as list of strings
    check: bool
        Whether to raise an exception on non-zero return code

    Returns
    -------
    subprocess.CompletedProcess
        The completed process result
    """
    cmd = ["kubectl", "exec", "-n", namespace, pod_name, "--"] + command
    return run_kubectl_command(cmd, check=check)


def apply_manifest(yaml_str: str, namespace: str = "eda-system") -> None:
    """
    Applies a kubernetes manifest

    Parameters
    ----------
    yaml_str: str
        The YAML manifest to apply
    namespace: str
        The namespace to apply the manifest to

    Raises
    ------
    RuntimeError
        If manifest application fails
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".yaml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(yaml_str)
        cmd = ["kubectl", "apply", "-n", namespace, "-f", tmp_path]
        result = run_kubectl_command(cmd)
    except Exception as e:
        raise RuntimeError(f"Failed to apply manifest: {e}")
    finally:
        os.remove(tmp_path)


def edactl_namespace_bootstrap(namespace: str) -> Optional[int]:
    """
    Execute edactl namespace bootstrap command

    Parameters
    ----------
    namespace: str
        The namespace to bootstrap

    Returns
    -------
    Optional[int]
        The transaction ID if found, None otherwise
    """
    toolbox_pod = get_toolbox_pod()
    result = exec_in_pod(
        toolbox_pod, "eda-system", ["edactl", "namespace", "bootstrap", namespace]
    )

    match = re.search(r"Transaction (\d+)", result.stdout)
    if match:
        transaction_id = int(match.group(1))
        logger.info(
            f"Successfully created namespace {namespace} (Transaction ID: {transaction_id})"
        )
        return transaction_id
    logger.info(f"Namespace {namespace} created but no transaction ID found")
    return None


def wait_for_namespace(
    namespace: str, max_retries: int = 10, retry_delay: int = 1
) -> bool:
    """
    Wait for namespace to be available

    Parameters
    ----------
    namespace: str
        The namespace to wait for
    max_retries: int
        Maximum number of retry attempts
    retry_delay: int
        Delay between retries in seconds

    Returns
    -------
    bool
        True if namespace becomes available

    Raises
    ------
    Exception
        If namespace does not become available within max_retries
    """
    for i in range(max_retries):
        cmd = ["kubectl", "get", "namespace", namespace]
        result = run_kubectl_command(cmd, check=False)
        if result.returncode == 0:
            logger.info(f"Namespace {namespace} is available")
            return True
        logger.debug(f"Waiting for namespace (attempt {i + 1}/{max_retries})")
        time.sleep(retry_delay)
    raise Exception(f"Timed out waiting for namespace {namespace}")


def update_namespace_description(namespace: str, description: str) -> None:
    """
    Update namespace description using kubectl patch

    Parameters
    ----------
    namespace: str
        The namespace to update
    description: str
        The new description to set
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


def ping_from_bsvr(target_ip: str) -> bool:
    """
    Ping a target from the bootstrap server pod

    Parameters
    ----------
    target_ip: str
        The IP address to ping

    Returns
    -------
    bool
        True if ping succeeds, False otherwise
    """
    bsvr_pod = get_bsvr_pod()
    result = exec_in_pod(
        bsvr_pod, "eda-system", ["ping", "-c", "1", target_ip], check=False
    )
    return result.returncode == 0


def edactl_revert_commit(commit_hash: str) -> bool:
    """
    Reverts to a specific commit hash

    Parameters
    ----------
    commit_hash: str
        The commit hash to revert to

    Returns
    -------
    bool
        True if revert succeeds, False otherwise
    """
    toolbox_pod = get_toolbox_pod()
    result = exec_in_pod(
        toolbox_pod, "eda-system", ["edactl", "git", "revert", commit_hash]
    )
    success = (
        "error" not in result.stdout.lower() and "error" not in result.stderr.lower()
    )
    if success:
        logger.info(f"Successfully reverted commit {commit_hash}")
    else:
        logger.error(f"Failed to revert commit {commit_hash}")
    return success
