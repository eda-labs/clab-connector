# clab_connector/clients/kubernetes/client.py

import logging
import re
import time
import yaml
from typing import Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
from kubernetes.utils import create_from_yaml

logger = logging.getLogger(__name__)

# Attempt to load config:
# 1) If in a Kubernetes pod, load in-cluster config
# 2) Otherwise load local kube config
try:
    config.load_incluster_config()
    logger.debug("Using in-cluster Kubernetes config.")
except Exception:
    config.load_kube_config()
    logger.debug("Using local kubeconfig.")


def get_toolbox_pod() -> str:
    """
    Retrieves the name of the toolbox pod in the eda-system namespace,
    identified by labelSelector: eda.nokia.com/app=eda-toolbox.

    Returns
    -------
    str
        The name of the first matching toolbox pod.

    Raises
    ------
    RuntimeError
        If no toolbox pod is found.
    """
    v1 = client.CoreV1Api()
    label_selector = "eda.nokia.com/app=eda-toolbox"
    pods = v1.list_namespaced_pod("eda-system", label_selector=label_selector)
    if not pods.items:
        raise RuntimeError("No toolbox pod found in 'eda-system' namespace.")
    return pods.items[0].metadata.name


def get_bsvr_pod() -> str:
    """
    Retrieves the name of the bootstrapserver (bsvr) pod in eda-system,
    identified by labelSelector: eda.nokia.com/app=bootstrapserver.

    Returns
    -------
    str
        The name of the first matching bsvr pod.

    Raises
    ------
    RuntimeError
        If no bsvr pod is found.
    """
    v1 = client.CoreV1Api()
    label_selector = "eda.nokia.com/app=bootstrapserver"
    pods = v1.list_namespaced_pod("eda-system", label_selector=label_selector)
    if not pods.items:
        raise RuntimeError("No bsvr pod found in 'eda-system' namespace.")
    return pods.items[0].metadata.name


def ping_from_bsvr(target_ip: str) -> bool:
    """
    Ping a target IP from the bsvr pod.

    Parameters
    ----------
    target_ip : str
        IP address to ping.

    Returns
    -------
    bool
        True if ping indicates success, False otherwise.
    """
    logger.debug(f"Pinging '{target_ip}' from the bsvr pod...")
    bsvr_name = get_bsvr_pod()
    core_api = client.CoreV1Api()
    command = ["ping", "-c", "1", target_ip]
    try:
        resp = stream(
            core_api.connect_get_namespaced_pod_exec,
            name=bsvr_name,
            namespace="eda-system",
            command=command,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
        )
        # A quick check for "1 packets transmitted, 1 received"
        if "1 packets transmitted, 1 received" in resp:
            logger.info(f"Ping from bsvr to {target_ip} succeeded")
            return True
        else:
            logger.error(f"Ping from bsvr to {target_ip} failed:\n{resp}")
            return False
    except ApiException as exc:
        logger.error(f"API error during ping: {exc}")
        return False


def apply_manifest(yaml_str: str, namespace: str = "eda-system") -> None:
    """
    Apply a YAML manifest using Python's create_from_yaml().

    Parameters
    ----------
    yaml_str : str
        The YAML content to apply.
    namespace : str
        The namespace into which to apply this resource.

    Raises
    ------
    RuntimeError
        If applying the manifest fails.
    """
    try:
        # Parse the YAML string into a dict
        manifest = yaml.safe_load(yaml_str)

        # Get the API version and kind
        api_version = manifest.get("apiVersion")
        kind = manifest.get("kind")

        if not api_version or not kind:
            raise RuntimeError("YAML manifest must specify apiVersion and kind")

        # Split API version into group and version
        if "/" in api_version:
            group, version = api_version.split("/")
        else:
            group = ""
            version = api_version

        # Use CustomObjectsApi for custom resources
        custom_api = client.CustomObjectsApi()

        try:
            if group:
                # For custom resources (like Artifact)
                custom_api.create_namespaced_custom_object(
                    group=group,
                    version=version,
                    namespace=namespace,
                    plural=f"{kind.lower()}s",  # Convention is to use lowercase plural
                    body=manifest,
                )
            else:
                # For core resources
                v1 = client.CoreV1Api()
                create_from_yaml(
                    k8s_client=client.ApiClient(),
                    yaml_file=yaml.dump(manifest),
                    namespace=namespace,
                )
            logger.info(f"Successfully applied {kind} to namespace '{namespace}'")
        except ApiException as e:
            if e.status == 409:  # Already exists
                logger.info(f"{kind} already exists in namespace '{namespace}'")
            else:
                raise

    except Exception as exc:
        logger.error(f"Failed to apply manifest: {exc}")
        raise RuntimeError(f"Failed to apply manifest: {exc}")


def edactl_namespace_bootstrap(namespace: str) -> Optional[int]:
    """
    Emulate `kubectl exec <toolbox_pod> -- edactl namespace bootstrap <namespace>`
    by streaming an exec call into the toolbox pod.

    Parameters
    ----------
    namespace : str
        Namespace to bootstrap in EDA.

    Returns
    -------
    Optional[int]
        The transaction ID if found, or None if skipping/existing.
    """
    toolbox = get_toolbox_pod()
    core_api = client.CoreV1Api()
    cmd = ["edactl", "namespace", "bootstrap", namespace]
    try:
        resp = stream(
            core_api.connect_get_namespaced_pod_exec,
            name=toolbox,
            namespace="eda-system",
            command=cmd,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
        )
        if "already exists" in resp:
            logger.info(f"Namespace {namespace} already exists, skipping bootstrap.")
            return None

        match = re.search(r"Transaction (\d+)", resp)
        if match:
            tx_id = int(match.group(1))
            logger.info(f"Created namespace {namespace} (Transaction: {tx_id})")
            return tx_id

        logger.info(f"Created namespace {namespace}, no transaction ID found.")
        return None
    except ApiException as exc:
        logger.error(f"Failed to bootstrap namespace {namespace}: {exc}")
        raise


def wait_for_namespace(
    namespace: str, max_retries: int = 10, retry_delay: int = 1
) -> bool:
    """
    Wait for a namespace to exist in Kubernetes.

    Parameters
    ----------
    namespace : str
        Namespace to wait for.
    max_retries : int
        Maximum number of attempts.
    retry_delay : int
        Delay (seconds) between attempts.

    Returns
    -------
    bool
        True if the namespace is found, else raises.

    Raises
    ------
    RuntimeError
        If the namespace is not found within the given attempts.
    """
    v1 = client.CoreV1Api()
    for attempt in range(max_retries):
        try:
            v1.read_namespace(name=namespace)
            logger.info(f"Namespace {namespace} is available")
            return True
        except ApiException as exc:
            if exc.status == 404:
                logger.debug(
                    f"Waiting for namespace '{namespace}' (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(retry_delay)
            else:
                logger.error(f"Error retrieving namespace {namespace}: {exc}")
                raise
    raise RuntimeError(f"Timed out waiting for namespace {namespace}")


def update_namespace_description(namespace: str, description: str) -> None:
    """
    Patch a namespace's description. For EDA, this may be a custom CRD
    (group=core.eda.nokia.com, version=v1, plural=namespaces).

    Parameters
    ----------
    namespace : str
        The namespace to patch.
    description : str
        The new description.

    Raises
    ------
    ApiException
        If the patch fails.
    """
    crd_api = client.CustomObjectsApi()
    group = "core.eda.nokia.com"
    version = "v1"
    plural = "namespaces"

    patch_body = {"spec": {"description": description}}

    try:
        resp = crd_api.patch_namespaced_custom_object(
            group=group,
            version=version,
            namespace="eda-system",  # If it's a cluster-scoped CRD, use patch_cluster_custom_object
            plural=plural,
            name=namespace,
            body=patch_body,
        )
        logger.info(f"Namespace '{namespace}' patched with description. resp={resp}")
    except ApiException as exc:
        logger.error(f"Failed to patch namespace '{namespace}': {exc}")
        raise


def edactl_revert_commit(commit_hash: str) -> bool:
    """
    Revert an EDA commit by running `edactl git revert <commit_hash>` in the toolbox pod.

    Parameters
    ----------
    commit_hash : str
        The commit hash to revert.

    Returns
    -------
    bool
        True if revert is successful, False otherwise.
    """
    toolbox = get_toolbox_pod()
    core_api = client.CoreV1Api()
    cmd = ["edactl", "git", "revert", commit_hash]
    try:
        resp = stream(
            core_api.connect_get_namespaced_pod_exec,
            name=toolbox,
            namespace="eda-system",
            command=cmd,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
        )
        if "Successfully reverted commit" in resp:
            logger.info(f"Successfully reverted commit {commit_hash}")
            return True
        else:
            logger.error(f"Failed to revert commit {commit_hash}: {resp}")
            return False
    except ApiException as exc:
        logger.error(f"Failed to revert commit {commit_hash}: {exc}")
        return False
