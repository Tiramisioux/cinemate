# System services

Cinemate uses three system services for its operation.

## cinemate-autostart.service

Responsible for autostart of Cinemate on boot. By default, it is turned off on the [downloadable image file](https://github.com/Tiramisioux/cinemate/releases/tag/3.1).

!!! note
    
     Users are recommended to first start Cinemate manually (by typing `cinemate` in the cli) to be able to inspect the startup sequence and make sure that the app starts as expected. Then, when smooth startup is confirmed, the cinemate-autostart.service can be activated.

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

!!! note

     Note that in order for the web ui to work properly you have to run `make install` once in the `/home/pi/cinemate` folder, even if you are not using the autostart service.

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

You can stop or disable it later with:
```bash
sudo make stop
sudo make disable
```

## wifi-hotspot.service
Wifi-hotspot keeps a small access point running with the help of NetworkManager so you can always reach the web interface. The SSID and password are read from `/home/pi/cinemate/src/settings.json` under `system.wifi_hotspot`.

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

      While evaluating, it might be practical to have the Pi connect to your local wifi for easy access (`sudo raspi-config`). Therefore, on the image file, the wifi-hotspot.service is **not** activated by default. Cinemate will still stream its web interface on the available netowrk. You can read more [here](hotspot-logic.md)