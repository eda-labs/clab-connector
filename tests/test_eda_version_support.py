import logging

import pytest

from clab_connector.clients.eda.client import (
    MAX_TESTED_EDA_VERSION,
    MIN_SUPPORTED_EDA_VERSION,
    EDAClient,
    parse_version_parts,
)
from clab_connector.models.node.nokia_srl import NokiaSRLinuxNode


def make_client(version):
    client = EDAClient.__new__(EDAClient)
    client.version = version
    return client


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("26.8.1", (26, 8)),
        ("v26.8.1", (26, 8)),
        ("26.4.1", (26, 4)),
        ("24.12.1", (24, 12)),
        ("unknown", (0, 0)),
    ],
)
def test_get_version_parts(version, expected):
    assert parse_version_parts(version) == expected
    assert make_client(version).get_version_parts() == expected


def test_supported_range_covers_26_4_through_26_8():
    assert MIN_SUPPORTED_EDA_VERSION == (26, 4)
    assert MAX_TESTED_EDA_VERSION == (26, 8)


@pytest.mark.parametrize("version", ["26.4.1", "26.8.1", "26.5.0", "v26.8.1"])
def test_no_warning_for_supported_versions(version, caplog):
    with caplog.at_level(logging.WARNING):
        EDAClient._warn_on_unsupported_version(version)
    assert caplog.records == []


def test_no_warning_for_unparseable_version(caplog):
    with caplog.at_level(logging.WARNING):
        EDAClient._warn_on_unsupported_version("unknown")
    assert caplog.records == []


@pytest.mark.parametrize("version", ["25.12.1", "24.12.1"])
def test_warns_below_minimum_supported_version(version, caplog):
    with caplog.at_level(logging.WARNING):
        EDAClient._warn_on_unsupported_version(version)
    assert "older than the minimum supported release" in caplog.text
    assert "0.8.11" in caplog.text


def test_warns_above_last_tested_version(caplog):
    with caplog.at_level(logging.WARNING):
        EDAClient._warn_on_unsupported_version("27.4.1")
    assert "newer than the latest tested release" in caplog.text


# Every SR Linux release published to nokia-eda/schema-profiles, with the build
# number of its schema zip. Kept in sync with the releases of that repository.
SCHEMA_PROFILE_BUILDS = {
    "24.10.4": "244",
    "24.10.5": "344",
    "24.10.6": "209",
    "24.10.7": "191",
    "25.3.2": "312",
    "25.3.3": "158",
    "25.7.1": "187",
    "25.7.2": "266",
    "25.10.1": "399",
    "25.10.2": "527",
    "25.10.3": "449",
    "25.10.4": "336",
    "25.10.5": "111",
    "26.3.1": "410",
    "26.3.2": "426",
    "26.3.3": "392",
    "26.7.1": "554",
    "26.7.2": "519",
}

# Older releases predate nokia-eda/schema-profiles and still live in the
# srlinux-yang-models repository under a differently shaped tag.
LEGACY_SCHEMA_PROFILES = {
    "24.10.1": "v24.10.1/srlinux-24.10.1-492.zip",
    "24.10.2": "v24.10.2/srlinux-24.10.2-357.zip",
    "24.10.3": "v24.10.3/srlinux-24.10.3-201.zip",
    "25.3.1": "v25.3.1/srlinux-25.3.1-149.zip",
}


@pytest.mark.parametrize(("version", "build"), sorted(SCHEMA_PROFILE_BUILDS.items()))
def test_schema_profile_urls(version, build):
    url = NokiaSRLinuxNode.SUPPORTED_SCHEMA_PROFILES[version]
    assert url == (
        "https://github.com/nokia-eda/schema-profiles/"
        f"releases/download/nokia-srl-{version}/srlinux-{version}-{build}.zip"
    )


@pytest.mark.parametrize(("version", "suffix"), sorted(LEGACY_SCHEMA_PROFILES.items()))
def test_legacy_schema_profile_urls(version, suffix):
    assert NokiaSRLinuxNode.SUPPORTED_SCHEMA_PROFILES[version] == (
        f"https://github.com/nokia/srlinux-yang-models/releases/download/{suffix}"
    )


def test_no_unregistered_schema_profiles():
    """Every registered version is accounted for by one of the maps above."""
    assert set(NokiaSRLinuxNode.SUPPORTED_SCHEMA_PROFILES) == (
        set(SCHEMA_PROFILE_BUILDS) | set(LEGACY_SCHEMA_PROFILES)
    )


@pytest.mark.parametrize("version", sorted(NokiaSRLinuxNode.SUPPORTED_SCHEMA_PROFILES))
def test_artifact_info(version):
    node = NokiaSRLinuxNode(
        name="leaf1",
        kind="nokia_srlinux",
        node_type="ixr-d3l",
        version=version,
        mgmt_ipv4="172.20.20.2",
        mgmt_ipv4_prefix_length="24",
    )
    artifact_name, filename, download_url = node.get_artifact_info()

    assert artifact_name == f"clab-srlinux-{version}"
    assert filename == f"srlinux-{version}.zip"
    assert download_url == NokiaSRLinuxNode.SUPPORTED_SCHEMA_PROFILES[version]
