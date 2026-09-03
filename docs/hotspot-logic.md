# Configuring the Wi-Fi hotspot

The built-in hotspot lets you use any device (phone/tablet/computer) for preview/controlling the camera.

There are three layers involved, each able to keep the hotspot up if the one above it is not running:

- **NetworkManager itself:** the AP connection profile is persisted with `connection.autoconnect=yes`, so the hotspot comes up at boot before any Cinemate Python has run at all — even if both layers below are dead.
- **As a background service:** `wifi-hotspot.service` reconciles the hotspot every 60 seconds. It runs as its own root systemd unit with no dependency on `cinemate-autostart.service`, so it keeps working through a Cinemate crash, a corrupted install, or a `settings.jsonc` that fails to parse.
- **At app startup:** when `system.wifi_hotspot.enabled` is `true`, Cinemate also creates the hotspot itself with `nmcli device wifi hotspot`. If `wifi-hotspot.service` is already active it stands down, so there is exactly one owner of the hotspot at any time.

This is handy when shooting in the field. Connect your phone or laptop directly to the hotspot and browse to the GUI to control the camera. If the Pi was previously connected to another Wi-Fi network, that Wi-Fi connection is replaced by the hotspot.

## Credential fallback ladder

`wifi-hotspot.service` resolves the SSID and password on every reconcile pass through three rungs, applied in order:

1. **`settings.jsonc` parses** — use `system.wifi_hotspot.name` / `.password`, and cache the result as the new last-known-good.
2. **`settings.jsonc` does not parse** — use the cached last-known-good credentials instead of falling straight to the compiled-in default.
3. **No usable cache** — fall back to the compiled-in `CinePi` / `11111111`.

This matters because a broken `settings.jsonc` is exactly the moment you most need to reach the camera. Without the cache rung, a single stray comma in `settings.jsonc` would silently rename your network back to `CinePi`, with no indication of why. With it, the hotspot keeps the SSID you last configured, and the reason for any fallback is recorded — not buried in a journal.

The active rung is published to `/var/lib/cinemate/hotspot.state` on every pass, and the [recovery console](recovery-console.md) displays it on its status page, so you can learn *"you are on the cached SSID because settings.jsonc is broken"* without SSH.

Restoring a valid `settings.jsonc` returns the hotspot to rung 1 — and the configured SSID — within one reconcile pass (up to 60 seconds), no reboot needed.

During development you may want the Pi to join your normal Wi-Fi so it has internet access. Set `system.wifi_hotspot.enabled` to `false` and configure Wi-Fi through `raspi-config` or the desktop tools.

If you plug an Ethernet cable into the Pi, you can keep the hotspot running while also having a wired connection for internet and local networking.

!!! note ""
    The web GUI only starts when `wlan0` or `eth0` already has an IP address. When networking is up, the UI is served at `<ip-address>:5000` and the clean preview stream is at `<ip-address>:8000/stream`. If the interface comes up only after Cinemate has already started, restart Cinemate to start the web server.
