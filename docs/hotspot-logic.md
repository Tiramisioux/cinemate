# Configuring the Wi-Fi hotspot

The built-in hotspot lets you use any device (phone/tablet/computer) for preview/controlling the camera.

Once joined, the camera is at `cinepi.local` or, equivalently, `10.42.0.1`. 

During development you may want the Pi to join your normal Wi-Fi so it has internet access. Set `system.wifi_hotspot.enabled` to `false` and configure Wi-Fi through `raspi-config` or the desktop tools.

If you plug an Ethernet cable into the Pi, you can keep the hotspot running while also having a wired connection for internet and local networking.

!!! note ""
    The web GUI only starts when `wlan0` or `eth0` already has an IP address. When networking is up, the UI is served at `<ip-address>:5000` and the clean preview stream is at `<ip-address>:8000/stream`. If the interface comes up only after CineMate has already started, restart CineMate to start the web server.
