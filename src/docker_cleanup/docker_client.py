"""Docker CLI wrapper for cleanup operations."""

import subprocess
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DockerResource:
    """Represents a Docker resource (image, container, volume, network)."""
    id: str
    name: str
    size_bytes: int = 0
    created: str = ""
    status: str = ""
    labels: dict = field(default_factory=dict)


class DockerError(Exception):
    """Raised when a Docker command fails."""
    pass


class DockerClient:
    """Wrapper around docker CLI for cleanup operations."""

    def __init__(self, docker_bin: str = "docker"):
        self.docker_bin = docker_bin

    def _run(self, args: list[str], check: bool = True) -> str:
        """Run a docker command and return stdout."""
        cmd = [self.docker_bin] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            raise DockerError(f"docker binary not found: {self.docker_bin}")
        except subprocess.TimeoutExpired:
            raise DockerError(f"docker command timed out: {' '.join(cmd)}")

        if check and result.returncode != 0:
            raise DockerError(
                f"docker command failed: {' '.join(cmd)}\n"
                f"stderr: {result.stderr.strip()}"
            )
        return result.stdout

    def _is_available(self) -> bool:
        """Check if docker daemon is reachable."""
        try:
            self._run(["info"], check=True)
            return True
        except DockerError:
            return False

    @property
    def available(self) -> bool:
        return self._is_available()

    # ── Images ────────────────────────────────────────────────────────

    def list_dangling_images(self) -> list[DockerResource]:
        """List dangling (unreferenced) images."""
        return self._list_images(filter="dangling=true")

    def list_all_unused_images(self) -> list[DockerResource]:
        """List all images not used by any container."""
        # Get all image IDs used by containers
        used = set()
        try:
            output = self._run(
                ["ps", "-a", "--format", "{{.Image}}"],
                check=False,
            )
            for line in output.strip().splitlines():
                line = line.strip()
                if line:
                    used.add(line)
        except DockerError:
            pass

        all_images = self._list_images(filter="")
        if not used:
            return all_images
        return [img for img in all_images if img.name not in used and img.id not in used]

    def _list_images(self, filter: str) -> list[DockerResource]:
        """List images with optional filter."""
        args = [
            "images",
            "--format", "{{json .}}",
        ]
        if filter:
            args.extend(["--filter", filter])

        output = self._run(args)
        resources = []
        for line in output.strip().splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            # Parse size - docker outputs e.g. "123MB", "1.2GB"
            size_bytes = parse_size(data.get("Size", "0B"))
            resources.append(DockerResource(
                id=data.get("ID", ""),
                name=data.get("Repository", "<none>") + ":" + data.get("Tag", "<none>"),
                size_bytes=size_bytes,
                created=data.get("CreatedAt", ""),
            ))
        return resources

    def remove_images(self, image_ids: list[str]) -> tuple[int, int]:
        """Remove images by ID. Returns (removed_count, failed_count)."""
        if not image_ids:
            return 0, 0
        removed = 0
        failed = 0
        for img_id in image_ids:
            try:
                self._run(["image", "rm", "-f", img_id])
                removed += 1
            except DockerError:
                failed += 1
        return removed, failed

    # ── Containers ────────────────────────────────────────────────────

    def list_stopped_containers(self) -> list[DockerResource]:
        """List stopped containers."""
        output = self._run(
            ["ps", "-a", "--filter", "status=exited", "--format", "{{json .}}"],
        )
        resources = []
        for line in output.strip().splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            resources.append(DockerResource(
                id=data.get("ID", ""),
                name=data.get("Names", ""),
                size_bytes=0,
                created=data.get("CreatedAt", ""),
                status=data.get("Status", ""),
            ))
        return resources

    def remove_containers(self, container_ids: list[str]) -> tuple[int, int]:
        """Remove containers by ID. Returns (removed_count, failed_count)."""
        if not container_ids:
            return 0, 0
        removed = 0
        failed = 0
        for cid in container_ids:
            try:
                self._run(["container", "rm", "-f", cid])
                removed += 1
            except DockerError:
                failed += 1
        return removed, failed

    # ── Volumes ───────────────────────────────────────────────────────

    def list_unused_volumes(self) -> list[DockerResource]:
        """List volumes not used by any container."""
        output = self._run(
            ["volume", "ls", "--filter", "dangling=true", "--format", "{{json .}}"],
        )
        resources = []
        for line in output.strip().splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            resources.append(DockerResource(
                id=data.get("Name", ""),
                name=data.get("Name", ""),
                size_bytes=0,  # docker volume ls doesn't report size by default
                created=data.get("CreatedAt", ""),
            ))
        return resources

    def remove_volumes(self, volume_names: list[str]) -> tuple[int, int]:
        """Remove volumes by name. Returns (removed_count, failed_count)."""
        if not volume_names:
            return 0, 0
        removed = 0
        failed = 0
        for name in volume_names:
            try:
                self._run(["volume", "rm", name])
                removed += 1
            except DockerError:
                failed += 1
        return removed, failed

    # ── Networks ──────────────────────────────────────────────────────

    def list_unused_networks(self) -> list[DockerResource]:
        """List networks not used by any container."""
        output = self._run(
            ["network", "ls", "--filter", "type=custom", "--format", "{{json .}}"],
        )
        # Filter to networks with no attached containers
        resources = []
        for line in output.strip().splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            name = data.get("Name", "")
            # Check if any container is using this network
            try:
                ps_output = self._run(
                    ["ps", "-q", "--filter", f"network={name}"],
                    check=False,
                )
                if ps_output.strip():
                    continue  # network is in use
            except DockerError:
                pass
            resources.append(DockerResource(
                id=data.get("ID", ""),
                name=name,
                created=data.get("CreatedAt", ""),
            ))
        return resources

    def remove_networks(self, network_ids: list[str]) -> tuple[int, int]:
        """Remove networks by ID/name. Returns (removed_count, failed_count)."""
        if not network_ids:
            return 0, 0
        removed = 0
        failed = 0
        for nid in network_ids:
            try:
                self._run(["network", "rm", nid])
                removed += 1
            except DockerError:
                failed += 1
        return removed, failed

    # ── Bulk cleanup ──────────────────────────────────────────────────

    def prune_all(self, all: bool = False) -> dict:
        """Run docker system prune. Returns summary dict."""
        args = ["system", "prune", "-f"]
        if all:
            args.append("-a")
        try:
            output = self._run(args)
            return {"output": output.strip(), "success": True}
        except DockerError as e:
            return {"error": str(e), "success": False}


def parse_size(size_str: str) -> int:
    """Parse a Docker size string (e.g. '123MB', '1.2GB') into bytes."""
    size_str = size_str.strip().upper()
    if not size_str:
        return 0

    # Docker format: "123B", "123kB", "123MB", "123GB", "123TB"
    # or virtual size format: "123MB (virtual 456MB)"
    if "(" in size_str:
        size_str = size_str.split("(")[0].strip()

    units = {
        "B": 1,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
    }

    for suffix, multiplier in sorted(units.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(suffix):
            try:
                num = float(size_str[: -len(suffix)])
                return int(num * multiplier)
            except ValueError:
                return 0

    # Try plain number (bytes)
    try:
        return int(float(size_str))
    except ValueError:
        return 0
