# Installation
This page starts with the repo-root one-click installer and then continues with the full step-by-step manual install for libcamera, cinepi-raw, cinemate and accompanying software on the Raspberry Pi.

!!! Note ""

     Stack works on Raspberry Pi 4 and 5 models. 2 GB RAM is sufficient, while more RAM will give you a larger framebuffer. Useful at high frame rates.

!!! Note ""

     Cinemate is using Linux kernel version 6.12.25. Supported install target is Raspberry Pi OS Lite (Bookworm).

### One-click installer

If you want the automated path, install `git`, clone the repo, and run the repo-root installer instead of stepping through the whole page by hand:

```bash
sudo apt update
sudo apt install -y git
cd /home/pi
git clone https://github.com/Tiramisioux/cinemate.git
cd /home/pi/cinemate
chmod +x cinemate-install.sh
./cinemate-install.sh
```

The default installer profile is `imx477` on `cam0` with the boot framebuffer pinned to `HDMI-A-1`.

The script applies the full manual flow from this guide in the same order, including `storage-automount`, `wifi-hotspot`, and `redis-log-maintenance`, plus the optional console-font, PiShrink, Plymouth, and IMX585 helper steps. It is intended for Raspberry Pi OS Lite (Bookworm), stops early on unsupported releases such as Trixie, aligns Raspberry Pi 5 / CM5 installs to the known-good `6.12.25+rpt-rpi-2712` kernel baseline, builds Will Whang's `libcamera` fork at commit `9d0cdfe5`, and then builds `cinepi-raw` with the matching local `rpicam-*` utilities under `/usr/local/bin`. It installs the required stack libraries on top of a Lite system, not a full desktop image, creates `~/.cinemate-env`, auto-activates it from `.bashrc`, adds a `cinemate-env` helper alias so you can reactivate it after `deactivate`, and writes `/home/pi/compile-raw.sh` as a reusable cinepi-raw rebuild helper. If you stay in the same shell after the installer finishes, run `source ~/.bashrc` once to load the aliases right away. If you want the script to perform the manual reboot steps automatically too, run it as `RUN_REBOOT=1 ./cinemate-install.sh`. Set `SENSOR_MODEL`, `CAM_PORT`, and `HDMI_BOOT_PORT` at the top of the script or override them inline, for example:

```bash
SENSOR_MODEL=imx585_mono CAM_PORT=cam1 HDMI_BOOT_PORT=1 ./cinemate-install.sh
```

### Manual install starts here

If you prefer to install everything by hand, continue with the steps below.

Start from a fresh Raspberry Pi OS Lite (Bookworm) install before continuing. If your Pi is already on Trixie, reimage with Bookworm first.

```
sudo apt update -y
sudo apt upgrade -y
```

### Kernel baseline (Raspberry Pi 5 / CM5)

Fresh Bookworm Pi 5 images currently boot a newer kernel than the one Cinemate is validated against. Before building `libcamera`, `cinepi-raw`, or the IMX585 driver, roll the Pi 5 kernel and firmware back to the known-good baseline and make the new boot files stick in `/boot/firmware`.

Skip this section on Pi 4.

```bash
mkdir -p ~/kernel-rollback-6.12.25
cd ~/kernel-rollback-6.12.25

curl -LO https://archive.raspberrypi.com/debian/pool/main/l/linux/linux-support-6.12.25+rpt_6.12.25-1+rpt1_all.deb
curl -LO https://archive.raspberrypi.com/debian/pool/main/l/linux/linux-image-6.12.25+rpt-rpi-2712_6.12.25-1+rpt1_arm64.deb
curl -LO https://archive.raspberrypi.com/debian/pool/main/l/linux/linux-image-rpi-2712_6.12.25-1+rpt1_arm64.deb
curl -LO https://archive.raspberrypi.com/debian/pool/main/l/linux/linux-headers-6.12.25+rpt-rpi-2712_6.12.25-1+rpt1_arm64.deb
curl -LO https://archive.raspberrypi.com/debian/pool/main/l/linux/linux-headers-rpi-2712_6.12.25-1+rpt1_arm64.deb
curl -LO https://archive.raspberrypi.com/debian/pool/untested/r/raspi-firmware/raspi-firmware_1.20250430-1_all.deb

sudo apt install -y --allow-downgrades ./*.deb
sudo update-initramfs -u -k 6.12.25+rpt-rpi-2712
sudo cp /boot/vmlinuz-6.12.25+rpt-rpi-2712 /boot/firmware/kernel_2712.img
sudo cp /boot/initrd.img-6.12.25+rpt-rpi-2712 /boot/firmware/initramfs_2712
sudo apt-mark hold \
  raspi-firmware \
  linux-support-6.12.25+rpt \
  linux-image-6.12.25+rpt-rpi-2712 \
  linux-image-rpi-2712 \
  linux-headers-6.12.25+rpt-rpi-2712 \
  linux-headers-rpi-2712
sudo reboot
```

After the reboot, verify the rollback before continuing:

```bash
uname -r
```

Expected output on Pi 5:

```text
6.12.25+rpt-rpi-2712
```

```bash
sudo apt-get install python3-jinja2 python3-ply python3-yaml ffmpeg
```

```
sudo apt install -y git cmake libepoxy-dev libavdevice-dev build-essential cmake libboost-program-options-dev libdrm-dev libexif-dev libcamera-dev libjpeg-dev libtiff5-dev libpng-dev redis-server libhiredis-dev libasound2-dev libjsoncpp-dev libpng-dev meson ninja-build libavcodec-dev libavdevice-dev libavformat-dev libswresample-dev ffmpeg && sudo apt-get install libjsoncpp-dev && cd ~ && git clone https://github.com/sewenew/redis-plus-plus.git && cd redis-plus-plus && mkdir build && cd build && cmake .. && make && sudo make install && cd ~
```

### libcamera (Will Whang fork pinned to `9d0cdfe5`) <img src="https://img.shields.io/badge/cinemate-fork-gren" height="12" >

If you are already inside `~/.cinemate-env`, either run `deactivate` before building `libcamera` or install the Python helpers into that environment with `pip install PyYAML ply Jinja2` first.

```shell
sudo apt install -y python3-pip python3-jinja2 libboost-dev libgnutls28-dev openssl pybind11-dev qtbase5-dev libqt5core5a meson cmake python3-yaml python3-ply libglib2.0-dev libgstreamer-plugins-base1.0-dev libgstreamer1.0-dev libavdevice59
```

```shell
sudo apt-get install --reinstall libtiff5-dev && sudo ln -sf $(find /usr/lib -name "libtiff.so" | head -n 1) /usr/lib/aarch64-linux-gnu/libtiff.so.5 && export LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu:$LD_LIBRARY_PATH && sudo ldconfig
```

```shell
git clone https://github.com/will127534/libcamera.git && \
cd libcamera && \
git checkout 9d0cdfe5 && \
find ~/libcamera -type f \( -name '*.py' -o -name '*.sh' \) -exec chmod +x {} \; && \
chmod +x ~/libcamera/src/ipa/ipa-sign.sh && \
meson setup build --buildtype=release \
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
ninja -C build && \
sudo ninja -C build install && \
sudo ldconfig
```

```shell
git -C ~/libcamera rev-parse --short HEAD
find ~/libcamera/src/ipa/rpi/cam_helper -name '*imx585*'
```

Expected output:

```text
9d0cdfe5
/home/pi/libcamera/src/ipa/rpi/cam_helper/cam_helper_imx585.cpp
```

### cpp-mjpeg-streamer

```bash
sudo apt install -y libspdlog-dev libjsoncpp-dev && cd /home/pi && git clone https://github.com/nadjieb/cpp-mjpeg-streamer.git && cd cpp-mjpeg-streamer && mkdir build && cd build && cmake .. && make && sudo make install && cd
```

### CinePi-RAW <img src="https://img.shields.io/badge/cinemate-fork-gren" height="12" >

WAV BEXT/iXML timecode metadata requires the `ffmpeg` package from the dependency step above.

```bash
git clone https://github.com/Tiramisioux/cinepi-raw.git
cat > /home/pi/compile-raw.sh <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

CINEPI_RAW_DIR="${CINEPI_RAW_DIR:-/home/pi/cinepi-raw}"
CPP_MJPEG_STREAMER_DIR="${CPP_MJPEG_STREAMER_DIR:-/home/pi/cpp-mjpeg-streamer}"
BUILD_JOBS="${BUILD_JOBS:-$(nproc 2>/dev/null || printf '4')}"
BUILD_DIR="${BUILD_DIR:-$CINEPI_RAW_DIR/build}"
PKG_CONFIG_PATH="$CPP_MJPEG_STREAMER_DIR/build:${PKG_CONFIG_PATH:-}"
export PKG_CONFIG_PATH

printf '[compile-raw] Source: %s\n' "$CINEPI_RAW_DIR"
printf '[compile-raw] Build directory: %s\n' "$BUILD_DIR"
printf '[compile-raw] Using PKG_CONFIG_PATH=%s\n' "$PKG_CONFIG_PATH"
printf '[compile-raw] Running meson setup --wipe\n'
meson setup "$BUILD_DIR" "$CINEPI_RAW_DIR" --wipe
printf '[compile-raw] Building with ninja (%s jobs)\n' "$BUILD_JOBS"
ninja -C "$BUILD_DIR" -j "$BUILD_JOBS"
printf '[compile-raw] Installing cinepi-raw\n'
sudo env PKG_CONFIG_PATH="$PKG_CONFIG_PATH" meson install -C "$BUILD_DIR"
printf '[compile-raw] Refreshing linker cache\n'
sudo ldconfig
EOF
chmod +x /home/pi/compile-raw.sh
/home/pi/compile-raw.sh
```

You can rerun `/home/pi/compile-raw.sh` later whenever you need to rebuild `cinepi-raw`.

The `cinepi-raw` build now also installs the matching `rpicam-*` utilities into `/usr/local/bin`. Verify that the local binary wins over the distro one:

```bash
command -v rpicam-hello
/usr/local/bin/rpicam-hello --version
```

### Seed Redis with white balance default keys

```
redis-cli <<EOF
SET cg_rb 3.5,1.5
PUBLISH cp_controls cg_rb
EOF
```

### .asoundrc Setup

For `dsnoop` support, create a `/etc/asound.conf`:

```bash

    sudo tee /etc/asound.conf >/dev/null <<'EOF'
# RODE NTG path (24-bit stereo)
pcm.mic_dsnoop_24 {
  type dsnoop
  ipc_key 5978
  ipc_perm 0666
  ipc_key_add_uid false
  slave {
    pcm "hw:CARD=NTG,DEV=0"
    format S24_3LE
    rate 48000
    channels 2
  }
  bindings.0 0
  bindings.1 1
}

# Cheap USB path (16-bit mono)
pcm.mic_dsnoop_16 {
  type dsnoop
  ipc_key 5979
  ipc_perm 0666
  ipc_key_add_uid false
  slave {
    pcm "hw:CARD=Device,DEV=0"
    format S16_LE
    rate 48000
    channels 1
  }
  bindings.0 0
}

pcm.mic_24bit { type plug; slave.pcm "mic_dsnoop_24" }
pcm.mic_16bit { type plug; slave.pcm "mic_dsnoop_16" }


EOF

```

Exit nano editor using ctrl+x.

### IMX585 driver (optional)

```shell
sudo apt install dkms -y
```

```
git clone https://github.com/will127534/imx585-v4l2-driver.git --branch 6.12.y
cd imx585-v4l2-driver/
./setup.sh
sudo dkms autoinstall -k 6.12.25+rpt-rpi-2712
cd

```

!!! note ""
    The imx585 is written by Will Whang. For original drivers and startup guides, visit https://github.com/will127534/StarlightEye

#### Install Cinemate IMX585 tuning overrides

Will Whang's `libcamera` fork already contains `imx585` support. These commands overlay Cinemate's local tuning files into both installed IPA directories so the runtime stays aligned with Cinemate's defaults.

```bash
for dir in /usr/local/share/libcamera/ipa/rpi/pisp /usr/local/share/libcamera/ipa/rpi/vc4; do
  sudo install -d -m 755 "$dir"
  sudo install -m 644 /home/pi/cinemate/resources/tuning_files/imx585.json "$dir/imx585.json"
  sudo install -m 644 /home/pi/cinemate/resources/tuning_files/imx585_mono.json "$dir/imx585_mono.json"
done
```
 
#### IR filter switch script

```bash
sudo wget https://raw.githubusercontent.com/will127534/StarlightEye/master/software/IRFilter -O /usr/local/bin/IRFilter
sudo chmod +x /usr/local/bin/IRFilter
```

!!! note ""
    Cinemate has its own way of handling the IR switch but the installation above can be convenient for use outside of Cinemate

### Enabling I²C

```bash
sudo raspi-config nonint do_i2c 0
```
!!! note ""
    Enabling I2C is needed for using the camera modules.

### Setting hostname

```bash
sudo hostnamectl set-hostname cinepi
```
!!! note ""
    You will find the pi as `cinepi.local` on the local network, or at the hotspot Cinemate creates

### Add camera modules to config.txt

```shell
sudo nano /boot/firmware/config.txt
```

Paste this into your file, and uncomment the sensor you are using.

Also specify which physical camera port you have connected your sensor to (example shows imx477 activated)

```bash
# Raspberry Pi HQ camera
camera_auto_detect=1
dtoverlay=imx477,cam0

# Raspberry Pi GS camera
#camera_auto_detect=1
#dtoverlay=imx296,cam0

# OneInchEye
#camera_auto_detect=0
#dtoverlay=imx283,cam0

# StarlightEye
#camera_auto_detect=0
#dtoverlay=imx585,cam0

# StarlightEye Mono
#camera_auto_detect=0
#dtoverlay=imx585,cam1,mono

# CFE Hat (pi 5 only)
dtparam=pciex1
dtparam=pciex1_gen=3

dtoverlay=disable-bt
```

And at the very bottom of the file:

```bash
[all]
avoid_warnings=1
disable_splash=1
```

Exit with Ctrl+x. System will ask you to save the file. Press "y" and then enter.

### Pin the HDMI boot mode for headless startup

On Raspberry Pi Bookworm with KMS enabled, a Pi that boots without a monitor can later hotplug into a fallback mode such as `1024x768`. That makes the GUI and preview appear inside a 4:3 framebuffer even if Cinemate is configured for `1920x1080`.

Edit the kernel command line:

```bash
sudo nano /boot/firmware/cmdline.txt
```

Keep everything on a single line and append the display override at the end:

```text
video=HDMI-A-1:1920x1080M@60D
```

If your monitor is connected to the second full-size/micro-HDMI connector instead, use:

```text
video=HDMI-A-2:1920x1080M@60D
```

!!! note ""
    `cmdline.txt` must stay on a single line. Do not add line breaks.

!!! note ""
    This boot-time `video=` setting pins the framebuffer mode. Cinemate still reads the preferred HDMI canvas and runtime HDMI port from `settings.json`.

### Change the console font (optional)

```bash
sudo apt install console-setup kbd
sudo dpkg-reconfigure console-setup  

# choose: UTF-8
#         Guess optimal character set
#         Terminus
#         16x32 (framebuffer only)
```

Enable the service:

```bash
sudo systemctl enable console-setup.service
sudo systemctl start console-setup.service
```

!!! note ""
    This can be useful if running the Pi on a small HD field monitor

### Create post-processing configs

Paste this into the terminal and hit enter:
```shell
cat > /home/pi/post-processing.json <<'EOF'
{
    "sharedContext": {},
    "mjpegPreview": {
        "port": 8000
    }
}
EOF

cat > /home/pi/post-processing0.json <<'EOF'
{
    "sharedContext": {},
    "mjpegPreview": {
        "port": 8000
    }
}
EOF

cat > /home/pi/post-processing1.json <<'EOF'
{
    "sharedContext": {},
    "mjpegPreview": {
        "port": 8001
    }
}
EOF
```

### Install PiShrink

```bash
sudo wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh -O /usr/local/bin/pishrink.sh
sudo chmod +x /usr/local/bin/pishrink.sh
```

!!! tip ""
    PiShrink is a handy tool for compressing SD image file backups of the SD card. See here for instructions

### Reboot

```bash
sudo reboot
```

### Trying out CinePi from the terminal

You should now have a working install of cinepi-raw. To see if your camera is recognized by the system:

```shell
cinepi-raw --list-cameras
```

Try it out with a simple cli command:

```shell
cinepi-raw --mode 2028:1080:12:U --width 2028 --height 1080 --lores-width 1280 --lores-height 720
```

For more details on running CinePi-raw from the command line, see [this section](/cli-user-guide.md). 

## Cinemate

### System wide packages

```shell
sudo apt update
sudo apt install -y \
    git build-essential python3-dev python3-pip python3-venv \
    i2c-tools python3-smbus python3-pyudev \
    libgpiod-dev libgpiod2 python3-libgpiod gpiod \
    portaudio19-dev python3-systemd \
    e2fsprogs ntfs-3g exfatprogs \
    console-terminus
```

### Create a Python virtual environment

```bash
python3 -m venv ~/.cinemate-env
source /home/pi/.cinemate-env/bin/activate
echo "source /home/pi/.cinemate-env/bin/activate" >> ~/.bashrc
```

### Grant sudo privileges and enable I²C

```bash
echo "pi ALL=(ALL) NOPASSWD: /home/pi/.cinemate-env/bin/*" | sudo tee /etc/sudoers.d/cinemate-env
sudo chown -R pi:pi /home/pi/.cinemate-env
sudo chown -R pi:pi /media && chmod 755 /media
sudo usermod -aG i2c pi
sudo modprobe i2c-dev && echo i2c-dev | sudo tee -a /etc/modules
```
Reboot so the group changes take effect:

```bash
sudo reboot
```

### Python packages

!!! Note ""
    If you previously installed the `board` Python package, remove it with `pip3 uninstall board`.

```bash
pip install \
    gpiozero \
    adafruit-blinka adafruit-circuitpython-ssd1306 adafruit-circuitpython-seesaw \
    luma.oled grove.py pigpio-encoder smbus2 rpi_hardware_pwm \
    watchdog psutil pillow redis keyboard pyudev numpy termcolor sounddevice \
    evdev inotify_simple sysv_ipc flask_socketio sugarpie
```

### Alternative GPIO back-end

```bash
sudo apt install -y swig python3-dev build-essential git
git clone https://github.com/joan2937/lg
cd lg && make
sudo make install
cd .. && pip install lgpio
```

### Clone the Cinemate repo

```bash
sudo apt install -y git
git clone https://github.com/Tiramisioux/cinemate.git
```

### Allow Cinemate to run with sudo

Write the `pi_cinemate` sudoers drop-in and validate it:

```shell
sudo tee /etc/sudoers.d/pi_cinemate <<'EOF'
pi ALL=(ALL) NOPASSWD: /home/pi/run_cinemate.sh
pi ALL=(ALL) NOPASSWD: /home/pi/cinemate/src/main.py
pi ALL=(ALL) NOPASSWD: /bin/mount, /bin/umount, /usr/bin/ntfs-3g
pi ALL=(ALL) NOPASSWD: /sbin/mount.ext4
EOF
sudo visudo -cf /etc/sudoers.d/pi_cinemate
```

### Enable NetworkManager

```bash
sudo systemctl enable NetworkManager --now
```

### Rotate logs

Paste this into the terminal and hit enter:

```bash
sudo tee /etc/logrotate.d/general_logs <<'EOP'
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

```shell
redis-cli MSET \
anamorphic_factor 0 bit_depth 0 buffer 0 buffer_size 0 cam_init 0 cameras 0 cg_rb 3.5,1.5 \
file_size 0 fps 24 fps_actual 24 fps_last 24 fps_max 1 fps_user 24 framecount 0 \
gui_layout 0 height 0 ir_filter 0 is_buffering 0 is_mounted 0 is_recording 0 \
is_writing 0 is_writing_buf 0 tc_cam0 0 tc_cam1 0 iso 100 lores_height 0 lores_width 0 \
pi_model 0 rec 0 sensor 0 sensor_mode 0 shutter_a 0 space_left 0 storage_type 0 \
wb 5600 wb_user 5600 width 0 memory_alert 0 \
shutter_a_sync_mode 0 shutter_angle_nom 0 shutter_angle_actual 0 shutter_angle_transient 0 \
exposure_time 0 last_dng_cam1 0 last_dng_cam0 0 \
zoom 0 write_speed_to_drive 0 recording_time 0
```

(See the settings guide for the full list.)

### Add aliases

```shell
nano ~/.bashrc
```

Add to the end of the file:

```shell
alias cinemate-env='source /home/pi/.cinemate-env/bin/activate'
alias cinemate='/home/pi/run_cinemate.sh'
alias editboot='sudo nano /boot/firmware/config.txt'
alias editcmdline='sudo nano /boot/firmware/cmdline.txt'
alias editsettings='sudo nano /home/pi/cinemate/src/settings.json'
```

Exit with Ctrl+x. System will ask you to save the file. Press "y" and then enter.

Reload .bashrc

```shell
source ~/.bashrc
```

### Match `settings.json` to the HDMI output you want to use

Open the settings file:

```shell
editsettings
```

Make sure the HDMI sections are present and match your install:

```json
"output": {
  "cam0": { "hdmi_port": 0 },
  "cam1": { "hdmi_port": 1 }
},

"hdmi_display": {
  "width": 1920,
  "height": 1080
}
```

Use HDMI port `0` for `HDMI-A-1` and port `1` for `HDMI-A-2`.

!!! note ""
    Current Cinemate builds can start without HDMI attached and recover when HDMI is plugged in later, but the Pi still needs the `video=` entry in `cmdline.txt` above if you want the headless boot framebuffer to come up in `1920x1080` instead of a fallback 4:3 mode.

### Optional: install Plymouth for the boot spinner

If you want the same boot spinner and clean spinner-to-Cinemate handoff as the prebuilt image, install Plymouth before enabling `cinemate-autostart.service`. The Cinemate theme below keeps the spinner centered on the HDMI framebuffer during Pi startup and shutdown, while Cinemate itself shows the welcome message after Plymouth hands off to the app.

Install the required packages:

```bash
sudo apt update
sudo apt install -y plymouth plymouth-themes plymouth-label
```

Install the Cinemate-owned Plymouth theme from this repo and set it as the default:

```bash
sudo install -d -m 755 /usr/share/plymouth/themes/cinemate
sudo install -m 644 resources/plymouth/cinemate/cinemate.plymouth /usr/share/plymouth/themes/cinemate/cinemate.plymouth
sudo install -m 644 resources/plymouth/cinemate/cinemate.script /usr/share/plymouth/themes/cinemate/cinemate.script
```

Then point Plymouth at that theme and scale it up for the Pi display:

```bash
sudo tee /etc/plymouth/plymouthd.conf <<'EOF'
[Daemon]
Theme=cinemate
DeviceScale=4
EOF
```

Make sure `/boot/firmware/cmdline.txt` contains these boot flags on the same single line:

```text
quiet splash loglevel=1 plymouth.ignore-serial-consoles vt.global_cursor_default=0 logo.nologo
```

Keep the `video=HDMI-A-1:1920x1080M@60D` or `video=HDMI-A-2:1920x1080M@60D` override from the HDMI setup above on that same line as well.

Apply the Plymouth theme and rebuild the initramfs:

```bash
sudo plymouth-set-default-theme cinemate
sudo update-initramfs -u
```

After that, reinstall the Cinemate autostart service so the latest `tty1` handoff scripts and Plymouth ordering are installed:

```bash
cd /home/pi/cinemate
sudo make install
sudo make enable
```

Reboot to test:

```bash
sudo reboot
```

If you skip Plymouth, Cinemate still works. You just will not get the boot spinner or the same CLI-suppressed boot handoff.
## Cinemate services

#### storage-automount

Mounts and unmounts removable drives such as SSDs, NVMe enclosures and the CFE HAT. 

#### wifi-hotspot

Keeps a simple Wi‑Fi hotspot running via NetworkManager so you can reach the web UI while in the field. The SSID and password come from the `system.wifi_hotspot` section of `settings.json`.

#### redis-log-maintenance

Enables the `redis-log-maintenance.timer`, which periodically trims `/var/log/redis/redis-server.log` and removes old Redis log rotations so the Pi root filesystem does not slowly fill up.

Install and enable the support services with:

```bash
cd /home/pi/cinemate/services
```

```
sudo make install
sudo make start  # starts storage-automount and wifi-hotspot now, and runs one redis cleanup pass
sudo make enable # enables storage-automount, wifi-hotspot, and redis-log-maintenance.timer on boot
```
You can also start and enable the service individually, by entering their respective folders and issuing the `sudo make` command

When you install `storage-automount`, it should replace the older `cfe-hat-automount.service`. Do not leave both enabled at the same time, or `/media/RAW` can be mounted and then immediately unmounted again during boot.

Note that if you were connected to the Pi via wifi, this connection is now broken due to the Pi setting up its own hotspot.

To connect again, check your available wifi networks. There should now be a network available named CinePi. Connect to it using password `11111111`

Now you shuld be able to ssh to the Pi this command:

```shell
ssh pi@cinepi.local
```

You should also be able to find the Pi by opening a terminal and typing:

```shell
arp -a
```

You will see something like
```shell    
❯ arp -a

? (10.42.0.1) at e4:5f:1:a9:72:a7 on en0 ifscope [ethernet]
```

During development/building your rig you might prefer the Pi to use your normal Wi‑Fi instead of its own hotspot so you remain online while tinkering. Disable the hotspot by setting `system.wifi_hotspot.enabled` to `false` in `settings.json` _and_ by stopping the service with: 

```
sudo systemctl stop wifi-hotspot
```

To stop the hotspot from starting on boot, type 

```
sudo systemctl disable wifi-hotspot
```

See [Hotspot logic](hotspot-logic.md) for more details on how the hotspot works.

To inspect the Redis log maintenance timer later:

```bash
systemctl status redis-log-maintenance.timer
journalctl -u redis-log-maintenance.service
```

### Connect to the Pi (if not already connected):

```shell
ssh pi@10.42.0.1
```

password: 1



### Starting Cinemate

Now, back on the Pi, anywhere in the terminal, type:

```shell
cinemate
```

Make sure things are running smoothly and then you can move on to enabling the cinemate-autostart service:

#### cinemate-autostart.service

```shell
cd /home/pi/cinemate/
```

```
sudo make install   # copy service file
sudo make enable    # start on boot
make start          # launch now
```

After enabling the service, Cinemate should autostart on boot.

> **Tip:** `sudo make install` also places `/usr/local/bin/camera-ready.sh`, `/usr/local/bin/cinemate-startup-failure-display.sh`, and `/usr/local/bin/cinemate-console-handoff.sh` on the system. The camera-ready helper waits for `cinepi-raw` to report a camera before systemd launches Cinemate, the startup-failure helper preserves early crash diagnostics on `tty1`, and the console-handoff helper restores the CLI on a normal Cinemate stop while leaving `tty1` available for Plymouth during full system shutdown.

You now have a 12 bit RAW image capturing system on your Raspberry Pi!
