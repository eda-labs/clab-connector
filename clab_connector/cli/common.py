# clab_connector/cli/common.py

"""Minimal shared utilities to eliminate CLI duplication"""

from clab_connector.clients.eda.client import EDAClient


def create_eda_client(**kwargs) -> EDAClient:
    """Create EDA client from common parameters"""
    return EDAClient(
        hostname=kwargs['eda_url'],
        eda_user=kwargs.get('eda_user', 'admin'),
        eda_password=kwargs.get('eda_password', 'admin'),
        kc_secret=kwargs.get('kc_secret'),
        kc_user=kwargs.get('kc_user', 'admin'),
        kc_password=kwargs.get('kc_password', 'admin'),
        verify=kwargs.get('verify', False)
    )