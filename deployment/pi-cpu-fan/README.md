# Local CPU fan control

OctoPi and CRTPi can run their CPU fans from the Pi's own thermal sensor. The service runs under the distribution's Python 3.9 or later with `python3-rpi.gpio`, independently of Home Assistant, MQTT, Telegraf and the wg-scripts virtual environment. Install the service only on a Pi whose fan wiring and other GPIO owners you have identified.

| Host | Fan pin and driver to hand over | Starting threshold | Print policy |
| --- | --- | --- | --- |
| OctoPi | OctoPrint GPIO Control's **CPU Fan**, BCM26, active high | 65 °C | Once running, hold the fan on until OctoPrint reports `Operational` |
| CRTPi | Inspect the active GPIO service and the local `cpu-fan` mapping before setting the BCM pin and polarity | 70 °C | Temperature only |

## Prepare the local controls

Use an idle maintenance window. Check the thermal source with `cat /sys/class/thermal/thermal_zone0/{type,temp}` and verify that it represents the Pi CPU in millidegrees Celsius. Confirm that `/usr/bin/python3 -c 'from RPi import GPIO'` succeeds and that the service user `pi` belongs to the `gpio` group. From the reviewed wg-scripts checkout, stage just the service files:

```fish
sudo install -d -m 0755 /etc/pi-cpu-fan /usr/local/lib/pi-cpu-fan
sudo install -m 0644 deployment/pi-cpu-fan/pi_cpu_fan.py /usr/local/lib/pi-cpu-fan/
sudo install -m 0644 deployment/pi-cpu-fan/pi-cpu-fan.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Create root-owned `/etc/pi-cpu-fan/hardware.ini`. For OctoPi use:

```ini
[fan]
bcm_pin = 26
active_high = true
watch_print = true
```

For CRTPi set the BCM pin and polarity verified against its installed driver and set `watch_print = false`. Check `systemctl show mqtt_gpio -p ExecStart -p WorkingDirectory` and the matching checkout's `src/services/mqtt_gpio/gpio_mapping.json`. The wg-scripts driver uses BCM numbers and writes a high level for an on command. Check for service overrides, boot overlays and any other writer before transferring the output. Leave CRTPi on its existing controller if the mapping or polarity cannot be established.

Create root-owned `/etc/pi-cpu-fan/controls.ini` with the site's threshold:

```ini
[fan]
threshold_c = 65
mode = auto
```

Use `threshold_c = 70` for CRTPi or carry over its owner's current threshold. Controls are reread every five seconds. Edit this file to change the threshold (20–100 °C) or select `auto`, `on` or `off`. Changes survive a reboot. An unreadable temperature or invalid controls requests immediate cooling. At 80 °C the fan starts regardless of mode or dwell time. A running fan stays on at or above 75 °C. Below that boundary normal changes respect a five-minute minimum dwell and, on OctoPi, the print hold. Startup requests cooling immediately.

For OctoPi create a dedicated local OctoPrint account with only the **Status** permission and issue an API key for it. Create `/etc/pi-cpu-fan/octoprint.key` as `root:pi` with mode `0640` and enter the key using a local editor. The service reads only `GET /api/job` on `127.0.0.1:5000` before switching a running fan off. Printing, pausing, paused, unknown state, authentication failure and timeout hold the fan on. Each decision uses a fresh response. The journal contains only the requested fan state and a bounded reason.

## Transfer one pin

1. Check the new host files and take note of the working settings for the existing GPIO and MQTT handlers. Disable the corresponding Home Assistant **CPU fan control** automation and manual command sources during the handoff. Its retained command can still be replayed to a subscribed driver.
2. On CRTPi remove the `cpu-fan` entry from the active GPIO driver's mapping and restart that driver to release the old subscription and callbacks. Preserve mappings for other pins. If the CPU fan is its only mapping, stop and disable the old unit instead. Check the installed driver's script, mapping and active service state before proceeding.
3. On OctoPi wait for an idle printer. Remove MQTT Subscribe's `/octopi/gpio/cpu-fan` command, then remove only the **CPU Fan** entry in GPIO Control. **Enclosure Fan** stays on BCM16, active high. GPIO Control resolves its API `id` by position in the configuration list. With the two configured outputs, removing CPU Fan moves Enclosure Fan from index 1 to 0. Update the **enclosure** MQTT Subscribe command for `/prusa-i3-mk3/enclosure/fan` to `{"command":"turnGpio{0}", "id": 0}`, keeping the existing topic and extraction. If the list contains other entries, use the enclosure's actual new index. Restart OctoPrint while idle so the old CPU output is released. Verify the enclosure mapping and that OctoPrint's enclosure control reads the correct output.
4. With the old writer detached, run `sudo systemctl enable --now pi-cpu-fan.service` on that Pi and inspect `journalctl -u pi-cpu-fan.service`. Check that the CPU fan spins at startup, the physical output matches its polarity, and the enclosure fan and any unrelated GPIO outputs retain their normal behavior. On a cool idle Pi, observe the automatic transition after five minutes. Try `mode = on`, observe the fan after the dwell, then restore `auto`. Confirm a naturally occurring print holds an already-running OctoPi fan through cooling and a subsequent idle response allows it to stop. Keep the old HA CPU controls disabled once local ownership is established.

For a rollback while the printer is idle, stop and disable the local controller **before** restoring the old GPIO mapping and MQTT subscription. Restore the original enclosure index on OctoPi. Check the retained CPU command and current temperature, then re-enable the previous HA automation and verify cooling. Service shutdown requests fan on. Check the actual pin after switching drivers or powering down the board.
