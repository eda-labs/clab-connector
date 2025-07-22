# clab_connector/utils/kubernetes_utils.py

"""Minimal Kubernetes utilities to eliminate duplication"""

from kubernetes import config


def load_k8s_config() -> None:
    """Load Kubernetes config, trying in-cluster first, then local."""

    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config()  # Will raise if no config found
