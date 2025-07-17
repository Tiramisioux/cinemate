# Installing CinePi and Cinemate

This guide walks you through installing the `cinepi-raw` fork and the Cinemate UI on a fresh Bookworm installation. Lite version of Bookworm also works.

## Prerequisites

If you run Raspberry Pi OS Lite, begin by installing the following packages:

```bash
sudo apt install -y python-pip git python3-jinja2
```

### libcamera

```shell
git clone https://github.com/raspberrypi/libcamera && \
sudo find ~/libcamera -type f \( -name '*.py' -o -name '*.sh' \) -exec chmod +x {} \; && \
cd libcamera && \
sudo meson setup build --buildtype=release \
  -Dpipelines=rpi/vc4,rpi/pisp \
  -Dipas=rpi/vc4,rpi/pisp \
  -Dv4l2=true \
  -Dgstreamer=enabled \
  -Dtest=false \
  -Dlc-compliance=disabled \
  -Dcam=disabled \
  -Dqcam=disabled \
  -Ddocumentation=disabled \
  -Dpycamera=enabled && \
sudo ninja -C build install && \
cd
```

```shell
cd ~/libcamera/utils && sudo chmod +x *.py *.sh && sudo chmod +x ~/libcamera/src/ipa/ipa-sign.sh && cd ~/libcamera && sudo ninja -C build install
```

```shell
sudo apt-get install --reinstall libtiff5-dev && sudo ln -sf $(find /usr/lib -name "libtiff.so" | head -n 1) /usr/lib/aarch64-linux-gnu/libtiff.so.5 && export LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu:$LD_LIBRARY_PATH && sudo ldconfig
```

```shell
sudo apt install -y python3-pip git python3-jinja2 libboost-dev libgnutls28-dev openssl pybind11-dev qtbase5-dev libqt5core5a meson cmake python3-yaml python3-ply libglib2.0-dev libgstreamer-plugins-base1.0-dev libgstreamer1.0-dev libavdevice59
```

### Node Version Manager

```bash
wget -qO- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc
nvm install --lts
```

### cpp-mjpeg-streamer <img src="https://img.shields.io/badge/cinemate-fork-gren" height="10" >

```bash
sudo apt install -y libspdlog-dev libjsoncpp-dev
cd /home/pi
git clone https://github.com/Tiramisioux/cpp-mjpeg-streamer.git --branch cinemate
cd cpp-mjpeg-streamer && mkdir build && cd build
cmake .. && make
make install-here
```

## cinepi-raw <img src="https://img.shields.io/badge/cinemate-fork-gren" height="10" >

Cinemate depends on a custom branch of [cinepi-raw](https://github.com/Tiramisioux/cinepi-raw/tree/rpicam-apps_1.7_custom_encoder, created by Csaba Nagy.

```bash
git clone https://github.com/Tiramisioux/cinepi-raw.git --branch rpicam-apps_1.7_custom_encoder
cd /home/pi/cinepi-raw
sudo rm -rf build (if you have a previous build)
export PKG_CONFIG_PATH=/home/pi/cpp-mjpeg-streamer/build:$PKG_CONFIG_PATH
sudo meson setup build
sudo ninja -C build
meson install -C build
```
>Join the CinePi Discord [here](https://discord.gg/Hr4dfhuK)!

## Configuring the Raspberry Pi

### Update & enable I²C and setting hostname
```bash
sudo apt update && apt upgrade
sudo raspi-config nonint do_i2c 0
sudo hostnamectl set-hostname cinepi
```
>Now you will find the pi as `cinepi.local` on the local network, or at the hotspot Cinemate creates

### Update `/boot/firmware/config.txt`

```shell
sudo nano /boot/firmware/config.txt
```

Paste this into your file, and uncomment the sensor you are using.

Also specify which physical camera port you have connected your sensor to.

```bash
# Raspberry Pi HQ camera
#camera_auto_detect=1
#dtoverlay=imx477,cam0

# Raspberry Pi GS camera
#camera_auto_detect=1
#dtoverlay=imx296,cam0

# OneInchEye
#camera_auto_detect=0
#dtoverlay=imx283,cam0

# StarlightEye
camera_auto_detect=0
dtoverlay=imx585,cam0

# StarlightEye Mono
camera_auto_detect=0
#dtoverlay=imx585,cam1,mono

# CFE Hat (pi 5 only)
dtparam=pciex1
dtparam=pciex1_gen=3

dtoverlay=disable-bt

[cm4]
# Enable host mode on the 2711 built-in XHCI USB controller.
# This line should be removed if the legacy DWC2 controller is required
# (e.g. for USB device mode) or if USB support is not required.
otg_mode=1

[all]
usb_max_current_enable=1
#dtoverlay=vc4-kms-DPI-4inch
#dtoverlay=waveshare-touch-4dpi
avoid_warnings=1
disable_splash=1
#boot_delay=0
#power_off_on_halt=1
```

### Add the IMX585 tuning file (optional)

```bash
curl -L -o /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585.json \
  https://raw.githubusercontent.com/will127534/libcamera/master/src/ipa/rpi/pisp/data/imx585.json
sed -i '8s/"black_level": *[0-9]\+/"black_level": 0/' /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585.json
# cp /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585.json /usr/local/share/libcamera/ipa/rpi/pisp/
```
For the mono sensor use `imx585_mono.json` instead.
 
### IR filter switch script (optional)

```bash
wget https://raw.githubusercontent.com/will127534/StarlightEye/master/software/IRFilter -O /usr/local/bin/IRFilter
sudo chmod +x /usr/local/bin/IRFilter
```

>Cinemate has its own way of handling the IR switch but the installation above can be convenient for use outside of Cinemate

### Change the console font (optional)

This can be useful if running the Pi on a small HD field monitor

```bash
sudi apt update
sudo apt install console-setup kbd
sudo dpkg-reconfigure console-setup  # choose Terminus / 16x32
```

Verify `/etc/default/console-setup` contains:
```text
FONTFACE="Terminus"
FONTSIZE="16x32"
```
Then enable the service:
```bash
sudo systemctl enable console-setup.service
sudo systemctl start console-setup.service
```

### Create post-processing configs

Paste this into the terminal and hit enter:
```shell
sudo bash -c 'cat > post-processing.json << EOF
{
    "sharedContext": {},
    "mjpegPreview": {
        "port": 8000
    }
}
EOF' && \
sudo chmod +x post-processing.json && \
sudo bash -c 'cat > post-processing0.json << EOF
{
    "sharedContext": {},
    "mjpegPreview": {
        "port": 8000
    }
}
EOF' && \
sudo chmod +x post-processing0.json && \
sudo bash -c 'cat > post-processing1.json << EOF
{
    "sharedContext": {},
    "mjpegPreview": {
        "port": 8001
    }
}
EOF' && \
sudo chmod +x post-processing1.json
```

### Install PiShrink

```bash
wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
sudo install -m755 pishrink.sh /usr/local/bin/pishrink
```

Reboot before installing Cinemate:

```bash
reboot
```

## Install Cinemate

### Create a Python virtual environment

```bash
sudo apt update && apt install -y python3-venv
python3 -m venv /home/pi/.Cinemate-env
echo "source /home/pi/.Cinemate-env/bin/activate" >> ~/.bashrc
source /home/pi/.Cinemate-env/bin/activate
```

### Grant sudo privileges and enable I²C

```bash
echo "pi ALL=(ALL) NOPASSWD: /home/pi/.Cinemate-env/bin/*" | sudo tee /etc/sudoers.d/Cinemate-env
sudo chown -R pi:pi /home/pi/.Cinemate-env
sudo chown -R pi:pi /media && chmod 755 /media
sudo usermod -aG i2c pi
sudo modprobe i2c-dev && echo i2c-dev | sudo tee -a /etc/modules
echo "pi ALL=(ALL) NOPASSWD: /home/pi/run_Cinemate.sh" | sudo tee -a /etc/sudoers.d/pi_Cinemate
```
Reboot so the group changes take effect:

```bash
reboot
```

### Install dependencies

```bash
source /home/pi/.Cinemate-env/bin/activate
python3 -m pip install --upgrade pip setuptools wheel
sudo apt-get install -y i2c-tools portaudio19-dev build-essential python3-dev python3-pip python3-smbus python3-serial git
pip3 install adafruit-circuitpython-ssd1306 watchdog psutil Pillow redis keyboard pyudev sounddevice smbus2 gpiozero RPI.GPIO evdev termcolor pyserial inotify_simple numpy rpi_hardware_pwm
pip3 uninstall -y Pillow && pip3 install Pillow
pip3 install sugarpie flask_socketio board adafruit-blinka adafruit-circuitpython-seesaw luma.oled grove.py pigpio-encoder gpiod
sudo apt install python3-systemd e2fsprogs ntfs-3g exfatprogs console-terminus
```

### Replace RPi.GPIO with lgpio

```bash
sudo apt install -y swig python3-dev build-essential git
git clone https://github.com/joan2937/lg
cd lg && make
sudo make install
cd .. && pip install lgpio
```

### Clone the Cinemate repo

```bash
git clone https://github.com/Tiramisioux/Cinemate.git
```

### Allow `main.py` to run with sudo

Edit the sudoers file:

```shell
sudo visudo
```

add this to the end of the file:
```text
pi ALL=(ALL) NOPASSWD: /home/pi/Cinemate/src/main.py
pi ALL=(ALL) NOPASSWD: /bin/mount, /bin/umount, /usr/bin/ntfs-3g
pi ALL=(ALL) NOPASSWD: /home/pi/Cinemate/src/logs/system.log
pi ALL=(ALL) NOPASSWD: /sbin/mount.ext4
```

### Enable NetworkManager

```bash
sudo systemctl enable NetworkManager --now
```

### Rotate logs

Paste this into the terminal and hit enter:

```bash
# tee /etc/logrotate.d/general_logs <<'EOP'
/var/log/*.log {
   size 100M
   rotate 5
   compress
   missingok
   notifempty
}
EOP
```

### Seed Redis with default keys

```bash
redis-cli <<'EOF'
SET anamorphic_factor 1.0
PUBLISH cp_controls anamorphic_factor
SET bit_depth 12
PUBLISH cp_controls bit_depth
...
EOF
```

(See the settings guide for the full list.)

### Add a convenience alias

Append to `~/.bashrc`:

```bash
alias Cinemate='python3 /home/pi/Cinemate/src/main.py'
```
Then, inside `cinemate` folder:

```shell
make install
```

### Install the Cinemate services

Cinemate with two small helper services under `services/`:

- **storage-automount** – mounts and unmounts removable drives such as SSDs,
  NVMe enclosures and the CFE HAT. Partitions named `RAW` are attached at
  `/media/RAW`; all others are mounted under `/media/<LABEL>`.
- **wifi-hotspot** – keeps a simple Wi‑Fi hotspot running via NetworkManager so
  you can reach the web UI even without other networking. The SSID and password
  come from the `system.wifi_hotspot` section of `settings.json`.

Install and enable both services with:

```bash
cd /home/pi/Cinemate/services
sudo make install
sudo make enable
```

You can manage each one individually with `make <action>-<service>`, for example
`make status-wifi-hotspot`.

## Backing up the SD card

Create a compressed image:

```bash
sudo dd if=/dev/mmcblk0 bs=4M conv=sparse,noerror status=progress | \ gzip -c > /media/RAW/Cinemate_$(date +"%Y%m%d_%H%M%S").img.gz
```

Or use PiShrink for a smaller file:

```bash
sudo bash -euo pipefail -c '
  ts=$(date +%Y%m%d_%H%M%S)
  raw="/media/RAW/Cinemate_${ts}.img"
  final="/media/RAW/Cinemate_${ts}.img.gz"
  dd if=/dev/mmcblk0 of="$raw" bs=4M conv=sparse,noerror status=progress
  pishrink.sh -v -z "$raw" "$final"
  rm -f "$raw"
'
```

You now have cinepi-raw and Cinemate installed on your Raspberry Pi. Happy shooting!

## Starting Cinemate

If you are not using the service file for autostart, anywhere in the terminal, type:

```shell
cinemate
```

>This would be the recommended way of trying out Cinemate as you will get extended logging in the terminal which can be helpful when troubleshooting. The Cinemate logger also relays logging messages from the running cinepi-raw instance.

# Extra stuff

## Hotspot logic
If `wifi_hotspot` in `settings.json` is `true` and no hotspot is active, Cinemate starts its own hotspot `nmcli device wifi hotspot` using your chosen SSID and password. If the Pi is already connected to wifi (for example WiFi settings set with `sudo raspi-config`) this connection will be replaced by Cinemates hotspot. Set `enabled: false` to keep wlan0 free for regular Wi‑Fi use. 

>Note that Cinemate still streams its web gui on whatever network the Pi is connected to, with GUI at <ip-address>:5000 and clean preview without GUI on <ip-address>:8000/stream

## Building cinepi-raw

For easy later rebuilding and installation of cinepi-raw you can create this file [to be added]

## Managing the cinemate-autostart service

```bash
# Here are the available Make commands for managing the service:

make install   # copy service file
make enable    # start on boot
make start     # launch now
make stop      # stop it
make status    # check status
make disable   # disable autostart
make clean     # remove the service
```

Note that in order for the web ui to work properly you have to run `make install` once in the `/home/pi/cinemate` folder, even if you are not using the autostart service.

## Managing the storage-automount and wifi-hotspot services

Cinemate ships with two small helper services under `services/`:

- **storage-automount** – mounts and unmounts removable drives such as SSDs,
  NVMe enclosures and the CFE HAT. Partitions named `RAW` are attached at
  `/media/RAW`; all others are mounted under `/media/<LABEL>`.
- **wifi-hotspot** – keeps a simple Wi‑Fi hotspot running via NetworkManager so
  you can reach the web UI even without other networking. The SSID and password
  come from the `system.wifi_hotspot` section of `settings.json`.

Install and enable both services with:

```bash
cd /home/pi/cinemate/services
sudo make install
sudo make enable
```

You can manage each one individually with `make <action>-<service>`, for example
`make status-wifi-hotspot`.

### storage-automount service
`storage-automount` is a systemd service that watches for removable drives and mounts them automatically. The accompanying Python script reacts to udev events and the CFE-HAT eject button so drives can be attached or detached safely.

It understands `ext4`, `ntfs` and `exfat` filesystems. Partitions labelled `RAW` are mounted at `/media/RAW`; any other label is mounted under `/media/<LABEL>` after sanitising the name. This applies to USB SSDs, NVMe drives and the CFE-HAT slot.

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

### wifi-hotspot service
`wifi-hotspot` keeps a small access point running with the help of NetworkManager so you can always reach the web interface. The SSID and password are read from `/home/pi/cinemate/src/settings.json` under `system.wifi_hotspot`.

Install and enable it with:

```bash
cd cinemate/services/wifi-hotspot
sudo make install
sudo make enable
```

As with `storage-automount`, you can stop or disable the hotspot with `make stop` and `make disable`.