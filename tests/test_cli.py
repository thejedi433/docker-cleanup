"""Tests for the CLI interface."""

import pytest
import json
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from docker_cleanup.cli import main
from docker_cleanup.docker_client import DockerResource, DockerError


@pytest.fixture
def runner():
    return CliRunner()


def _make_image(id="abc123", name="test:latest", size=100_000_000):
    return DockerResource(id=id, name=name, size_bytes=size, created="")


def _make_container(id="ctr1", name="myctr", status="Exited (0)"):
    return DockerResource(id=id, name=name, created="", status=status)


def _make_volume(name="vol1"):
    return DockerResource(id=name, name=name, created="")


def _make_network(name="net1"):
    return DockerResource(id="netid1", name=name, created="")


class TestMainGroup:
    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Docker cleanup tool" in result.output

    def test_status_help(self, runner):
        result = runner.invoke(main, ["status", "--help"])
        assert result.exit_code == 0
        assert "reclaimable" in result.output.lower()

    def test_clean_help(self, runner):
        result = runner.invoke(main, ["clean", "--help"])
        assert result.exit_code == 0
        assert "Remove" in result.output

    def test_prune_help(self, runner):
        result = runner.invoke(main, ["prune", "--help"])
        assert result.exit_code == 0

    def test_prune_all_help(self, runner):
        result = runner.invoke(main, ["prune-all", "--help"])
        assert result.exit_code == 0


class TestStatusCommand:
    @patch("docker_cleanup.cli.DockerClient")
    def test_status_empty(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.list_dangling_images.return_value = []
        mock_client.list_stopped_containers.return_value = []
        mock_client.list_unused_volumes.return_value = []
        mock_client.list_unused_networks.return_value = []

        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "0" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_status_with_dangling(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.list_dangling_images.return_value = [
            _make_image(id="sha256:abcdef123456789", name="<none>:<none>", size=200_000_000)
        ]
        mock_client.list_stopped_containers.return_value = []
        mock_client.list_unused_volumes.return_value = []
        mock_client.list_unused_networks.return_value = []

        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "Dangling images" in result.output
        assert "200MB" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_status_with_all_flag(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.list_all_unused_images.return_value = [_make_image()]
        mock_client.list_stopped_containers.return_value = []
        mock_client.list_unused_volumes.return_value = []
        mock_client.list_unused_networks.return_value = []

        result = runner.invoke(main, ["status", "--all"])
        assert result.exit_code == 0
        assert "Unused images" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_status_docker_unavailable(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = False

        result = runner.invoke(main, ["status"])
        assert result.exit_code == 1
        assert "Cannot connect to Docker" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_status_with_containers_volumes_networks(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.list_dangling_images.return_value = []
        mock_client.list_stopped_containers.return_value = [_make_container()]
        mock_client.list_unused_volumes.return_value = [_make_volume()]
        mock_client.list_unused_networks.return_value = [_make_network()]

        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "Stopped containers" in result.output
        assert "Unused volumes" in result.output
        assert "Unused networks" in result.output


class TestCleanCommand:
    @patch("docker_cleanup.cli.DockerClient")
    def test_clean_empty_nothing_to_do(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.list_dangling_images.return_value = []
        mock_client.list_stopped_containers.return_value = []
        mock_client.list_unused_volumes.return_value = []
        mock_client.list_unused_networks.return_value = []
        mock_client.remove_images.return_value = (0, 0)
        mock_client.remove_containers.return_value = (0, 0)
        mock_client.remove_volumes.return_value = (0, 0)
        mock_client.remove_networks.return_value = (0, 0)

        result = runner.invoke(main, ["clean", "-f"])
        assert result.exit_code == 0
        assert "Cleanup complete" in result.output
        assert "0 removed" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_clean_with_resources_force(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.list_dangling_images.return_value = [_make_image()]
        mock_client.list_stopped_containers.return_value = [_make_container()]
        mock_client.list_unused_volumes.return_value = [_make_volume()]
        mock_client.list_unused_networks.return_value = [_make_network()]
        mock_client.remove_images.return_value = (1, 0)
        mock_client.remove_containers.return_value = (1, 0)
        mock_client.remove_volumes.return_value = (1, 0)
        mock_client.remove_networks.return_value = (1, 0)

        result = runner.invoke(main, ["clean", "-f"])
        assert result.exit_code == 0
        assert "Cleanup complete" in result.output
        assert "1 removed" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_clean_with_prompt_yes(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.list_dangling_images.return_value = [_make_image()]
        mock_client.list_stopped_containers.return_value = []
        mock_client.list_unused_volumes.return_value = []
        mock_client.list_unused_networks.return_value = []
        mock_client.remove_images.return_value = (1, 0)
        mock_client.remove_containers.return_value = (0, 0)
        mock_client.remove_volumes.return_value = (0, 0)
        mock_client.remove_networks.return_value = (0, 0)

        result = runner.invoke(main, ["clean"], input="y\n")
        assert result.exit_code == 0
        assert "1 removed, 0 failed" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_clean_with_prompt_no(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.list_dangling_images.return_value = [_make_image()]
        mock_client.list_stopped_containers.return_value = []
        mock_client.list_unused_volumes.return_value = []
        mock_client.list_unused_networks.return_value = []

        result = runner.invoke(main, ["clean"], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_clean_all_flag(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.list_all_unused_images.return_value = [_make_image(), _make_image(id="def", name="other:v1")]
        mock_client.list_stopped_containers.return_value = []
        mock_client.list_unused_volumes.return_value = []
        mock_client.list_unused_networks.return_value = []
        mock_client.remove_images.return_value = (2, 0)
        mock_client.remove_containers.return_value = (0, 0)
        mock_client.remove_volumes.return_value = (0, 0)
        mock_client.remove_networks.return_value = (0, 0)

        result = runner.invoke(main, ["clean", "--all", "-f"])
        assert result.exit_code == 0
        assert "2 removed" in result.output
        assert "unused images" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_clean_docker_unavailable(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = False

        result = runner.invoke(main, ["clean"])
        assert result.exit_code == 1

    @patch("docker_cleanup.cli.DockerClient")
    def test_clean_with_failures(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.list_dangling_images.return_value = [_make_image()]
        mock_client.list_stopped_containers.return_value = []
        mock_client.list_unused_volumes.return_value = []
        mock_client.list_unused_networks.return_value = []
        mock_client.remove_images.return_value = (0, 1)
        mock_client.remove_containers.return_value = (0, 0)
        mock_client.remove_volumes.return_value = (0, 0)
        mock_client.remove_networks.return_value = (0, 0)

        result = runner.invoke(main, ["clean", "-f"])
        assert result.exit_code == 0
        assert "0 removed, 1 failed" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_clean_list_error(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.list_dangling_images.side_effect = DockerError("docker error")

        result = runner.invoke(main, ["clean"])
        assert result.exit_code == 1
        assert "Error" in result.output
        assert "docker error" in result.output


class TestPruneCommand:
    @patch("docker_cleanup.cli.DockerClient")
    def test_prune_force(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.prune_all.return_value = {"success": True, "output": "Deleted: abc"}

        result = runner.invoke(main, ["prune", "-f"])
        assert result.exit_code == 0
        assert "Deleted: abc" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_prune_confirm_yes(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.prune_all.return_value = {"success": True, "output": "done"}

        result = runner.invoke(main, ["prune"], input="y\n")
        assert result.exit_code == 0
        assert "done" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_prune_confirm_no(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True

        result = runner.invoke(main, ["prune"], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_prune_failure(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.prune_all.return_value = {"success": False, "error": "something broke"}

        result = runner.invoke(main, ["prune", "-f"])
        assert result.exit_code == 1
        assert "something broke" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_prune_docker_unavailable(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = False

        result = runner.invoke(main, ["prune"])
        assert result.exit_code == 1


class TestPruneAllCommand:
    @patch("docker_cleanup.cli.DockerClient")
    def test_prune_all_force(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.prune_all.return_value = {"success": True, "output": "all pruned"}

        result = runner.invoke(main, ["prune-all", "-f"])
        assert result.exit_code == 0
        assert "all pruned" in result.output
        mock_client.prune_all.assert_called_with(all=True)

    @patch("docker_cleanup.cli.DockerClient")
    def test_prune_all_confirm_yes(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.prune_all.return_value = {"success": True, "output": "done"}

        result = runner.invoke(main, ["prune-all"], input="y\n")
        assert result.exit_code == 0

    @patch("docker_cleanup.cli.DockerClient")
    def test_prune_all_confirm_no(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True

        result = runner.invoke(main, ["prune-all"], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_prune_all_warning_message(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.prune_all.return_value = {"success": True, "output": "done"}

        result = runner.invoke(main, ["prune-all", "-f"])
        assert "WARNING" in result.output
        assert "ALL unused images" in result.output

    @patch("docker_cleanup.cli.DockerClient")
    def test_prune_all_failure(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.prune_all.return_value = {"success": False, "error": "fail"}

        result = runner.invoke(main, ["prune-all", "-f"])
        assert result.exit_code == 1


class TestDockerBinOption:
    @patch("docker_cleanup.cli.DockerClient")
    def test_custom_docker_bin(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.list_dangling_images.return_value = []
        mock_client.list_stopped_containers.return_value = []
        mock_client.list_unused_volumes.return_value = []
        mock_client.list_unused_networks.return_value = []

        result = runner.invoke(main, ["--docker-bin", "/usr/local/bin/docker", "status"])
        assert result.exit_code == 0
        MockClient.assert_called_with(docker_bin="/usr/local/bin/docker")

    @patch("docker_cleanup.cli.DockerClient")
    def test_status_list_error(self, MockClient, runner):
        mock_client = MockClient.return_value
        mock_client.available = True
        mock_client.list_dangling_images.side_effect = DockerError("docker error")

        result = runner.invoke(main, ["status"])
        assert result.exit_code == 1
        assert "Error" in result.output
        assert "docker error" in result.output
