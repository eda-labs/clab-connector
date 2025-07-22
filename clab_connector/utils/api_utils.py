# clab_connector/utils/api_utils.py

"""Minimal API utilities to eliminate duplication"""

import json
import logging

logger = logging.getLogger(__name__)


def try_api_endpoints(client, endpoints, log_name="resource"):
    """Try multiple API endpoints until one succeeds"""
    for endpoint in endpoints:
        try:
            response = client.get(endpoint)
            if response.status == 200:
                data = json.loads(response.data.decode('utf-8'))
                logger.debug(f"Successfully got {log_name} via endpoint: {endpoint}")
                return data, endpoint
            else:
                logger.debug(f"API call to {endpoint} returned status {response.status}")
        except Exception as e:
            logger.debug(f"Error trying endpoint {endpoint}: {e}")
    
    logger.warning(f"Failed to get {log_name} from any API endpoint")
    return None, None


def extract_k8s_names(data, name_filter=None):
    """Extract names from Kubernetes-style API response"""
    names = []
    
    if isinstance(data, dict) and 'items' in data:
        for item in data['items']:
            if isinstance(item, dict) and 'metadata' in item:
                name = item['metadata'].get('name', '')
                if name and (not name_filter or name_filter(name)):
                    names.append(name)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                if not name_filter or name_filter(item):
                    names.append(item)
            elif isinstance(item, dict):
                name = item.get('name', '') or item.get('metadata', {}).get('name', '')
                if name and (not name_filter or name_filter(name)):
                    names.append(name)
    
    return names