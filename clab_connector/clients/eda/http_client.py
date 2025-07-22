# clab_connector/clients/eda/http_client.py

import logging
import os
import re
from urllib.parse import urlparse

import urllib3

logger = logging.getLogger(__name__)


def get_proxy_settings():
    """
    Read proxy environment variables.

    Returns
    -------
    tuple
        (http_proxy, https_proxy, no_proxy).
    """
    http_upper = os.environ.get("HTTP_PROXY")
    http_lower = os.environ.get("http_proxy")
    https_upper = os.environ.get("HTTPS_PROXY")
    https_lower = os.environ.get("https_proxy")
    no_upper = os.environ.get("NO_PROXY")
    no_lower = os.environ.get("no_proxy")

    if http_upper and http_lower and http_upper != http_lower:
        logger.warning("Both HTTP_PROXY and http_proxy are set. Using HTTP_PROXY.")
    if https_upper and https_lower and https_upper != https_lower:
        logger.warning("Both HTTPS_PROXY and https_proxy are set. Using HTTPS_PROXY.")
    if no_upper and no_lower and no_upper != no_lower:
        logger.warning("Both NO_PROXY and no_proxy are set. Using NO_PROXY.")

    http_proxy = http_upper if http_upper else http_lower
    https_proxy = https_upper if https_upper else https_lower
    no_proxy = no_upper if no_upper else no_lower or ""
    return http_proxy, https_proxy, no_proxy


def should_bypass_proxy(url, no_proxy=None):
    """
    Check if a URL should bypass proxy based on NO_PROXY settings.

    Parameters
    ----------
    url : str
        The URL to check.
    no_proxy : str, optional
        NO_PROXY environment variable content.

    Returns
    -------
    bool
        True if the URL is matched by no_proxy patterns, False otherwise.
    """
    if no_proxy is None:
        _, _, no_proxy = get_proxy_settings()
    if not no_proxy:
        return False

    parsed_url = urlparse(url if "//" in url else f"http://{url}")
    hostname = parsed_url.hostname
    if not hostname:
        return False

    no_proxy_parts = [p.strip() for p in no_proxy.split(",") if p.strip()]

    for np_entry in no_proxy_parts:
        pattern_val = np_entry[1:] if np_entry.startswith(".") else np_entry
        # Convert wildcard to regex
        pattern = re.escape(pattern_val).replace(r"\*", ".*")
        if re.match(f"^{pattern}$", hostname, re.IGNORECASE):
            return True

    return False


def create_pool_manager(url=None, verify=True):
    """
    Create an appropriate urllib3 PoolManager or ProxyManager for the given URL.

    Parameters
    ----------
    url : str, optional
        The base URL used to decide if proxy should be bypassed.
    verify : bool
        Whether to enforce certificate validation.

    Returns
    -------
    urllib3.PoolManager or urllib3.ProxyManager
        The configured HTTP client manager.
    """
    http_proxy, https_proxy, no_proxy = get_proxy_settings()
    if url and should_bypass_proxy(url, no_proxy):
        logger.debug(f"URL {url} in NO_PROXY, returning direct PoolManager.")
        return urllib3.PoolManager(
            cert_reqs="CERT_REQUIRED" if verify else "CERT_NONE",
            retries=urllib3.Retry(3),
        )
    proxy_url = https_proxy or http_proxy
    if proxy_url:
        logger.debug(f"Using ProxyManager: {proxy_url}")
        return urllib3.ProxyManager(
            proxy_url,
            cert_reqs="CERT_REQUIRED" if verify else "CERT_NONE",
            retries=urllib3.Retry(3),
        )
    logger.debug("No proxy, returning direct PoolManager.")
    return urllib3.PoolManager(
        cert_reqs="CERT_REQUIRED" if verify else "CERT_NONE",
        retries=urllib3.Retry(3),
    )
