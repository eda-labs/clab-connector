# clab_connector/clients/kubernetes/client.py

import logging
import re
import time

import yaml

import kubernetes as k8s
from clab_connector.utils.constants import SUBSTEP_INDENT
from kubernetes import config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
from kubernetes.utils import create_from_yaml

k8s_client = k8s.client

HTTP_STATUS_CONFLICT = 409
HTTP_STATUS_NOT_FOUND = 404

logger = logging.getLogger(__name__)

# Attempt to load config:
# 1) If in a Kubernetes pod, load in-cluster config
# 2) Otherwise load local kube config
try:
    config.load_incluster_config()
    logger.debug("Using in-cluster Kubernetes config.")
except Exception:
    try:
        config.load_kube_config()
        logger.debug("Using local kubeconfig.")
    except Exception:
        logger.debug("Kubernetes configuration could not be loaded")


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
    v1 = k8s_client.CoreV1Api()
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
    v1 = k8s_client.CoreV1Api()
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
    core_api = k8s_client.CoreV1Api()
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
            logger.info(f"{SUBSTEP_INDENT}Ping from bsvr to {target_ip} succeeded")
            return True
        else:
            logger.error(
                f"{SUBSTEP_INDENT}Ping from bsvr to {target_ip} failed:\n{resp}"
            )
            return False
    except ApiException as exc:
        logger.error(f"{SUBSTEP_INDENT}API error during ping: {exc}")
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
        custom_api = k8s_client.CustomObjectsApi()

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
                create_from_yaml(
                    k8s_client=k8s_client.ApiClient(),
                    yaml_file=yaml.dump(manifest),
                    namespace=namespace,
                )
            logger.info(
                f"{SUBSTEP_INDENT}Successfully applied {kind} to namespace '{namespace}'"
            )
        except ApiException as e:
            if e.status == HTTP_STATUS_CONFLICT:  # Already exists
                logger.info(
                    f"{SUBSTEP_INDENT}{kind} already exists in namespace '{namespace}'"
                )
            else:
                raise

    except Exception as exc:
        logger.error(f"Failed to apply manifest: {exc}")
        raise RuntimeError(f"Failed to apply manifest: {exc}") from exc


def edactl_namespace_bootstrap(namespace: str) -> int | None:
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
    core_api = k8s_client.CoreV1Api()
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
            logger.info(
                f"{SUBSTEP_INDENT}Namespace {namespace} already exists, skipping bootstrap."
            )
            return None

        match = re.search(r"Transaction (\d+)", resp)
        if match:
            tx_id = int(match.group(1))
            logger.info(
                f"{SUBSTEP_INDENT}Created namespace {namespace} (Transaction: {tx_id})"
            )
            return tx_id

        logger.info(
            f"{SUBSTEP_INDENT}Created namespace {namespace}, no transaction ID found."
        )
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
    v1 = k8s_client.CoreV1Api()
    for attempt in range(max_retries):
        try:
            v1.read_namespace(name=namespace)
            logger.info(f"{SUBSTEP_INDENT}Namespace {namespace} is available")
            return True
        except ApiException as exc:
            if exc.status == HTTP_STATUS_NOT_FOUND:
                logger.debug(
                    f"Waiting for namespace '{namespace}' (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(retry_delay)
            else:
                logger.error(f"Error retrieving namespace {namespace}: {exc}")
                raise
    raise RuntimeError(f"Timed out waiting for namespace {namespace}")


def update_namespace_description(
    namespace: str, description: str, max_retries: int = 5, retry_delay: int = 2
) -> bool:
    """
    Patch a namespace's description. For EDA, this may be a custom CRD
    (group=core.eda.nokia.com, version=v1, plural=namespaces).
    Handles 404 errors with retries if the namespace is not yet available.

    Parameters
    ----------
    namespace : str
        The namespace to patch.
    description : str
        The new description.
    max_retries : int
        Maximum number of retry attempts.
    retry_delay : int
        Delay in seconds between retries.

    Returns
    -------
    bool
        True if successful, False if couldn't update after retries.
    """
    crd_api = k8s_client.CustomObjectsApi()
    group = "core.eda.nokia.com"
    version = "v1"
    plural = "namespaces"

    patch_body = {"spec": {"description": description}}

    # Check if namespace exists in Kubernetes first
    v1 = k8s_client.CoreV1Api()
    try:
        v1.read_namespace(name=namespace)
    except ApiException as exc:
        if exc.status == HTTP_STATUS_NOT_FOUND:
            logger.warning(
                f"{SUBSTEP_INDENT}Kubernetes namespace '{namespace}' does not exist. Cannot update EDA description."
            )
            return False
        else:
            logger.error(f"Error checking namespace '{namespace}': {exc}")
            raise

    # Try to update the EDA namespace description with retries
    for attempt in range(max_retries):
        try:
            resp = crd_api.patch_namespaced_custom_object(
                group=group,
                version=version,
                namespace="eda-system",
                plural=plural,
                name=namespace,
                body=patch_body,
            )
            logger.debug(
                f"Namespace '{namespace}' patched with description. resp={resp}"
            )
            return True
        except ApiException as exc:
            if exc.status == HTTP_STATUS_NOT_FOUND:
                logger.info(
                    f"{SUBSTEP_INDENT}EDA namespace '{namespace}' not found (attempt {attempt + 1}/{max_retries}). Retrying in {retry_delay}s..."
                )
                time.sleep(retry_delay)
            else:
                logger.error(f"Failed to patch namespace '{namespace}': {exc}")
                raise

    logger.warning(
        f"{SUBSTEP_INDENT}Could not update description for namespace '{namespace}' after {max_retries} attempts."
    )
    return False


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
    core_api = k8s_client.CoreV1Api()
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


def list_toponodes_in_namespace(namespace: str):
    crd_api = k8s_client.CustomObjectsApi()
    group = "core.eda.nokia.com"
    version = "v1"
    plural = "toponodes"
    # We do a namespaced call
    toponodes = crd_api.list_namespaced_custom_object(
        group=group, version=version, namespace=namespace, plural=plural
    )
    # returns a dict with "items": [...]
    return toponodes.get("items", [])


def list_topolinks_in_namespace(namespace: str):
    crd_api = k8s_client.CustomObjectsApi()
    group = "core.eda.nokia.com"
    version = "v1"
    plural = "topolinks"
    topolinks = crd_api.list_namespaced_custom_object(
        group=group, version=version, namespace=namespace, plural=plural
    )
    return topolinks.get("items", [])
