# Raspberry Pi host metrics

One Telegraf process on each enrolled Pi writes samples directly to the private CT111 InfluxDB v2 API, in organization `worganisation` and bucket `pi-hosts`. The agent sets the stable lowercase short host name and timestamps each observation before buffering. It collects every minute and buffers up to 1,000 metrics in memory while the database is unavailable. Process restarts or a full buffer can leave a gap. Each Pi uses a separate token with **write only** on this bucket. The token can be revoked individually. InfluxDB scopes permissions by bucket, so it trusts an enrolled writer to supply its own host tag.

| Measurement | Fields and tags used by consumers |
| --- | --- |
| `system`, `cpu`, `mem`, `swap` | `uptime` in seconds and `load1/5/15`, `usage_idle` and `usage_iowait` for `cpu=cpu-total`, memory and swap `used_percent`. Uptime point time is the heartbeat. |
| `disk`, `net`, `pi_link`, `wireless` | Capacity and free space on the selected mounted `path`. Network counters by physical `interface`, link `up` and Wi-Fi `level` in dBm where the driver reports it. Compute traffic rates from non-negative counter differences. |
| `pi_hardware`, `pi_packages` | `temperature_c`, `frequency_mhz`, `throttling_active`, `throttling_occurred`, raw flags, `fan_speed_rpm`, `fan_pwm_percent` and `reboot_required`. Pending package count comes from the local apt cache every six hours. Unavailable hardware fields are omitted. |
| `pi_mount` | `mount` tag, boolean `healthy` and the first failing `reason` or `ok`. VaultPi checks exact mountpoint, source identity, read/write state and required child directories using the same inspection as pi_stats. |
| `smart_device`, `smart_attribute` | Every five minutes on VaultPi, `health_ok`, `temp_c` and supported wear readings by `device`. ATA reallocated and pending sector counts use `raw_value` for attribute IDs 5 and 197. NVMe wear uses `percentage_used`. Sleeping disks can omit a sample. |

## Enroll a Pi

1. Install a Telegraf build compatible with the Pi's actual OS and CPU architecture and providing the configured inputs. The configuration targets Telegraf 1.40.1. Check `dpkg --print-architecture`, `telegraf --version` and the available plugins on the Pi. The standalone installer needs Bash, systemd, the package's `telegraf` user and system Python 3.9+. It works independently of uv and the application's Python 3.14 environment. Check the vendor's packaged `telegraf.service` before enabling the dedicated unit. Leave only the intended agent collecting these measurements. [Install Telegraf](https://docs.influxdata.com/telegraf/v1/install/).
2. On CT111 create the `pi-hosts` bucket and issue a dedicated bucket-write token for this Pi. On the Pi, select `iot` for `10.0.0.111` or `main` for `192.168.68.231`, whichever CT111 interface is on its trusted local network. Verify its `/health` endpoint on port 8086 from that Pi. The deployment uses private HTTP; a bearer token is observable by a party able to intercept that LAN connection. Use the private path only.
3. Create the protected credential with the following commands. In the private editor enter one line, `PI_INFLUX_TOKEN=<this Pi's token>`. Keep the value out of command arguments and repository files.

   ```fish
   sudo install -d -m 0755 /etc/wg-pi-telegraf
   sudo touch /etc/wg-pi-telegraf/writer.env
   sudo chmod 0600 /etc/wg-pi-telegraf/writer.env
   sudoedit /etc/wg-pi-telegraf/writer.env
   ```

4. On VaultPi install `smartmontools`. Compare the configured SATA transports and NVMe device in `vaultpi-smart.conf` with the attached disks. The role grants Telegraf the three exact read-only smartctl invocations. ATA disks behind SAT USB bridges are addressed explicitly. Check `/etc/wg-pi-telegraf/mounts.json` against the existing `PI_STATS_MOUNTS_JSON` before relying on mount alerts. You may set this file before installing. The installer seeds VaultPi's checked-in defaults only when it is absent and preserves the owner's checks on subsequent installs. The `telegraf` user needs directory traversal to inspect the listed children and read access to the Pi firmware device for throttle flags (normally the `video` group).
5. From a reviewed release checkout, run `sudo deployment/pi-telegraf/install iot` or select `main`. A second argument can set the existing canonical host ID when the operating system has a different name. Keep that ID stable across restarts and releases. The installer prepares files and reloads systemd. Choose the activation time with `sudo systemctl enable --now wg-pi-telegraf.service`.

## Check the first samples and complete cutover

In Grafana Explore use the scoped Pi InfluxDB reader. Replace `vaultpi` with the enrolled host.

```flux
from(bucket: "pi-hosts")
    |> range(start: -10m)
    |> filter(fn: (r) => r.host == "vaultpi" and r._measurement == "system" and r._field == "uptime")
    |> last()
```

Compare the point time and uptime with the Pi. Check `100 - usage_idle` against host CPU use, compare the thermal reading with local sysfs, and check any current throttling or SMART references against the device. On VaultPi expect both mount IDs and a fresh result for each awake drive. Compare the reported mount status with `findmnt` and the required directories. A typed false mount sample, a missing drive metric and an absent host heartbeat require different operator checks. Inspect `journalctl -u wg-pi-telegraf.service` for collection or write errors. A valid direct write and fresh points establish InfluxDB routing and authorization.

Keep the MQTT publisher available until the intended Home Assistant readers, storage alerts and any local fan control have been checked on the same host. Then run `sudo systemctl disable --now pi_stats.service` for that Pi. A later wg-scripts release keeps an inactive, disabled pi_stats unit retired on an enrolled host. Unrelated MQTT applications continue to use their own services. When rolling the checkout back to a release that restarts every installed service, remove the retired pi_stats unit file and reload systemd first to keep its publisher stopped. After HA no longer uses the old device, remove only its retained discovery configuration at `homeassistant/device/<hostname>_pi_stats/config` using the broker's authorized management path. Leave other hosts and devices intact.

The wg-scripts release workflow targets MtrxPi, VaultPi and VSMPPi. Its normal deploy path refreshes the dedicated unit only on enrolled hosts and restarts it if active. For other Pis, run the standalone installer again from the reviewed revision and use `sudo systemctl try-restart wg-pi-telegraf.service`. When an individual Pi leaves the fleet, stop and disable its unit and revoke its own InfluxDB writer.
