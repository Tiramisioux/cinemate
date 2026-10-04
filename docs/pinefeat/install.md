# Installation

Two levels. Almost everyone needs only the first.

| Level | Gives you | Install |
|---|---|---|
| **Basic** | Iris, focus, calibration, lens database | Nothing |
| **Kernel driver** (optional) | The same, reached through Pinefeat's driver. The board also appears as a V4L2 lens device for other tools. | Kernel driver (DKMS) and an overlay |

Autofocus is paused, so the driver is not needed for any CineMate feature today.

## Basic level

Connect the adapter and boot. CineMate finds the board on the camera's I²C bus and the lens controls appear.

| Check | Where |
|---|---|
| The `IRIS` group appears in the top row of the HDMI GUI | [Panes and controls](panes.md#hdmi-gui) |
| The **Lens / Pinefeat** pane says the adapter is found, via raw I²C | Settings editor |
| Nothing shows | See [Compatibility](compatibility.md#troubleshooting) |

!!! note ""
    If you ran Pinefeat's own `configure.sh` earlier, read [Undoing Pinefeat's installer](#undoing-pinefeats-installer) first. It is not needed for basic use and it clashes with the driver level.

## Kernel driver level (optional)

!!! note "Status"
    Desk-checked on all four platforms. The first run on a camera is still to come.

With the driver, the adapter is a **lens subdevice** in the camera's media graph. That takes two things:

| Piece | What it is |
|---|---|
| `cef168.ko` | Pinefeat's kernel driver, pinned at commit `e3abfb2`. Built with **DKMS**, so it is rebuilt for every kernel. |
| `cef168` overlay | CineMate's own device-tree overlay, `resources/overlays/cef168/cef168-overlay.dts`. Declares the board and tells the sensor about it. |

!!! danger "Never enable the overlay without the module"
    With the overlay loaded and `cef168.ko` missing for the running kernel, the sensor driver waits forever for a lens driver. **The camera never registers.** CineMate does not enable the overlay for you. When you add the line, check first:

    ```bash
    ~/cinemate/scripts/cef168-module-installed.sh -v && echo installed
    ```

    Prints the module's path and `installed`, or nothing. Recovery if the camera is already gone: remove the `dtoverlay=cef168` line from `/boot/firmware/config.txt` and reboot.

### Scripted

On an **installed camera**, run only this step:

```bash
cd ~/cinemate
scripts/install-cef168.sh
```

On a **fresh install**, add one variable to the normal installer:

```bash
INSTALL_CEF168_DRIVER=1 SENSOR_MODEL=imx477 CAM_PORT=cam0 ./cinemate-install.sh
```

Either way the step does this, and nothing else:

| Step | Detail |
|---|---|
| Packages | `dkms`, `device-tree-compiler`, and kernel headers for the target kernel |
| Driver | Clones `https://github.com/pinefeat/cef168` into `~/cef168` at the pinned commit |
| DKMS | Stages `cef168.c` with CineMate's `Kbuild` and `dkms.conf` in `/usr/src/cef168-1.0/`, then builds and installs for the target kernel |
| Overlay | Compiles it to `/boot/firmware/overlays/cef168.dtbo`. **Not enabled.** |
| Checks | Warns if Pinefeat's patch is still in a sensor overlay |

| Property | How |
|---|---|
| Opt-in | Off unless `INSTALL_CEF168_DRIVER=1` or you run the script |
| Safe to repeat | Skips DKMS when the module is already built for this pin and kernel. Skips the overlay when it is already current. |
| Never aborts the install | A failure prints a warning and the rest of the installer carries on. Basic use is unaffected. |
| Target kernel | Pi 5 and CM5: the pinned baseline kernel (reboot once to run it). Pi 4B and CM4: the running kernel. |
| Never touches `config.txt` | You add the line yourself, see below |

### Enabling the overlay

The script leaves the overlay off. Step 7 below turns it on. Do that only after step 5 shows the module.

### By hand, step by step

Use this to see exactly what the script does, and to enable the overlay.

1\. Packages and headers.

```bash
sudo apt install -y dkms device-tree-compiler git
```

Headers for the kernel you will run. Pi 5 and CM5: the CineMate installer already installed and pinned them. Pi 4B and CM4:

```bash
sudo apt install -y "linux-headers-$(uname -r)" linux-headers-rpi-v8
```

2\. Clone Pinefeat's driver at the pinned commit.

```bash
git clone https://github.com/pinefeat/cef168.git ~/cef168
git -C ~/cef168 checkout e3abfb2
```

3\. Stage the sources for DKMS. Only `cef168.c` comes from Pinefeat. `Kbuild` and `dkms.conf` come from CineMate.

```bash
sudo mkdir -p /usr/src/cef168-1.0
sudo cp ~/cef168/cef168.c ~/cinemate/resources/overlays/cef168/Kbuild ~/cinemate/resources/overlays/cef168/dkms.conf /usr/src/cef168-1.0/
```

4\. Build and install.

```bash
sudo dkms add -m cef168 -v 1.0
sudo dkms build -m cef168 -v 1.0
sudo dkms install -m cef168 -v 1.0
```

5\. Check the module.

```bash
sudo dkms status | grep cef168
~/cinemate/scripts/cef168-module-installed.sh -v
```

6\. Compile and install the overlay.

```bash
dtc -@ -I dts -O dtb -W no-unit_address_vs_reg -o /tmp/cef168.dtbo ~/cinemate/resources/overlays/cef168/cef168-overlay.dts
sudo install -m 644 /tmp/cef168.dtbo /boot/firmware/overlays/cef168.dtbo
```

7\. Add the line to `/boot/firmware/config.txt`, **outside** the CineMate block, at the end of the file. The block is rewritten by the installer and the settings editor, which would remove it.

| Sensor | Its own line | Add this line |
|---|---|---|
| imx477 | `dtoverlay=imx477,cam0` | `dtoverlay=cef168,cam0,imx477` |
| imx296 | `dtoverlay=imx296,cam0` | `dtoverlay=cef168,cam0,imx296` |
| imx283 | `dtoverlay=imx283,cam0` | `dtoverlay=cef168,cam0,imx283` |
| imx585 | `dtoverlay=imx585,cam1,ccmp` | `dtoverlay=cef168,cam1,imx585` |
| imx585 mono | `dtoverlay=imx585,cam1,mono,ccmp` | `dtoverlay=cef168,cam1,imx585` |

Rules:

| Rule | Why |
|---|---|
| The port (`cam0` or `cam1`) matches the sensor's line | The lens must sit on the same I²C bus as the sensor |
| Last word is the sensor name, `imx585` for colour and mono | It tells the overlay which sensor node gets `lens-focus` |
| Pi 4B: leave the port out | One port, same as the stock sensor overlays |
| Order against the sensor line does not matter | The overlay merges into the sensor node whichever loads first |
| Dual sensors | One `cef168` line per port that has an adapter |

8\. Reboot, then verify.

```bash
export DEV_MEDIA=$(v4l2-ctl --list-devices | awk '/unicam|rp1-cfe/ {found=1} found && /\/dev\/media/ {print; exit;}')
export DEV_LENS=$(media-ctl -d $DEV_MEDIA -p | awk '/entity.*cef168.*-000d/ {found=1} found && /\/dev\/v4l-subdev/ {print $4; exit;}')
echo $DEV_LENS
v4l2-ctl -d $DEV_LENS --list-ctrls
```

The two `export` lines are Pinefeat's. `DEV_LENS` prints a `/dev/v4l-subdevN` path, and the control list names `focus_absolute`, `iris_absolute` and `calibrate`. No path means the lens is not in the camera's media graph: [Compatibility](compatibility.md#troubleshooting).

## Undoing Pinefeat's installer

Pinefeat's own `configure.sh` and `make install` work differently from CineMate's overlay.

| Pinefeat's installer | CineMate's overlay |
|---|---|
| Rewrites the **sensor's** overlay in `/boot/firmware/overlays/<sensor>.dtbo` | Adds one separate file, `cef168.dtbo` |
| Backs the old file up as `<sensor>.dtbo.~1~`, `.~2~`, ... | Nothing to back up |
| A firmware upgrade overwrites the patched file and the lens vanishes | A firmware upgrade does not touch `cef168.dtbo` |
| Downloads the sensor overlay from Raspberry Pi's tree | Never replaces a sensor overlay, including CineMate's own imx585 and imx283 |
| The sensor overlay declares the lens **always** | CineMate loads the lens overlay only when the module exists |

Undo Pinefeat's patch before the driver level. With both in place the two declarations merge into one lens node, so it may even work. But the sensor overlay then declares the lens whether or not `cef168.ko` exists for the running kernel. After a kernel update without a rebuilt module the camera would not register, and CineMate cannot prevent that. A firmware upgrade would also quietly drop Pinefeat's half.

1\. Find the patched files and their backups. The patched file contains `pinefeat,cef168`; the stock backup does not.

```bash
sudo grep -al pinefeat,cef168 /boot/firmware/overlays/*.dtbo*
ls -l /boot/firmware/overlays/*.dtbo.~*~
```

2\. Restore the backup that does **not** appear in the first list. `~1~` is the oldest and is the stock file if Pinefeat's installer was only run once.

```bash
sudo cp /boot/firmware/overlays/imx477.dtbo.~1~ /boot/firmware/overlays/imx477.dtbo
```

3\. imx585 and imx283 (CineMate's own overlays): if no clean backup exists, reinstall the sensor driver from [Manual installation](../installation-steps.md#imx283-and-imx585-sensor-support). That rewrites the overlay.

4\. Pinefeat's `make install` also copied `cef168.ko` into `/lib/modules/<kernel>/kernel/drivers/media/i2c/`. That copy is not rebuilt for new kernels. Once the DKMS copy is installed, remove it:

```bash
sudo rm -f /lib/modules/$(uname -r)/kernel/drivers/media/i2c/cef168.ko*
sudo depmod -a
```

5\. Reboot.

## Kernel and firmware updates

| Event | What happens | You do |
|---|---|---|
| Kernel update, Pi 4B and CM4 | DKMS rebuilds `cef168.ko` for the new kernel, if its headers are installed. The installer installs the `linux-headers-rpi-v8` package so they arrive with the kernel. | Check with `sudo dkms status`. If a kernel shows no `cef168`: `sudo dkms autoinstall -k <kernel>`. |
| Kernel update, Pi 5 and CM5 | CineMate pins the kernel, so nothing changes. | Nothing |
| Firmware upgrade | `cef168.dtbo` is a separate file and is left alone. | Nothing |
| Pinned driver commit changes in a CineMate update | Rebuild with the script. | `scripts/install-cef168.sh` |

## Removing it

```bash
# 1. delete the dtoverlay=cef168 line from /boot/firmware/config.txt
sudo dkms remove -m cef168 -v 1.0 --all
sudo rm -rf /usr/src/cef168-1.0
sudo rm -f /boot/firmware/overlays/cef168.dtbo
sudo reboot
```

Basic use keeps working. The raw I²C way needs none of these files.
