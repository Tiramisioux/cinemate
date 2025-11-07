# System services

Cinemate uses several system services for its operation.

!!! note ""

     Note if you have Cinemate already running, for example by running the preinstalled image file, anything you type will be interpreted by the Cinemate CLI only. In order to use these commands you have to [start an SSH session](ssh.md) and log in in a new shell.

## cinemate-autostart.service

Responsible for autostart of Cinemate on boot. By default, it is turned off on the [downloadable image file](https://github.com/Tiramisioux/cinemate/releases/tag/3.1).

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

## Storage automount services

Removable storage is managed by a shared Python helper (`services/storage-automount/storage-automount.py`) and three dedicated systemd units. Each unit targets a specific bus or hat so you can enable only what your build requires:

* `ssd-automount.service` – USB SSD enclosures and card readers
* `nvme-automount.service` – USB NVMe bridge adapters
* `cfe-hat-automount.service` – Will Whang's CFExpress hat on the PCIe slot

All three services understand `ext4`, `ntfs` and `exfat` filesystems. Partitions labelled `RAW` are mounted at `/media/RAW`; any other label is mounted under `/media/<LABEL>` after sanitising the name.

!!! note

     On the stock image the appropriate automount service is enabled automatically. If you rebuild manually, enable the units that match your hardware.

To manually install and enable one of the services:

```bash
cd cinemate/services/ssd-automount    # or nvme-automount / cfe-hat-automount

sudo make install
sudo make enable
```

You can stop or disable it later with:

```bash
sudo make stop
sudo make disable
```

If you prefer to install all automount units together, run:

```bash
cd cinemate/services

sudo make -f cinemate-services.Makefile install
```

## wifi-hotspot.service
Wifi-hotspot keeps a small access point running with the help of NetworkManager so you can always reach the web interface. The SSID and password are read from `/home/pi/cinemate/src/settings.json` under `system.wifi_hotspot`.

Install and enable it with:

```bash
cd cinemate/services/wifi-hotspot

sudo make install
sudo make enable
```

As with the storage automount services, you can stop or disable the hotspot with

````
make stop
make disable
```

!!! note

      While evaluating, it might be practical to have the Pi connect to your local wifi for easy access (`sudo raspi-config`). Therefore, on the image file, the wifi-hotspot.service is **not** activated by default. Cinemate will still stream its web interface on the available netowrk. You can read more [here](hotspot-logic.md)