"""Tests for the Docker client wrapper."""

import pytest
import subprocess
import json
from unittest.mock import patch, MagicMock

from docker_cleanup.docker_client import (
    DockerClient,
    DockerResource,
    DockerError,
    parse_size,
)


# ── parse_size tests ─────────────────────────────────────────────────────


class TestParseSize:
    def test_bytes(self):
        assert parse_size("123B") == 123

    def test_kilobytes(self):
        assert parse_size("100kB") == 100_000

    def test_megabytes(self):
        assert parse_size("50MB") == 50_000_000

    def test_gigabytes(self):
        assert parse_size("1.5GB") == 1_500_000_000

    def test_terabytes(self):
        assert parse_size("2TB") == 2_000_000_000_000

    def test_virtual_size(self):
        assert parse_size("100MB (virtual 200MB)") == 100_000_000

    def test_empty_string(self):
        assert parse_size("") == 0

    def test_plain_number(self):
        assert parse_size("12345") == 12345

    def test_invalid_string(self):
        assert parse_size("abcXYZ") == 0

    def test_invalid_number(self):
        assert parse_size("abcMB") == 0

    def test_whitespace(self):
        assert parse_size("  50MB  ") == 50_000_000

    def test_decimal(self):
        assert parse_size("1.5MB") == 1_500_000


# ── DockerClient tests ──────────────────────────────────────────────────


class TestDockerClient:
    def setup_method(self):
        self.client = DockerClient(docker_bin="/usr/bin/docker")

    def test_init(self):
        assert self.client.docker_bin == "/usr/bin/docker"

    def test_init_default(self):
        client = DockerClient()
        assert client.docker_bin == "docker"

    @patch("subprocess.run")
    def test_run_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="output", stderr=""
        )
        result = self.client._run(["ps"])
        assert result == "output"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_run_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error message"
        )
        with pytest.raises(DockerError, match="docker command failed"):
            self.client._run(["bad"])

    @patch("subprocess.run")
    def test_run_failure_no_check(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="output", stderr="err"
        )
        result = self.client._run(["cmd"], check=False)
        assert result == "output"

    @patch("subprocess.run")
    def test_run_docker_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        with pytest.raises(DockerError, match="docker binary not found"):
            self.client._run(["ps"])

    @patch("subprocess.run")
    def test_run_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=30)
        with pytest.raises(DockerError, match="timed out"):
            self.client._run(["ps"])

    @patch("subprocess.run")
    def test_available_true(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        assert self.client.available is True

    @patch("subprocess.run")
    def test_available_false(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        assert self.client.available is False


# ── Image listing tests ─────────────────────────────────────────────────


class TestListDanglingImages:
    def setup_method(self):
        self.client = DockerClient()

    @patch("subprocess.run")
    def test_list_dangling_images(self, mock_run):
        img_data = {
            "Containers": "N/A",
            "CreatedAt": "2024-01-01",
            "CreatedSince": "10 days ago",
            "Digest": "<none>",
            "ID": "sha256:abc123def456",
            "Repository": "<none>",
            "SharedSize": "N/A",
            "Size": "100MB",
            "Tag": "<none>",
            "UniqueSize": "N/A",
            "VirtualSize": "100MB",
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(img_data) + "\n",
            stderr="",
        )
        images = self.client.list_dangling_images()
        assert len(images) == 1
        assert images[0].id == "sha256:abc123def456"
        assert images[0].name == "<none>:<none>"
        assert images[0].size_bytes == 100_000_000

    @patch("subprocess.run")
    def test_list_dangling_images_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        images = self.client.list_dangling_images()
        assert images == []

    @patch("subprocess.run")
    def test_list_dangling_images_multiple(self, mock_run):
        img1 = {"ID": "aaa", "Repository": "<none>", "Tag": "<none>", "Size": "50MB", "CreatedAt": ""}
        img2 = {"ID": "bbb", "Repository": "<none>", "Tag": "<none>", "Size": "75MB", "CreatedAt": ""}
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(img1) + "\n" + json.dumps(img2) + "\n",
            stderr="",
        )
        images = self.client.list_dangling_images()
        assert len(images) == 2

    @patch("subprocess.run")
    def test_list_dangling_images_with_filter(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        self.client.list_dangling_images()
        call_args = mock_run.call_args[0][0]
        assert "--filter" in call_args
        assert "dangling=true" in call_args


class TestListAllUnusedImages:
    def setup_method(self):
        self.client = DockerClient()

    @patch("subprocess.run")
    def test_list_all_unused_images_no_containers(self, mock_run):
        # First call: docker ps -a (no containers)
        # Second call: docker images (all images are unused)
        img_data = {"ID": "img1", "Repository": "nginx", "Tag": "latest", "Size": "100MB", "CreatedAt": ""}
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # ps -a
            MagicMock(returncode=0, stdout=json.dumps(img_data) + "\n", stderr=""),  # images
        ]
        images = self.client.list_all_unused_images()
        assert len(images) == 1
        assert images[0].name == "nginx:latest"

    @patch("subprocess.run")
    def test_list_all_unused_images_filters_used(self, mock_run):
        img_used = {"ID": "img1", "Repository": "nginx", "Tag": "latest", "Size": "100MB", "CreatedAt": ""}
        img_unused = {"ID": "img2", "Repository": "redis", "Tag": "7", "Size": "50MB", "CreatedAt": ""}
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="nginx:latest\n", stderr=""),  # ps -a shows nginx used
            MagicMock(
                returncode=0,
                stdout=json.dumps(img_used) + "\n" + json.dumps(img_unused) + "\n",
                stderr="",
            ),
        ]
        images = self.client.list_all_unused_images()
        assert len(images) == 1
        assert images[0].name == "redis:7"

    @patch("subprocess.run")
    def test_list_all_unused_images_ps_failure(self, mock_run):
        """When docker ps fails, we still list all images."""
        img_data = {"ID": "img1", "Repository": "nginx", "Tag": "latest", "Size": "100MB", "CreatedAt": ""}
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="error"),  # ps -a fails
            MagicMock(returncode=0, stdout=json.dumps(img_data) + "\n", stderr=""),
        ]
        images = self.client.list_all_unused_images()
        assert len(images) == 1

    @patch("subprocess.run")
    def test_list_all_unused_images_ps_docker_error(self, mock_run):
        """When docker ps raises DockerError (binary missing), we still list all images."""
        img_data = {"ID": "img1", "Repository": "nginx", "Tag": "latest", "Size": "100MB", "CreatedAt": ""}
        mock_run.side_effect = [
            FileNotFoundError,  # ps -a raises DockerError via _run
            MagicMock(returncode=0, stdout=json.dumps(img_data) + "\n", stderr=""),
        ]
        images = self.client.list_all_unused_images()
        assert len(images) == 1

    @patch("subprocess.run")
    def test_list_all_unused_images_with_blank_line(self, mock_run):
        """Output with blank lines between entries is handled correctly."""
        img1 = {"ID": "img1", "Repository": "nginx", "Tag": "latest", "Size": "100MB", "CreatedAt": ""}
        img2 = {"ID": "img2", "Repository": "redis", "Tag": "7", "Size": "50MB", "CreatedAt": ""}
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="\n", stderr=""),  # ps -a with blank line only
            MagicMock(returncode=0, stdout=json.dumps(img1) + "\n\n" + json.dumps(img2) + "\n", stderr=""),
        ]
        images = self.client.list_all_unused_images()
        assert len(images) == 2

    @patch("subprocess.run")
    def test_list_all_unused_images_ps_with_blank_line(self, mock_run):
        """ps output with blank line in middle is handled correctly."""
        img_data = {"ID": "img1", "Repository": "nginx", "Tag": "latest", "Size": "100MB", "CreatedAt": ""}
        mock_run.side_effect = [
            # ps -a output with blank line in middle (used image)
            MagicMock(returncode=0, stdout="nginx:latest\n\nnginx:latest\n", stderr=""),
            MagicMock(returncode=0, stdout=json.dumps(img_data) + "\n", stderr=""),
        ]
        images = self.client.list_all_unused_images()
        # The image is used by a container, so should be filtered out
        assert len(images) == 0


# ── Container listing tests ─────────────────────────────────────────────


class TestListStoppedContainers:
    def setup_method(self):
        self.client = DockerClient()

    @patch("subprocess.run")
    def test_list_stopped_containers(self, mock_run):
        ctr = {
            "Command": "\"echo hello\"",
            "CreatedAt": "2024-01-01",
            "ID": "abc123",
            "Image": "alpine",
            "Labels": "",
            "LocalVolumes": "0",
            "Mounts": "",
            "Names": "my_container",
            "Networks": "bridge",
            "Ports": "",
            "RunningFor": "10 days ago",
            "Size": "0B",
            "State": "exited",
            "Status": "Exited (0) 10 days ago",
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(ctr) + "\n",
            stderr="",
        )
        containers = self.client.list_stopped_containers()
        assert len(containers) == 1
        assert containers[0].id == "abc123"
        assert containers[0].name == "my_container"
        assert containers[0].status == "Exited (0) 10 days ago"

    @patch("subprocess.run")
    def test_list_stopped_containers_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        containers = self.client.list_stopped_containers()
        assert containers == []

    @patch("subprocess.run")
    def test_list_stopped_containers_multiple(self, mock_run):
        c1 = {"ID": "aaa", "Names": "c1", "CreatedAt": "", "Status": "Exited (0)"}
        c2 = {"ID": "bbb", "Names": "c2", "CreatedAt": "", "Status": "Exited (1)"}
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(c1) + "\n" + json.dumps(c2) + "\n",
            stderr="",
        )
        containers = self.client.list_stopped_containers()
        assert len(containers) == 2

    @patch("subprocess.run")
    def test_list_stopped_containers_with_blank_line(self, mock_run):
        """Output with blank lines between entries is handled correctly."""
        c1 = {"ID": "abc123", "Names": "myctr", "CreatedAt": "", "Status": "Exited (0)"}
        c2 = {"ID": "def456", "Names": "other", "CreatedAt": "", "Status": "Exited (1)"}
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(c1) + "\n\n" + json.dumps(c2) + "\n",
            stderr="",
        )
        containers = self.client.list_stopped_containers()
        assert len(containers) == 2


# ── Volume listing tests ────────────────────────────────────────────────


class TestListUnusedVolumes:
    def setup_method(self):
        self.client = DockerClient()

    @patch("subprocess.run")
    def test_list_unused_volumes(self, mock_run):
        vol = {"Driver": "local", "Name": "my_volume", "Mountpoint": "/var/lib/...", "CreatedAt": ""}
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(vol) + "\n",
            stderr="",
        )
        volumes = self.client.list_unused_volumes()
        assert len(volumes) == 1
        assert volumes[0].name == "my_volume"
        assert volumes[0].id == "my_volume"

    @patch("subprocess.run")
    def test_list_unused_volumes_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        volumes = self.client.list_unused_volumes()
        assert volumes == []

    @patch("subprocess.run")
    def test_list_unused_volumes_with_blank_line(self, mock_run):
        """Output with blank lines between entries is handled correctly."""
        v1 = {"Name": "vol1", "CreatedAt": ""}
        v2 = {"Name": "vol2", "CreatedAt": ""}
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(v1) + "\n\n" + json.dumps(v2) + "\n",
            stderr="",
        )
        volumes = self.client.list_unused_volumes()
        assert len(volumes) == 2


# ── Network listing tests ───────────────────────────────────────────────


class TestListUnusedNetworks:
    def setup_method(self):
        self.client = DockerClient()

    @patch("subprocess.run")
    def test_list_unused_networks(self, mock_run):
        net = {"ID": "net123", "Name": "mynet", "Driver": "bridge", "CreatedAt": "", "IPv6": "false", "Internal": "false", "Labels": ""}
        # First call: network ls, second: ps -q --filter network=mynet (empty = unused)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps(net) + "\n", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        networks = self.client.list_unused_networks()
        assert len(networks) == 1
        assert networks[0].name == "mynet"

    @patch("subprocess.run")
    def test_list_unused_networks_skips_used(self, mock_run):
        net = {"ID": "net123", "Name": "mynet", "Driver": "bridge", "CreatedAt": "", "IPv6": "false", "Internal": "false", "Labels": ""}
        # Network has a container attached
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps(net) + "\n", stderr=""),
            MagicMock(returncode=0, stdout="container123\n", stderr=""),
        ]
        networks = self.client.list_unused_networks()
        assert len(networks) == 0

    @patch("subprocess.run")
    def test_list_unused_networks_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        networks = self.client.list_unused_networks()
        assert networks == []

    @patch("subprocess.run")
    def test_list_unused_networks_ps_failure(self, mock_run):
        """When ps fails for a network, it's treated as unused (no containers)."""
        net = {"ID": "net123", "Name": "mynet", "Driver": "bridge", "CreatedAt": "", "IPv6": "false", "Internal": "false", "Labels": ""}
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps(net) + "\n", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="error"),
        ]
        networks = self.client.list_unused_networks()
        assert len(networks) == 1

    @patch("subprocess.run")
    def test_list_unused_networks_with_blank_line(self, mock_run):
        """Output with blank lines between entries is handled correctly."""
        n1 = {"ID": "net1", "Name": "mynet1", "Driver": "bridge", "CreatedAt": "", "IPv6": "false", "Internal": "false", "Labels": ""}
        n2 = {"ID": "net2", "Name": "mynet2", "Driver": "bridge", "CreatedAt": "", "IPv6": "false", "Internal": "false", "Labels": ""}
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps(n1) + "\n\n" + json.dumps(n2) + "\n", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),  # ps -q for net1
            MagicMock(returncode=0, stdout="", stderr=""),  # ps -q for net2
        ]
        networks = self.client.list_unused_networks()
        assert len(networks) == 2

    @patch("subprocess.run")
    def test_list_unused_networks_ps_docker_error(self, mock_run):
        """When ps raises DockerError (binary missing), network is treated as unused."""
        net = {"ID": "net123", "Name": "mynet", "Driver": "bridge", "CreatedAt": "", "IPv6": "false", "Internal": "false", "Labels": ""}
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps(net) + "\n", stderr=""),
            FileNotFoundError,  # second call raises DockerError
        ]
        networks = self.client.list_unused_networks()
        assert len(networks) == 1


# ── Remove operations tests ─────────────────────────────────────────────


class TestRemoveOperations:
    def setup_method(self):
        self.client = DockerClient()

    @patch("subprocess.run")
    def test_remove_images_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        removed, failed = self.client.remove_images(["img1", "img2"])
        assert removed == 2
        assert failed == 0
        assert mock_run.call_count == 2

    @patch("subprocess.run")
    def test_remove_images_partial_failure(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="error"),
        ]
        removed, failed = self.client.remove_images(["img1", "img2"])
        assert removed == 1
        assert failed == 1

    @patch("subprocess.run")
    def test_remove_images_empty(self, mock_run):
        removed, failed = self.client.remove_images([])
        assert removed == 0
        assert failed == 0
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_remove_containers_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        removed, failed = self.client.remove_containers(["c1"])
        assert removed == 1
        assert failed == 0

    @patch("subprocess.run")
    def test_remove_containers_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="err")
        removed, failed = self.client.remove_containers(["c1"])
        assert removed == 0
        assert failed == 1

    @patch("subprocess.run")
    def test_remove_containers_empty(self, mock_run):
        removed, failed = self.client.remove_containers([])
        assert removed == 0
        assert failed == 0
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_remove_volumes_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        removed, failed = self.client.remove_volumes(["vol1"])
        assert removed == 1
        assert failed == 0

    @patch("subprocess.run")
    def test_remove_volumes_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="err")
        removed, failed = self.client.remove_volumes(["vol1"])
        assert removed == 0
        assert failed == 1

    @patch("subprocess.run")
    def test_remove_volumes_empty(self, mock_run):
        removed, failed = self.client.remove_volumes([])
        assert removed == 0
        assert failed == 0
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_remove_networks_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        removed, failed = self.client.remove_networks(["net1"])
        assert removed == 1
        assert failed == 0

    @patch("subprocess.run")
    def test_remove_networks_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="err")
        removed, failed = self.client.remove_networks(["net1"])
        assert removed == 0
        assert failed == 1

    @patch("subprocess.run")
    def test_remove_networks_empty(self, mock_run):
        removed, failed = self.client.remove_networks([])
        assert removed == 0
        assert failed == 0
        mock_run.assert_not_called()


# ── Prune tests ─────────────────────────────────────────────────────────


class TestPrune:
    def setup_method(self):
        self.client = DockerClient()

    @patch("subprocess.run")
    def test_prune_all_basic(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Deleted Containers:\nabc\nDeleted Images:\ndef\n", stderr=""
        )
        result = self.client.prune_all()
        assert result["success"] is True
        assert "output" in result
        call_args = mock_run.call_args[0][0]
        assert "-f" in call_args
        assert "-a" not in call_args

    @patch("subprocess.run")
    def test_prune_all_flag(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="done", stderr="")
        result = self.client.prune_all(all=True)
        assert result["success"] is True
        call_args = mock_run.call_args[0][0]
        assert "-a" in call_args

    @patch("subprocess.run")
    def test_prune_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = self.client.prune_all()
        assert result["success"] is False
        assert "error" in result


# ── DockerResource tests ────────────────────────────────────────────────


class TestDockerResource:
    def test_defaults(self):
        r = DockerResource(id="abc", name="test")
        assert r.size_bytes == 0
        assert r.created == ""
        assert r.status == ""
        assert r.labels == {}

    def test_full(self):
        r = DockerResource(id="abc", name="test", size_bytes=100, created="now", status="ok")
        assert r.id == "abc"
        assert r.name == "test"
        assert r.size_bytes == 100
        assert r.created == "now"
        assert r.status == "ok"

    def test_labels_default_factory(self):
        r1 = DockerResource(id="a", name="x")
        r2 = DockerResource(id="b", name="y")
        r1.labels["key"] = "val"
        assert "key" not in r2.labels


class TestDockerError:
    def test_error_message(self):
        err = DockerError("something went wrong")
        assert str(err) == "something went wrong"
        assert isinstance(err, Exception)
