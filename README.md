# docker-cleanup

A CLI tool to clean up unused Docker resources (dangling images, stopped containers, unused volumes and networks).

## Features

- **Status Report**: View all unused Docker resources with sizes
- **Selective Cleanup**: Remove specific resource types (images, containers, volumes, networks)
- **Prune Operations**: Use Docker's native prune commands
- **Safe by Default**: Interactive confirmation before destructive operations
- **Flexible Filtering**: Option to target all unused resources or just dangling ones

## Installation

```bash
pip install docker-cleanup
```

Or install from source:

```bash
git clone https://github.com/thejedi433/docker-cleanup.git
cd docker-cleanup
uv venv
source .venv/bin/activate
uv pip install -e .
```

## Usage

### Check status of unused Docker resources

```bash
docker-cleanup status
```

Show all unused resources (not just dangling):
```bash
docker-cleanup status --all
```

### Clean up resources

Remove dangling images, stopped containers, unused volumes and networks:
```bash
docker-cleanup clean
```

Remove all unused resources (not just dangling):
```bash
docker-cleanup clean --all
```

Force cleanup without confirmation:
```bash
docker-cleanup clean -f
```

### Prune operations

Use Docker's native prune commands:
```bash
docker-cleanup prune
```

Prune all unused resources (equivalent to `docker system prune -a`):
```bash
docker-cleanup prune-all
```

### Custom Docker binary

If Docker is not in the default path:
```bash
docker-cleanup --docker-bin /usr/local/bin/docker status
```

## Requirements

- Python 3.11+
- Docker installed and accessible

## Development

### Setup

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Run tests

```bash
pytest
```

### Run tests with coverage

```bash
pytest --cov=docker_cleanup --cov-report=term-missing
```

## License

MIT
