# clab_connector/clients/eda/http_client.py

import logging
import os
import re
import urllib3
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def get_proxy_settings():
    """
    Get proxy settings from environment variables.
    Handles both upper and lowercase variants.

    Returns
    -------
    tuple: (http_proxy, https_proxy, no_proxy)
    """
    # Check both variants
    http_upper = os.environ.get("HTTP_PROXY")
    http_lower = os.environ.get("http_proxy")
    https_upper = os.environ.get("HTTPS_PROXY")
    https_lower = os.environ.get("https_proxy")
    no_upper = os.environ.get("NO_PROXY")
    no_lower = os.environ.get("no_proxy")

    # Log if both variants are set
    if http_upper and http_lower and http_upper != http_lower:
        logger.warning(
            f"Both HTTP_PROXY ({http_upper}) and http_proxy ({http_lower}) are set with different values. Using HTTP_PROXY."
        )

    if https_upper and https_lower and https_upper != https_lower:
        logger.warning(
            f"Both HTTPS_PROXY ({https_upper}) and https_proxy ({https_lower}) are set with different values. Using HTTPS_PROXY."
        )

    if no_upper and no_lower and no_upper != no_lower:
        logger.warning(
            f"Both NO_PROXY ({no_upper}) and no_proxy ({no_lower}) are set with different values. Using NO_PROXY."
        )

    # Use uppercase variants if set, otherwise lowercase
    http_proxy = http_upper if http_upper is not None else http_lower
    https_proxy = https_upper if https_upper is not None else https_lower
    no_proxy = no_upper if no_upper is not None else no_lower or ""

    return http_proxy, https_proxy, no_proxy


def should_bypass_proxy(url, no_proxy=None):
    """
    Check if the given URL should bypass proxy based on NO_PROXY settings.

    Parameters
    ----------
    url : str
        The URL to check
    no_proxy : str, optional
        The NO_PROXY string to use. If None, gets from environment.

    Returns
    -------
    bool
        True if proxy should be bypassed, False otherwise
    """
    if no_proxy is None:
        _, _, no_proxy = get_proxy_settings()

    if not no_proxy:
        return False

    parsed_url = urlparse(url if "//" in url else f"http://{url}")
    hostname = parsed_url.hostname

    if not hostname:
        return False

    # Split NO_PROXY into parts and clean them
    no_proxy_parts = [p.strip() for p in no_proxy.split(",") if p.strip()]

    for no_proxy_value in no_proxy_parts:
        # Convert .foo.com to foo.com
        if no_proxy_value.startswith("."):
            no_proxy_value = no_proxy_value[1:]

        # Handle IP addresses and CIDR notation
        if re.match(r"^(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?$", no_proxy_value):
            # TODO: Implement CIDR matching if needed
            if hostname == no_proxy_value:
                return True
        # Handle domain names with wildcards
        else:
            pattern = re.escape(no_proxy_value).replace(r"\*", ".*")
            if re.match(f"^{pattern}$", hostname, re.IGNORECASE):
                return True

    return False


def create_pool_manager(url=None, verify=True):
    """
    Create a PoolManager or ProxyManager based on environment settings and URL

    Parameters
    ----------
    url : str, optional
        The URL that will be accessed with this pool manager
        If provided, NO_PROXY rules will be checked
    verify : bool
        Whether to verify SSL certificates

    Returns
    -------
    urllib3.PoolManager or urllib3.ProxyManager
    """
    http_proxy, https_proxy, no_proxy = get_proxy_settings()

    # Check if this URL should bypass proxy
    if url and should_bypass_proxy(url, no_proxy):
        logger.debug(f"URL {url} matches NO_PROXY rules, creating direct PoolManager")
        return urllib3.PoolManager(
            cert_reqs="CERT_REQUIRED" if verify else "CERT_NONE",
            retries=urllib3.Retry(3),
        )

    proxy_url = https_proxy or http_proxy
    if proxy_url:
        logger.debug(f"Creating ProxyManager with proxy URL: {proxy_url}")
        return urllib3.ProxyManager(
            proxy_url,
            cert_reqs="CERT_REQUIRED" if verify else "CERT_NONE",
            retries=urllib3.Retry(3),
        )

    logger.debug("Creating PoolManager without proxy")
    return urllib3.PoolManager(
        cert_reqs="CERT_REQUIRED" if verify else "CERT_NONE", retries=urllib3.Retry(3)
    )
