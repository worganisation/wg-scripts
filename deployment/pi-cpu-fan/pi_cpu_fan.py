"""Operate a Pi CPU fan from its local thermal sensor and optional OctoPrint job state."""

from __future__ import annotations

import json
import logging
import signal
import time
from configparser import ConfigParser, SectionProxy
from configparser import Error as ConfigError
from http import HTTPStatus
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from threading import Event

from RPi import GPIO

CONFIG_DIR = Path("/etc/pi-cpu-fan")
THERMAL = Path("/sys/class/thermal/thermal_zone0/temp")
POLL_SECONDS = 5
DWELL_SECONDS = 300
EMERGENCY_C = 80
RECOVER_C = 75
MIN_THRESHOLD_C = 20
MAX_THRESHOLD_C = 100
MAX_SENSOR_C = 125
MAX_HEADER_BCM = 27
MAX_JOB_BYTES = 65536
LOGGER = logging.getLogger("pi-cpu-fan")


def settings(name: str) -> SectionProxy:
    """Read the fan section of a local INI file.

    Args:
        name: Configuration filename under /etc/pi-cpu-fan.

    Returns:
        The fan section from a freshly read file.

    Raises:
        OSError: The file could not be read.
        ConfigError: The file is malformed.
        KeyError: The fan section is missing.
    """  # ruff: ignore[docstring-extraneous-exception] -- File and parser errors propagate to the caller.
    parser = ConfigParser(interpolation=None)
    with (CONFIG_DIR / name).open(encoding="utf-8") as source:
        parser.read_file(source)

    return parser["fan"]


def printer_idle() -> bool:
    """Check whether the local OctoPrint server positively reports idle.

    Returns:
        True only for an authenticated, successful, current Operational response.
    """
    connection = HTTPConnection("127.0.0.1", 5000, timeout=2)
    try:
        key = (CONFIG_DIR / "octoprint.key").read_text(encoding="ascii").strip()
        connection.request("GET", "/api/job", headers={"X-Api-Key": key})
        response = connection.getresponse()
        if response.status != HTTPStatus.OK:
            return False

        body = response.read(MAX_JOB_BYTES + 1)
        if len(body) > MAX_JOB_BYTES:
            return False

        job = json.loads(body)
        return isinstance(job, dict) and job.get("state") == "Operational"
    except (OSError, ValueError, HTTPException):
        return False
    finally:
        connection.close()


def requested_state(
    *, current: bool, elapsed: float, watch_print: bool
) -> tuple[bool, str]:
    """Calculate the next output from fresh local inputs.

    Args:
        current: Current logical fan state.
        elapsed: Monotonic seconds since the last output transition.
        watch_print: Check OctoPrint whenever an active fan would stop.

    Returns:
        The requested fan state and a bounded reason for journal diagnostics.
    """
    try:
        temperature = int(THERMAL.read_text(encoding="ascii")) / 1000
        controls = settings("controls.ini")
        threshold = controls.getfloat("threshold_c")
        mode = controls["mode"]
        if (
            not 0 < temperature <= MAX_SENSOR_C
            or threshold is None
            or not MIN_THRESHOLD_C <= threshold <= MAX_THRESHOLD_C
            or mode not in {"auto", "on", "off"}
        ):
            return True, "input_unavailable"
    except (OSError, ValueError, TypeError, KeyError, ConfigError):
        return True, "input_unavailable"

    if temperature >= EMERGENCY_C:
        return True, "thermal_ceiling"

    demand = mode == "on" or (mode == "auto" and temperature > threshold)
    reason = mode
    if current and not demand and temperature >= RECOVER_C:
        demand, reason = True, "thermal_recovery"
    elif demand != current and elapsed < DWELL_SECONDS:
        demand, reason = current, "dwell"
    elif current and not demand and watch_print and not printer_idle():
        demand, reason = True, "print_or_unknown"

    return demand, reason


def main() -> None:
    """Claim the configured fan output and run local control until the service stops.

    Raises:
        OSError: The hardware configuration cannot be read.
        ConfigError: The hardware configuration is malformed.
        KeyError: A mandatory hardware setting is missing.
        ValueError: A hardware setting is invalid.
        RuntimeError: The GPIO device cannot be driven.
    """  # ruff: ignore[docstring-extraneous-exception] -- GPIO and configuration errors propagate.
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    hardware = settings("hardware.ini")
    pin = int(hardware["bcm_pin"])
    if not 0 <= pin <= MAX_HEADER_BCM:
        raise ValueError("Select a confirmed BCM header pin from 0 to 27")

    active_high = hardware.getboolean("active_high")
    watch_print = hardware.getboolean("watch_print")
    if active_high is None or watch_print is None:
        raise ValueError("Set both active_high and watch_print in hardware.ini")

    stopping = Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stopping.set())

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.OUT, initial=int(active_high))
    current = True
    changed = time.monotonic()
    previous_reason = "startup"
    LOGGER.info("fan=on reason=startup")

    try:
        while not stopping.is_set():
            target, reason = requested_state(
                current=current,
                elapsed=time.monotonic() - changed,
                watch_print=watch_print,
            )
            if target != current:
                GPIO.output(pin, int(target == active_high))
                changed = time.monotonic()

            if target != current or reason != previous_reason:
                LOGGER.info("fan=%s reason=%s", "on" if target else "off", reason)

            current, previous_reason = target, reason
            stopping.wait(POLL_SECONDS)
    finally:
        GPIO.output(pin, int(active_high))


if __name__ == "__main__":
    main()
