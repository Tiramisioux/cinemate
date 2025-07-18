# Configuring the Wi-Fi hotspot
If `wifi_hotspot` in `settings.json` is `true` and no hotspot is active, Cinemate starts its own hotspot `nmcli device wifi hotspot` using your chosen SSID and password. If the Pi is already connected to wifi (for example WiFi settings set with `sudo raspi-config`) this connection will be replaced by Cinemates hotspot. Set `enabled: false` to keep wlan0 free for regular Wi‑Fi use. 

>Note that Cinemate still streams its web gui on whatever network the Pi is connected to, with GUI at <ip-address>:5000 and clean preview without GUI on <ip-address>:8000/stream