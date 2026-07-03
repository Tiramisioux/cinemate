# System services

Cinemate uses three long-running services and one maintenance timer for its operation.

## cinemate-autostart.service

Autostarts Cinemate on boot.

### Single-instance enforcement

Only one instance of Cinemate can run at a time. If you start `cinemate` while the service (or a previous manual session) is already running, the new instance automatically sends a graceful stop signal to the existing one, waits up to 5 seconds for it to exit cleanly, then proceeds with its own startup. No manual intervention is needed.

This means you can type `cinemate` in an SSH session at any time to restart the app — even if it is already running via the autostart service.

## storage-automount.service

Watches for removable drives and mounts them automatically. The accompanying Python script reacts to udev events and the CFE-HAT eject button so drives can be attached or detached safely.

It understands `ext4`, `ntfs` and `exfat` filesystems. Partitions labelled `RAW` are mounted at `/media/RAW`; any other label is mounted under `/media/<LABEL>` after sanitising the name. This applies to USB SSDs, NVMe drives and the CFE-HAT slot.

## wifi-hotspot.service
Keeps a small access point running with the help of NetworkManager so you can always reach the web interface. The SSID and password are read from `/home/pi/cinemate/src/settings.json` under `system.wifi_hotspot`.

## redis-log-maintenance.timer

Lightweight timer-backed helper that keeps `/var/log/redis/redis-server.log` from silently filling the Pi root filesystem over time.