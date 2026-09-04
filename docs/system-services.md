# System services

CineMate owns four long-running services and one maintenance timer. It also depends on a fifth unit
it does not own, `redis-server`, which the installer enables — six systemd units in all. See [The
CineMate stack explained](cinemate-stack.md#what-runs-as-what) for the whole list in one table.

## cinemate-autostart.service

Autostarts CineMate on boot.

### Single-instance enforcement

Only one instance of CineMate can run at a time. If you start `cinemate` while the service (or a previous manual session) is already running, the new instance automatically sends a graceful stop signal to the existing one, waits up to 5 seconds for it to exit cleanly, then proceeds with its own startup. No manual intervention is needed.

This means you can type `cinemate` in an SSH session at any time to restart the app — even if it is already running via the autostart service.

## storage-automount.service

Watches for removable drives and mounts them automatically. The accompanying Python script reacts to udev events and the CFE-HAT eject button so drives can be attached or detached safely.

It understands `ext4`, `ntfs` and `exfat` filesystems. Partitions labelled `RAW` are mounted at `/media/RAW`; any other label is mounted under `/media/<LABEL>` after sanitising the name. This applies to USB SSDs, NVMe drives and the CFE-HAT slot.

## wifi-hotspot.service

Keeps a small access point running with the help of NetworkManager so you can always reach the web interface. The SSID and password are read from `/home/pi/cinemate/settings.jsonc` under `system.wifi_hotspot`. Runs entirely independently of `cinemate-autostart.service` — it survives a CineMate crash — and applies a credential fallback ladder if `settings.jsonc` is broken. See [Configuring the Wi-Fi hotspot](hotspot-logic.md).

## cinemate-recovery.service

A standalone, root-run, standard-library-only web console on `:8080` for diagnosing and repairing a CineMate that will not start — from a phone on the hotspot, with no laptop or SSH. It has no dependency on `cinemate-autostart.service`, by design: that coupling is exactly what would make a recovery tool unreachable when it is needed most. See [Recovery console](recovery-console.md).

## redis-log-maintenance.timer

Lightweight timer-backed helper that keeps `/var/log/redis/redis-server.log` from silently filling the Pi root filesystem over time.
