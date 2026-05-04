from typer.testing import CliRunner

from clab_connector.cli import main

runner = CliRunner()


def test_version_command_short(monkeypatch):
    monkeypatch.setattr(main, "get_cli_version", lambda: "1.2.3")

    result = runner.invoke(main.app, ["version", "--short"])

    assert result.exit_code == 0
    assert result.output == "1.2.3\n"


def test_version_check_reports_newer_version(monkeypatch):
    def fake_fetch_latest_release_tag(timeout):
        assert timeout == main.EXPLICIT_VERSION_CHECK_TIMEOUT
        return "v1.2.4"

    monkeypatch.setattr(main, "get_cli_version", lambda: "1.2.3")
    monkeypatch.setattr(main, "fetch_latest_release_tag", fake_fetch_latest_release_tag)

    result = runner.invoke(main.app, ["version", "check"])

    assert result.exit_code == 0
    assert "A newer clab-connector version (v1.2.4) is available" in result.output
    assert "uv tool upgrade clab-connector" in result.output


def test_command_lifecycle_prints_version_and_upgrade_notice(monkeypatch, tmp_path):
    topology_data = tmp_path / "topology-data.json"
    topology_data.write_text("{}", encoding="utf-8")

    class FakeManifestGenerator:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def generate():
            pass

        @staticmethod
        def output_manifests():
            pass

    def fake_upgrade_notice(timeout=0):
        assert timeout == main.AUTO_VERSION_CHECK_TIMEOUT
        return "A newer clab-connector version (v1.2.4) is available."

    monkeypatch.setattr(main, "ManifestGenerator", FakeManifestGenerator)
    monkeypatch.setattr(main, "get_cli_version", lambda: "1.2.3")
    monkeypatch.setattr(main, "get_upgrade_notice", fake_upgrade_notice)

    result = runner.invoke(main.app, ["generate-crs", "-t", str(topology_data)])

    assert result.exit_code == 0
    assert "clab-connector version: 1.2.3" in result.output
    assert "A newer clab-connector version (v1.2.4) is available." in result.output
