import logging

import pytest

from clab_connector.clients.eda.client import (
    MAX_TESTED_EDA_VERSION,
    MIN_SUPPORTED_EDA_VERSION,
    EDAClient,
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
    assert make_client(version).get_version_parts() == expected


def test_supported_range_covers_26_4_through_26_8():
    assert MIN_SUPPORTED_EDA_VERSION == (26, 4)
    assert MAX_TESTED_EDA_VERSION == (26, 8)


@pytest.mark.parametrize("version", ["26.4.1", "26.8.1"])
def test_no_warning_for_supported_versions(version, caplog):
    client = make_client(version)
    with caplog.at_level(logging.WARNING):
        client._warn_on_unsupported_version()
    assert caplog.records == []


def test_warns_below_minimum_supported_version(caplog):
    client = make_client("25.12.1")
    with caplog.at_level(logging.WARNING):
        client._warn_on_unsupported_version()
    assert "older than the minimum supported release" in caplog.text
    assert "0.8.11" in caplog.text


def test_warns_above_last_tested_version(caplog):
    client = make_client("27.4.1")
    with caplog.at_level(logging.WARNING):
        client._warn_on_unsupported_version()
    assert "newer than the latest tested release" in caplog.text


@pytest.mark.parametrize(
    ("version", "build"),
    [("26.7.1", "554"), ("26.7.2", "519")],
)
def test_srl_26_7_schema_profiles_are_registered(version, build):
    url = NokiaSRLinuxNode.SUPPORTED_SCHEMA_PROFILES[version]
    assert url == (
        "https://github.com/nokia-eda/schema-profiles/"
        f"releases/download/nokia-srl-{version}/srlinux-{version}-{build}.zip"
    )


@pytest.mark.parametrize("version", ["26.7.1", "26.7.2"])
def test_srl_26_7_artifact_info(version):
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
