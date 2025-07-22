# clab_connector/utils/kubernetes_utils.py

"""Minimal Kubernetes utilities to eliminate duplication"""

def load_k8s_config():
    """Load Kubernetes config, trying in-cluster first, then local"""
    from kubernetes import config
    
    try:
        config.load_incluster_config()
    except:
        config.load_kube_config()  # Will raise if no config found