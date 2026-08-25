# Recovery console

`cinemate-recovery.service` is a small, deliberately ugly web console on `:8080` for the moment Cinemate will not start. It lets you see why, edit `settings.jsonc` and `config.txt`, and restart Cinemate — from a phone, over the camera's own hotspot, with no laptop and no SSH.

It is not a replacement for the [Web GUI](web-gui.md) or the [Web API](web-api.md). Those need Cinemate itself to be running. This console is the thing that still works when Cinemate is not.

## Reaching it

Connect a phone or laptop to the camera's hotspot (see [Configuring the Wi-Fi hotspot](hotspot-logic.md)), then browse to:

```
http://10.42.0.1:8080
```

That is the fixed address of the hotspot interface itself and always works while connected to the hotspot. If your device is on the same network as the Pi some other way (Ethernet, or joined to the same Wi-Fi), `http://cinepi.local:8080` works too, via mDNS.

That is the fixed address of the hotspot interface — it does not change, even when `settings.jsonc` is broken and the SSID itself has fallen back to a cached or default name. The recovery console runs as its own root systemd service with no dependency on `cinemate-autostart.service`, so it stays reachable through a Cinemate crash, a corrupted install, or Redis being down.

## What it can do

| Page | Purpose |
|---|---|
| **Status** (`/`) | State of all four services, the active hotspot credential rung, disk free space, uptime |
| **Why it failed** (`/why`) | The same startup-failure text Cinemate prints on the HDMI monitor, rendered for a phone screen |
| **Log** (`/log`) | Recent journal entries for `cinemate-autostart`, `wifi-hotspot`, or `storage-automount` |
| **Edit settings.jsonc** (`/edit/settings`) | Edit and save `settings.jsonc`, with automatic backup and validation |
| **Edit config.txt** (`/edit/config`) | Edit `/boot/firmware/config.txt` — off by default; see below |

Only three services can be restarted or stopped from here: `cinemate-autostart`, `wifi-hotspot`, `storage-automount`. Nothing else is reachable through the console, by design.

## Settings validation

When you save `settings.jsonc`, the console validates it before writing, using the best check available:

1. If the system Python 3 interpreter and the Cinemate source tree are both present, it runs the *exact same* loader Cinemate itself uses — so a rejected save shows you the exact error, with line and column, that you would otherwise only see on the HDMI monitor.
2. If the source tree is missing or corrupted, it falls back to a plain JSON syntax check.
3. If neither is available, the file is written anyway and labelled **unvalidated** — refusing to save would leave you unable to fix a file that is already broken. A backup is taken first regardless, so nothing is lost either way.

Every save keeps the previous version in `/var/lib/cinemate/backups/`, up to the last 10.

## Editing config.txt

Editing `/boot/firmware/config.txt` is **disabled by default**. Enable it deliberately in `settings.jsonc`:

```jsonc
"system": {
  "recovery": {
    "allow_config_txt": true
  }
}
```

It is off by default because a bad `config.txt` can stop the Pi from booting at all — and once that happens, nothing running *on* the Pi can fix it (see [The honest limit](#the-honest-limit) below).

When enabled, every save is protected by a confirm-or-revert countdown:

1. You save a change. The console backs up the previous `config.txt` and arms a countdown (5 minutes by default).
2. Reboot to apply the change.
3. If the camera comes back and you confirm in the console, the change is kept.
4. If you do **not** confirm within the countdown — because the change broke something and you can't reach the console, or because you forgot — the console restores the previous `config.txt` and reboots the Pi automatically.

This recovers a Pi that boots but is broken in some way: no camera, no HDMI output, no network. See the next section for what it cannot recover.

## The honest limit

Nothing running on the Pi can bring back a Pi that never reaches userspace. If a `config.txt` change is bad enough to stop the boot process itself — before the confirm-or-revert timer can ever run — the recovery console cannot help you, because nothing on the Pi is running yet.

The only fallback in that case:

1. Power off the Pi and remove the SD card (or the boot drive, if you have relocated `/boot`).
2. Mount its FAT boot partition on any Mac or Windows machine.
3. Find the most recent `config.txt.<timestamp>.bak` file and copy it over `config.txt`.
4. Put the card back and boot normally.

This is the reason config.txt editing defaults to off, and the reason a backup is taken on every single write with no exceptions — the backup is what makes step 3 possible.

## Configuring the console

A new `system.recovery` block in `settings.jsonc`:

```jsonc
"system": {
  "recovery": {
    "enabled": true,
    "port": 8080,
    // Required on every save/restart/config change once non-empty. Status,
    // why, and log stay reachable without it, so you can always diagnose.
    "token": "",
    "allow_config_txt": false,
    "config_confirm_timeout_s": 300
  }
}
```

A missing `system.recovery` block behaves exactly as the defaults shown above — you do not need to edit `settings.jsonc` to get a working recovery console.

If `settings.jsonc` cannot be parsed at all, the console falls back to `/etc/cinemate-recovery.conf` (written by the installer), and then to the same compiled-in defaults if that is unreadable too.

## Installing

Installed and enabled by default by `cinemate-install.sh`. To manage it manually on an existing install:

```bash
sudo make -C /home/pi/cinemate/services enable-cinemate-recovery   # install + enable + start
sudo make -C /home/pi/cinemate/services status-cinemate-recovery
sudo make -C /home/pi/cinemate/services disable-cinemate-recovery
```

## Security

The console runs as root and can restart Cinemate and rewrite `config.txt`. Read-only pages (status, why, log) are always reachable without a token, so a locked-out operator can still diagnose. Any page that changes something — restarting a service, saving a file — is logged to the journal with the client's IP address, and is gated behind the `token` setting once it is non-empty.
