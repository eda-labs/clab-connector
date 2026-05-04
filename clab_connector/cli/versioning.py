"""Version helpers for the clab-connector CLI."""

from __future__ import annotations

import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from importlib import metadata

PACKAGE_NAME = "clab-connector"
REPO_URL = "https://github.com/eda-labs/clab-connector"
LATEST_RELEASE_URL = f"{REPO_URL}/releases/latest"
UPGRADE_COMMAND = "uv tool upgrade clab-connector"
VERSION_CHECK_ENV = "CLAB_CONNECTOR_VERSION_CHECK"
AUTO_VERSION_CHECK_TIMEOUT = 3.0
EXPLICIT_VERSION_CHECK_TIMEOUT = 5.0

_REDIRECT_CODES = {301, 302, 303, 307, 308}
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[.+-].*)?$", re.IGNORECASE)

logger = logging.getLogger(__name__)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Return 3xx responses to the caller instead of following redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


def get_cli_version() -> str:
    """Return the installed clab-connector package version."""

    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        logger.debug(
            "Could not resolve installed package metadata for %s", PACKAGE_NAME
        )
        return "unknown"


def version_check_disabled() -> bool:
    """Return True when automatic version checking is disabled by env var."""

    return "disable" in os.environ.get(VERSION_CHECK_ENV, "").lower()


def parse_version_parts(version: str) -> tuple[int, int, int] | None:
    """Parse a release version into comparable major/minor/patch integers."""

    match = _VERSION_RE.match(version.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_newer_version(current_version: str, latest_version: str) -> bool:
    """Return True when latest_version is newer than current_version."""

    current_parts = parse_version_parts(current_version)
    latest_parts = parse_version_parts(latest_version)
    if current_parts is None or latest_parts is None:
        return False
    return latest_parts > current_parts


def parse_release_tag_from_location(location: str) -> str | None:
    """Extract a release tag from a GitHub releases redirect location."""

    if not location:
        return None

    absolute_location = urllib.parse.urljoin(LATEST_RELEASE_URL, location)
    parsed = urllib.parse.urlparse(absolute_location)
    marker = "/releases/tag/"
    if marker not in parsed.path:
        return None

    tag = urllib.parse.unquote(parsed.path.split(marker, 1)[1].split("/", 1)[0])
    if parse_version_parts(tag) is None:
        return None
    return tag


def fetch_latest_release_tag(timeout: float = AUTO_VERSION_CHECK_TIMEOUT) -> str | None:
    """
    Fetch the latest public GitHub release tag without using the GitHub API.

    This intentionally performs an unauthenticated HEAD request against the public
    releases/latest redirect and parses the Location header. Any failure is
    advisory only and returns None.
    """

    if version_check_disabled():
        return None

    request = urllib.request.Request(
        LATEST_RELEASE_URL,
        method="HEAD",
        headers={"User-Agent": f"{PACKAGE_NAME}/{get_cli_version()}"},
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())

    try:
        with opener.open(request, timeout=timeout) as response:
            location = response.headers.get("Location") or response.geturl()
    except urllib.error.HTTPError as err:
        if err.code not in _REDIRECT_CODES:
            logger.debug("Latest version check failed with HTTP %s", err.code)
            return None
        location = err.headers.get("Location")
    except (TimeoutError, OSError, ValueError, urllib.error.URLError) as err:
        logger.debug("Latest version check failed: %s", err)
        return None

    return parse_release_tag_from_location(location or "")


def get_upgrade_notice(timeout: float = AUTO_VERSION_CHECK_TIMEOUT) -> str | None:
    """Return an upgrade notice when a newer clab-connector release is available."""

    current_version = get_cli_version()
    latest_version = fetch_latest_release_tag(timeout=timeout)
    if not latest_version or not is_newer_version(current_version, latest_version):
        return None

    return (
        f"A newer clab-connector version ({latest_version}) is available. "
        f"Upgrade with: {UPGRADE_COMMAND}"
    )
