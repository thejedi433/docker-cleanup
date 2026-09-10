"""CLI interface for docker-cleanup."""

import click
import sys

from .docker_client import DockerClient, DockerError
from .formatter import format_size, format_table


@click.group()
@click.option("--docker-bin", default="docker", help="Path to docker binary")
@click.pass_context
def main(ctx, docker_bin):
    """Docker cleanup tool - remove unused resources and reclaim disk space."""
    ctx.ensure_object(dict)
    ctx.obj["client"] = DockerClient(docker_bin=docker_bin)


@main.command()
@click.option("--all", is_flag=True, help="Show all unused images, not just dangling")
@click.pass_context
def status(ctx, all):
    """Show summary of reclaimable resources."""
    client: DockerClient = ctx.obj["client"]
    _check_docker(client)

    try:
        images = client.list_dangling_images() if not all else client.list_all_unused_images()
        containers = client.list_stopped_containers()
        volumes = client.list_unused_volumes()
        networks = client.list_unused_networks()
    except DockerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    image_size = sum(img.size_bytes for img in images)
    container_count = len(containers)
    volume_count = len(volumes)
    network_count = len(networks)

    click.echo("Docker Cleanup Status")
    click.echo("=" * 40)
    click.echo()

    if all:
        click.echo(f"Unused images:  {len(images)} ({format_size(image_size)})")
    else:
        click.echo(f"Dangling images: {len(images)} ({format_size(image_size)})")
    click.echo(f"Stopped containers: {container_count}")
    click.echo(f"Unused volumes:  {volume_count}")
    click.echo(f"Unused networks:  {network_count}")
    click.echo()

    # Show details if there's something to clean
    if images:
        label = "Unused images" if all else "Dangling images"
        click.echo(f"{label}:")
        rows = []
        for img in images:
            rows.append([img.id[:12], img.name, format_size(img.size_bytes)])
        click.echo(format_table(["ID", "NAME", "SIZE"], rows))
        click.echo()

    if containers:
        click.echo("Stopped containers:")
        rows = [[c.id[:12], c.name, c.status] for c in containers]
        click.echo(format_table(["ID", "NAME", "STATUS"], rows))
        click.echo()

    if volumes:
        click.echo("Unused volumes:")
        rows = [[v.name] for v in volumes]
        click.echo(format_table(["NAME"], rows))
        click.echo()

    if networks:
        click.echo("Unused networks:")
        rows = [[n.name] for n in networks]
        click.echo(format_table(["NAME"], rows))
        click.echo()


@main.command()
@click.option("--all", is_flag=True, help="Remove all unused images, not just dangling")
@click.option("-f", "--force", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def clean(ctx, all, force):
    """Remove dangling images, stopped containers, and unused volumes."""
    client: DockerClient = ctx.obj["client"]
    _check_docker(client)

    try:
        if all:
            images = client.list_all_unused_images()
        else:
            images = client.list_dangling_images()
        containers = client.list_stopped_containers()
        volumes = client.list_unused_volumes()
        networks = client.list_unused_networks()
    except DockerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    image_size = sum(img.size_bytes for img in images)
    label = "unused images" if all else "dangling images"

    click.echo("The following resources will be removed:")
    click.echo(f"  {len(images)} {label} ({format_size(image_size)})")
    click.echo(f"  {len(containers)} stopped containers")
    click.echo(f"  {len(volumes)} unused volumes")
    click.echo(f"  {len(networks)} unused networks")
    click.echo()

    if not force and (images or containers or volumes or networks):
        if not click.confirm("Continue?"):
            click.echo("Aborted.")
            return

    # Perform cleanup
    img_removed, img_failed = client.remove_images([i.id for i in images])
    ctr_removed, ctr_failed = client.remove_containers([c.id for c in containers])
    vol_removed, vol_failed = client.remove_volumes([v.name for v in volumes])
    net_removed, net_failed = client.remove_networks([n.name for n in networks])

    click.echo()
    click.echo("Cleanup complete:")
    click.echo(f"  Images:     {img_removed} removed, {img_failed} failed")
    click.echo(f"  Containers: {ctr_removed} removed, {ctr_failed} failed")
    click.echo(f"  Volumes:    {vol_removed} removed, {vol_failed} failed")
    click.echo(f"  Networks:   {net_removed} removed, {net_failed} failed")


@main.command()
@click.option("-f", "--force", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def prune(ctx, force):
    """Run docker system prune (quick cleanup of all unused data)."""
    client: DockerClient = ctx.obj["client"]
    _check_docker(client)

    click.echo("This will remove:")
    click.echo("  - All stopped containers")
    click.echo("  - All dangling images")
    click.echo("  - All unused networks")
    click.echo("  - Build cache")
    click.echo()

    if not force:
        if not click.confirm("Continue?"):
            click.echo("Aborted.")
            return

    result = client.prune_all()
    if result["success"]:
        click.echo(result["output"])
    else:
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)


@main.command()
@click.option("-f", "--force", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def prune_all(ctx, force):
    """Run docker system prune -a (removes ALL unused images, not just dangling)."""
    client: DockerClient = ctx.obj["client"]
    _check_docker(client)

    click.echo("WARNING: This will remove ALL unused images, not just dangling ones.")
    click.echo("Images used by stopped containers will also be removed.")
    click.echo()

    if not force:
        if not click.confirm("Are you sure?"):
            click.echo("Aborted.")
            return

    result = client.prune_all(all=True)
    if result["success"]:
        click.echo(result["output"])
    else:
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)


def _check_docker(client: DockerClient):
    """Check docker is available, exit if not."""
    if not client.available:
        click.echo("Error: Cannot connect to Docker daemon. Is Docker running?", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
