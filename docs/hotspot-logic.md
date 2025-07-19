# Configuring the Wi-Fi hotspot
The built‑in hotspot ensures you can always reach Cinemate even when there is no other network available. When `wifi_hotspot` in `settings.json` is set to `true` and no hotspot is active, Cinemate runs `nmcli device wifi hotspot` using your chosen SSID and password.

This is handy when shooting in the field. Connect your phone or laptop directly to the hotspot and browse to the GUI to control the camera. If the Pi was previously connected to a Wi‑Fi network, that connection is replaced by the hotspot.

During development you may want the Pi to join your normal Wi‑Fi so it has internet access. Set `system.wifi_hotspot.enabled` to `false` and configure Wi‑Fi through `raspi-config` or the desktop tools. The web interface will appear on the Pi's regular network address, letting you stay connected to both the Pi and the internet.

If you plug an Ethernet cable into the Pi, you can keep the hotspot running while also having a wired connection for internet and local networking.

>Note that Cinemate still streams its web gui on whatever network the Pi is connected to, with GUI at <ip-address>:5000 and clean preview without GUI on <ip-address>:8000/stream
