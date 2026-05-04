import urllib.error

from clab_connector.cli import versioning

TEST_TIMEOUT = 0.1


def test_parse_version_parts_accepts_release_tags():
    assert versioning.parse_version_parts("0.9.1") == (0, 9, 1)
    assert versioning.parse_version_parts("v0.9.1") == (0, 9, 1)
    assert versioning.parse_version_parts("v0.9.1-dev") == (0, 9, 1)
    assert versioning.parse_version_parts("latest") is None


def test_is_newer_version_normalizes_tag_prefix():
    assert versioning.is_newer_version("0.9.1", "v0.9.2")
    assert not versioning.is_newer_version("0.9.1", "v0.9.1")
    assert not versioning.is_newer_version("0.9.2", "v0.9.1")
    assert not versioning.is_newer_version("unknown", "v0.9.2")


def test_parse_release_tag_from_location():
    location = "https://github.com/eda-labs/clab-connector/releases/tag/v0.9.2"

    assert versioning.parse_release_tag_from_location(location) == "v0.9.2"
    assert (
        versioning.parse_release_tag_from_location(
            "/eda-labs/clab-connector/releases/tag/v1.0.0"
        )
        == "v1.0.0"
    )
    assert (
        versioning.parse_release_tag_from_location(
            "https://api.github.com/repos/eda-labs/clab-connector"
        )
        is None
    )


def test_fetch_latest_release_tag_uses_public_redirect_not_github_api(monkeypatch):
    seen = {}

    class FakeOpener:
        @staticmethod
        def open(request, timeout):  # noqa: ARG004
            seen["url"] = request.full_url
            headers = {
                "Location": "https://github.com/eda-labs/clab-connector/releases/tag/v0.9.2"
            }
            raise urllib.error.HTTPError(request.full_url, 302, "Found", headers, None)

    monkeypatch.delenv(versioning.VERSION_CHECK_ENV, raising=False)
    monkeypatch.setattr(versioning, "get_cli_version", lambda: "0.9.1")
    monkeypatch.setattr(
        versioning.urllib.request, "build_opener", lambda *_args: FakeOpener()
    )

    assert versioning.fetch_latest_release_tag(timeout=0.1) == "v0.9.2"
    assert seen["url"] == versioning.LATEST_RELEASE_URL
    assert "api.github.com" not in seen["url"]


def test_fetch_latest_release_tag_respects_disable_env(monkeypatch):
    monkeypatch.setenv(versioning.VERSION_CHECK_ENV, "disable")
    monkeypatch.setattr(
        versioning.urllib.request,
        "build_opener",
        lambda *_args: (_ for _ in ()).throw(AssertionError("network used")),
    )

    assert versioning.fetch_latest_release_tag(timeout=0.1) is None


def test_get_upgrade_notice_only_when_latest_is_newer(monkeypatch):
    def newer_release(timeout):
        assert timeout == TEST_TIMEOUT
        return "v0.9.2"

    def current_release(timeout):
        assert timeout == TEST_TIMEOUT
        return "v0.9.1"

    monkeypatch.setattr(versioning, "get_cli_version", lambda: "0.9.1")
    monkeypatch.setattr(versioning, "fetch_latest_release_tag", newer_release)

    assert versioning.get_upgrade_notice(timeout=TEST_TIMEOUT) == (
        "A newer clab-connector version (v0.9.2) is available. "
        "Upgrade with: uv tool upgrade clab-connector"
    )

    monkeypatch.setattr(versioning, "fetch_latest_release_tag", current_release)
    assert versioning.get_upgrade_notice(timeout=TEST_TIMEOUT) is None
