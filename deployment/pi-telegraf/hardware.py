"""Emit bounded Raspberry Pi hardware readings for Telegraf's exec input."""

from __future__ import annotations

import re
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- fixed read-only firmware command.
from contextlib import suppress
from pathlib import Path


def read_number(path: Path) -> int | None:
    """Read an integer from an optional sysfs sensor.

    Args:
        path: The kernel-provided attribute file.

    Returns:
        The sensor value, or None when the attribute is unavailable.
    """
    with suppress(OSError, ValueError):
        return int(path.read_text(encoding="ascii").strip())

    return None


def throttling_fields() -> list[str]:
    """Read the active and historical Raspberry Pi firmware warning bits.

    Returns:
        Line-protocol fields for a valid firmware response, otherwise an empty list.
    """
    for executable in ("/usr/bin/vcgencmd", "/opt/vc/bin/vcgencmd"):
        if not Path(executable).is_file():
            continue

        with suppress(OSError, subprocess.SubprocessError):
            result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed executable and operation.
                [executable, "get_throttled"],
                check=True,
                capture_output=True,
                text=True,
                timeout=3,
            )
            if match := re.fullmatch(
                r"throttled=(0x[0-9a-fA-F]+)", result.stdout.strip()
            ):
                flags = int(match[1], 16)
                return [
                    f"throttled_flags={flags}i",
                    f"throttling_active={str(bool(flags & 0xF)).lower()}",
                    f"throttling_occurred={str(bool(flags & 0xF0000)).lower()}",
                ]

    return []


def main() -> None:
    """Write one line of available readings without manufacturing missing values."""
    fields = throttling_fields()
    reboot = Path("/var/run/reboot-required").is_file()
    fields.append(f"reboot_required={str(reboot).lower()}")

    if (temp := read_number(Path("/sys/class/thermal/thermal_zone0/temp"))) is not None:
        fields.append(f"temperature_c={temp / 1000.0}")

    freq = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    if (khz := read_number(freq)) is not None:
        fields.append(f"frequency_mhz={khz / 1000.0}")

    for name in Path("/sys/class/hwmon").glob("hwmon*/name"):
        with suppress(OSError):
            if name.read_text(encoding="ascii").strip() != "pwmfan":
                continue

            if (rpm := read_number(name.with_name("fan1_input"))) is not None:
                fields.append(f"fan_speed_rpm={rpm}i")
            if (duty := read_number(name.with_name("pwm1"))) is not None:
                fields.append(f"fan_pwm_percent={round(duty * 100.0 / 255, 1)}")
            break

    for nic in sorted(Path("/sys/class/net").glob("*")):
        if (
            not re.fullmatch(r"(?:eth|en|wl)[a-zA-Z0-9_-]+", nic.name)
            or not (nic / "device").exists()
        ):
            continue

        with suppress(OSError):
            state = (nic / "operstate").read_text(encoding="ascii").strip()
            if state in {"up", "down", "lowerlayerdown", "dormant"}:
                link = str(state == "up").lower()
                print(f"pi_link,interface={nic.name} up={link}")  # ruff: ignore[print] -- Telegraf line protocol.

    print("pi_hardware " + ",".join(fields))  # ruff: ignore[print] -- Telegraf line protocol.


if __name__ == "__main__":
    main()
