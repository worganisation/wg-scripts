"""Publish one bounded Influx line per enrolled mount using the pi_stats checks."""

from __future__ import annotations

from pathlib import Path

from mount_health import collect_mount_health, parse_mount_checks


def main() -> None:
    """Write the overall health and first actionable reason for each mount.

    Raises:
        OSError: The configured mount file cannot be read.
        ValueError: A check is invalid.
        TypeError: A check contains a value of the wrong type.
    """  # ruff: ignore[docstring-extraneous-exception] -- errors propagate from file and mount parsers.
    config = Path("/etc/wg-pi-telegraf/mounts.json").read_text(encoding="utf-8")
    checks = parse_mount_checks(config)

    for mount, health in collect_mount_health(checks).items():
        healthy = str(health["healthy"]).lower()
        reason = health["reasons"][0] if health["reasons"] else "ok"
        print(f'pi_mount,mount={mount} healthy={healthy},reason="{reason}"')  # ruff: ignore[print] -- Telegraf line protocol.


if __name__ == "__main__":
    main()
