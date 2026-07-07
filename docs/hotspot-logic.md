# Configuring the Wi-Fi hotspot

The built-in hotspot lets you use any device (phone/tablet/computer) for preview/controlling the camera.

There are two layers involved:

- **At app startup:** when `system.wifi_hotspot.enabled` is `true`, Cinemate can create the hotspot itself with `nmcli device wifi hotspot` using the SSID and password from `settings.json`.
- **As a background service:** `wifi-hotspot.service` is a simple watchdog that recreates the hotspot if it is supposed to be on and NetworkManager no longer reports an active hotspot.

This is handy when shooting in the field. Connect your phone or laptop directly to the hotspot and browse to the GUI to control the camera. If the Pi was previously connected to another Wi-Fi network, that Wi-Fi connection is replaced by the hotspot.

During development you may want the Pi to join your normal Wi-Fi so it has internet access. Set `system.wifi_hotspot.enabled` to `false` and configure Wi-Fi through `raspi-config` or the desktop tools.

If you plug an Ethernet cable into the Pi, you can keep the hotspot running while also having a wired connection for internet and local networking.

!!! note ""
    The web GUI only starts when `wlan0` or `eth0` already has an IP address. When networking is up, the UI is served at `<ip-address>:5000` and the clean preview stream is at `<ip-address>:8000/stream`. If the interface comes up only after Cinemate has already started, restart Cinemate to start the web server.
