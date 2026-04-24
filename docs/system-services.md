# System services

Cinemate uses three system services for its operation.

## cinemate-autostart.service

Responsible for autostart of Cinemate on boot. By default, it is turned off on the [downloadable image file](https://github.com/Tiramisioux/cinemate/releases/tag/3.2).

Starting in v3.2 the service now waits for the camera sensor to come online before launching the UI. The helper script `/usr/local/bin/camera-ready.sh` polls `cinepi-raw --list-cameras` for up to 30 seconds and logs progress to the systemd journal so Cinemate does not start with a black screen if the IMX sensor is still initialising.

When Plymouth is enabled on the Pi image, the service is also ordered before `plymouth-quit.service`, `plymouth-quit-wait.service`, and `getty@tty1.service`. That keeps the boot spinner visible while the camera check and the extra display-settle delay run, instead of briefly showing the autologin CLI on `tty1` before Cinemate takes over the screen.

Plymouth is optional. Cinemate still starts correctly if Plymouth is not installed; you simply will not get the boot spinner or the smoother spinner-to-Cinemate handoff used on the image.

While `cinemate-autostart.service` is running, `tty1` is reserved for Plymouth and the Cinemate GUI. The local login prompt is therefore suppressed on `tty1` during runtime and restored when the service stops. Use SSH or switch to `tty2` if you need a shell while Cinemate is active.

The service now uses `Type=notify`, so systemd can track Cinemate's boot progress through status messages such as the splash becoming active and the GUI starting.

To keep `journalctl -fu cinemate-autostart` readable when ALSA reports noisy underruns, the unit rate-limits log output (see `LogRateLimitIntervalSec` and `LogRateLimitBurst` in the service file). Adjust those values if you need more or less verbosity.

### Starting, stopping, enabling and disabling the service

Go to the Cinemate folder:

```
cd cinemate

make install   # copy service file
make enable    # start on boot
make start     # launch now
make stop      # stop it
make status    # check status
make disable   # disable autostart
make clean     # remove the service
```

The `make install` step also copies `camera-ready.sh` into `/usr/local/bin/` with execute permissions so that the systemd unit can call it from `ExecStartPre`.

If you want the same boot spinner flow as the prebuilt image, install Plymouth separately as described in the manual install guide and then reinstall `cinemate-autostart.service` so the latest `tty1` and `plymouth-quit*` ordering is in place.

To start Cinemate manually, anywhere in the cli, type `cinemate`.

## storage-automount.service

Storage-automount is a systemd service that watches for removable drives and mounts them automatically. The accompanying Python script reacts to udev events and the CFE-HAT eject button so drives can be attached or detached safely.

It understands `ext4`, `ntfs` and `exfat` filesystems. Partitions labelled `RAW` are mounted at `/media/RAW`; any other label is mounted under `/media/<LABEL>` after sanitising the name. This applies to USB SSDs, NVMe drives and the CFE-HAT slot.

!!! note

     On the image file, the storage-automount.service is activated by default.

To manually install and enable the service:

```bash
cd cinemate/services/storage-automount

sudo make install
sudo make enable
```

The install step also disables the older `cfe-hat-automount.service` if it is present. Both services try to manage the same NVMe/CFE storage, and leaving them enabled together can cause `/media/RAW` to be mounted by `storage-automount` and then immediately unmounted again by the legacy service.

You can stop or disable it later with:
```bash
sudo make stop
sudo make disable
```

## wifi-hotspot.service
Wifi-hotspot keeps a small access point running with the help of NetworkManager so you can always reach the web interface. The SSID and password are read from `/home/pi/cinemate/src/settings.json` under `system.wifi_hotspot`.

This service is a watchdog, not the only hotspot entry point. The main Cinemate app can also create the hotspot during startup when hotspot mode is enabled in `settings.json`. The service simply keeps that network alive even if the main app is not running.

Install and enable it with:

```bash
cd cinemate/services/wifi-hotspot

sudo make install
sudo make enable
```

As with **storage-automount**, you can stop or disable the hotspot with 

````
make stop
make disable
```

!!! note

      While evaluating, it might be practical to have the Pi connect to your local wifi for easy access (`sudo raspi-config`). Therefore, on the image file, the wifi-hotspot.service is **not** activated by default. Cinemate will still serve its web interface on the available network, but only after `wlan0` or `eth0` has an IP address. You can read more [here](hotspot-logic.md)
