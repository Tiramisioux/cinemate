# Installation
This page starts with the repo-root one-click installer and then continues with the full step-by-step manual install for libcamera, cinepi-raw, cinemate and accompanying software on the Raspberry Pi.

!!! Note ""

     Stack works on Raspberry Pi 4 and 5 models. The 2GB RAM version works with the prebuilt image, while 4GB is recommended if you plan to compile `cinepi-raw` on the Pi. More RAM also gives you a larger framebuffer, which can be useful at high frame rates.

!!! Note ""

     Cinemate is using Linux kernel version 6.12.25. Supported install target is Raspberry Pi OS Lite (Bookworm).

### One-click installer

Start from a fresh Raspberry Pi OS Lite Bookworm image. SSH to the Pi:

On macOS, open Terminal and run:

```bash
ssh pi@raspberrypi.local
```

On Windows, open PowerShell or Command Prompt and run:

```powershell
ssh pi@raspberrypi.local
```

Replace `pi` with the username configured in Raspberry Pi Imager if you used a different user. If `raspberrypi.local` does not resolve, use the Pi's IP address instead:

```bash
ssh pi@<pi-ip-address>
```

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/Tiramisioux/cinemate.git
cd cinemate
chmod +x cinemate-install.sh
./cinemate-install.sh
```

The installer defaults to an `imx477` on camera port `cam0` and writes a stock-style managed `/boot/firmware/config.txt` section with camera options for IMX477, IMX296, IMX283, IMX585 color, and IMX585 mono. To install directly for another sensor, pass `SENSOR_MODEL` and `CAM_PORT` inline:

```bash
SENSOR_MODEL=imx296 CAM_PORT=cam0 ./cinemate-install.sh
SENSOR_MODEL=imx283 CAM_PORT=cam0 ./cinemate-install.sh
SENSOR_MODEL=imx585 CAM_PORT=cam0 ./cinemate-install.sh
SENSOR_MODEL=imx585_mono CAM_PORT=cam1 ./cinemate-install.sh
```

After installing, reboot the system and Cinemate should start automatically.

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

### libcamera (Will Whang fork pinned to `ea5abb8b`) <img src="https://img.shields.io/badge/cinemate-fork-gren" height="12" >

This fork includes the following patches on top of the Raspberry Pi upstream:

| Commit | Change |
|--------|--------|
| `97f71626` | IMX585: exact pinned frame rate via VMAX/HMAX lattice search — eliminates ~440 ppm quantisation drift at 25 fps |
| `ea5abb8b` | IMX294/IMX492: same exact frame-rate algorithm (72 MHz clock) |

Also included between those two commits: IMX585 AGC gain profile widened from 8× to 16×, and sensor test-pattern mode support for IMX585/IMX294/IMX492.

**On the Pi, to update an existing install:**

If you are inside `~/.cinemate-env`, meson will use the virtualenv Python and will fail with *"Python module yaml not found"* unless the helpers are present. Install them first:

```shell
pip install PyYAML ply Jinja2
```

Then update and rebuild:

```shell
cd ~/libcamera && \
git config core.fileMode false && \
git fetch origin && \
git stash || true && \
git checkout ea5abb8b && \
find ~/libcamera -type f \( -name '*.py' -o -name '*.sh' \) -exec chmod +x {} \; && \
chmod +x ~/libcamera/src/ipa/ipa-sign.sh && \
meson setup build --wipe --buildtype=release \
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
sudo ldconfig && \
sudo systemctl restart cinepi-raw
```

`git config core.fileMode false` silences the executable-bit changes that the build leaves behind on Python files (a Linux-only git behaviour). `git stash` clears any remaining real content changes such as tuning JSONs so the checkout cannot be blocked.

**Fresh install:**

If you are already inside `~/.cinemate-env`, either run `deactivate` before building `libcamera` or install the Python helpers into that environment with `pip install PyYAML ply Jinja2` first.

```shell
sudo apt install -y python3-pip python3-jinja2 libboost-dev libgnutls28-dev openssl pybind11-dev qtbase5-dev libqt5core5a meson cmake python3-yaml python3-ply libglib2.0-dev libgstreamer-plugins-base1.0-dev libgstreamer1.0-dev libavdevice59 libyaml-dev
```

```shell
sudo apt-get install --reinstall libtiff5-dev && sudo ln -sf $(find /usr/lib -name "libtiff.so" | head -n 1) /usr/lib/aarch64-linux-gnu/libtiff.so.5 && export LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu:$LD_LIBRARY_PATH && sudo ldconfig
```

```shell
git clone https://github.com/will127534/libcamera.git && \
cd libcamera && \
git checkout ea5abb8b && \
find ~/libcamera -type f \( -name '*.py' -o -name '*.sh' \) -exec chmod +x {} \; && \
chmod +x ~/libcamera/src/ipa/ipa-sign.sh && \
meson setup build --wipe --buildtype=release \
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
find ~/libcamera/src/ipa/rpi/cam_helper -name '*imx585*' -o -name '*imx294*' -o -name '*imx492*'
```

Expected output:

```text
ea5abb8b
/home/pi/libcamera/src/ipa/rpi/cam_helper/cam_helper_imx294.cpp
/home/pi/libcamera/src/ipa/rpi/cam_helper/cam_helper_imx492.cpp
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
FORCE_WIPE="${FORCE_WIPE:-0}"

is_true() {
    case "${1,,}" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
}

build_dir_has_entries() {
    [[ -d "$1" ]] || return 1
    find "$1" -mindepth 1 -maxdepth 1 -print -quit | grep -q .
}

printf '[compile-raw] Source: %s\n' "$CINEPI_RAW_DIR"
printf '[compile-raw] Build directory: %s\n' "$BUILD_DIR"
printf '[compile-raw] Using PKG_CONFIG_PATH=%s\n' "$PKG_CONFIG_PATH"
if is_true "$FORCE_WIPE"; then
  printf '[compile-raw] FORCE_WIPE requested; running meson setup --wipe\n'
  meson setup "$BUILD_DIR" "$CINEPI_RAW_DIR" --wipe
elif [[ -f "$BUILD_DIR/build.ninja" || -f "$BUILD_DIR/meson-private/coredata.dat" ]]; then
  printf '[compile-raw] Reusing existing Meson build directory with --reconfigure\n'
  if ! meson setup "$BUILD_DIR" "$CINEPI_RAW_DIR" --reconfigure; then
    printf '[compile-raw] Reconfigure failed; retrying with --wipe\n'
    meson setup "$BUILD_DIR" "$CINEPI_RAW_DIR" --wipe
  fi
elif build_dir_has_entries "$BUILD_DIR"; then
  printf '[compile-raw] Build directory is non-empty but not reusable; running meson setup --wipe\n'
  meson setup "$BUILD_DIR" "$CINEPI_RAW_DIR" --wipe
else
  printf '[compile-raw] Running initial meson setup\n'
  meson setup "$BUILD_DIR" "$CINEPI_RAW_DIR"
fi
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

You can rerun `/home/pi/compile-raw.sh` later whenever you need to rebuild `cinepi-raw`. If you really do want a clean Meson reconfigure, run `FORCE_WIPE=1 /home/pi/compile-raw.sh`.

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

### IMX283 and IMX585 sensor support

Install both now even if your current default sensor is `imx477` or `imx296`, so later sensor swaps only need a `config.txt` change instead of another driver pass.

```shell
sudo apt install dkms -y
```

```shell
git clone https://github.com/will127534/imx283-v4l2-driver.git --branch 6.12.y
cd imx283-v4l2-driver/
./setup.sh
sudo dkms autoinstall -k 6.12.25+rpt-rpi-2712
cd
```

```shell
git clone https://github.com/will127534/imx585-v4l2-driver.git --branch 6.12.y
cd imx585-v4l2-driver/
./setup.sh
sudo dkms autoinstall -k 6.12.25+rpt-rpi-2712
cd
```

!!! note ""
    The IMX283 and IMX585 DKMS drivers used here are based on Will Whang's work. For the original drivers and startup guides, visit https://github.com/will127534/imx283-v4l2-driver and https://github.com/will127534/imx585-v4l2-driver

#### Install Cinemate IMX283 and IMX585 tuning overrides

These commands overlay Cinemate's local IMX283, IMX585 and IMX585 mono tuning files into both the `libcamera` source tree and the installed IPA directories so the runtime stays aligned with Cinemate's defaults and both sensors stay ready for later swaps.

```bash
for dir in /home/pi/libcamera/src/ipa/rpi/pisp/data /home/pi/libcamera/src/ipa/rpi/vc4/data; do
  install -d -m 755 "$dir"
  install -m 644 /home/pi/cinemate/resources/tuning_files/imx283.json "$dir/imx283.json"
  install -m 644 /home/pi/cinemate/resources/tuning_files/imx585.json "$dir/imx585.json"
  install -m 644 /home/pi/cinemate/resources/tuning_files/imx585_mono.json "$dir/imx585_mono.json"
done

for dir in /usr/local/share/libcamera/ipa/rpi/pisp /usr/local/share/libcamera/ipa/rpi/vc4; do
  sudo install -d -m 755 "$dir"
  sudo install -m 644 /home/pi/cinemate/resources/tuning_files/imx283.json "$dir/imx283.json"
  sudo install -m 644 /home/pi/cinemate/resources/tuning_files/imx585.json "$dir/imx585.json"
  sudo install -m 644 /home/pi/cinemate/resources/tuning_files/imx585_mono.json "$dir/imx585_mono.json"
done
```

Cinemate's stock `settings.json` shows 1.5K, 2K, and 4K-class recording-size choices by default. Keep `4` in `resolutions.k_steps` to expose 4K in the UI; remove it only if you intentionally want to hide 4K-class modes. To check or edit the list, type `editsettings` in the Pi terminal, or edit `/home/pi/cinemate/src/settings.json` directly:

```json
"resolutions": {
  "k_steps": [1.5, 2, 4],
  "bit_depths": [10, 12],
  "custom_modes": {}
}
```

Restart Cinemate after changing `settings.json`.

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

Replace the file contents with this managed-format block, and uncomment the sensor you are using.

Also specify which physical camera port you have connected your sensor to. A clean install should use the IMX477 section on `cam0`; a StarlightEye color setup should use the IMX585 section on the camera port where the sensor is connected.

The one-click installer writes the same fully managed Cinemate `config.txt` block and backs up the previous file under `/home/pi/.cinemate-install-backups/`.

```bash
# >>> cinemate-install >>>
# Managed by cinemate-install.sh
# For more options and information see
# http://rptl.io/configtxt
# Some settings may impact device functionality. See link above for details

# Uncomment some or all of these to enable the optional hardware interfaces
dtparam=i2c_arm=on
#dtparam=i2s=on
#dtparam=spi=on

# Enable audio (loads snd_bcm2835)
dtparam=audio=on

# ---- Camera section ----

# Raspberry Pi HQ camera (IMX477, clean-install default on cam0)
camera_auto_detect=1
dtoverlay=imx477,cam0

# Raspberry Pi GS camera (IMX296, 10-bit RAW)
#camera_auto_detect=1
#dtoverlay=imx296,cam0

# OneInchEye (IMX283)
#camera_auto_detect=0
#dtoverlay=imx283,cam0

# StarlightEye color (IMX585)
#camera_auto_detect=0
#dtoverlay=imx585,cam0

# StarlightEye Mono (IMX585 mono)
#camera_auto_detect=0
#dtoverlay=imx585,cam1,mono

# ---- End camera section ----

# Automatically load overlays for detected DSI displays
display_auto_detect=1

# Automatically load initramfs files, if found
auto_initramfs=1

# Enable DRM VC4 V3D driver
dtoverlay=vc4-kms-v3d
max_framebuffers=2

# Don't have the firmware create an initial video= setting in cmdline.txt.
# Use the kernel's default instead.
disable_fw_kms_setup=1

# Run in 64-bit mode
arm_64bit=1

# Disable compensation for displays with overscan
disable_overscan=1

# Run as fast as firmware / board allows
arm_boost=1

[cm4]
# Enable host mode on the 2711 built-in XHCI USB controller.
# This line should be removed if the legacy DWC2 controller is required
# (e.g. for USB device mode) or if USB support is not required.
otg_mode=1

[cm5]
dtoverlay=dwc2,dr_mode=host

# CFE Hat PCIe 3.0
dtparam=pciex1
dtparam=pciex1_gen=3

[all]
auto_initramfs=1
avoid_warnings=1
disable_splash=1
dtparam=i2c1=on
dtoverlay=disable-bt
# <<< cinemate-install <<<
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

### Enable console auto-login

The one-click installer does this automatically unless `ENABLE_CONSOLE_AUTOLOGIN=0` is set. For a manual install, create a systemd drop-in for `getty@tty1` so the configured Pi user is logged in on the main console after boot:

```bash
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf >/dev/null <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin pi --noclear %I $TERM
EOF
sudo systemctl daemon-reload
```

Replace `pi` in the `--autologin` line if your Raspberry Pi user has a different name. The change applies the next time `tty1` starts, normally after a reboot.

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

Use the packing suffix that matches your Pi generation and sensor. For IMX296, the sensor mode is 10-bit:

```shell
# IMX296 on Raspberry Pi 5 / CM5
cinepi-raw --mode 1456:1088:10:U --width 1456 --height 1088 --lores-width 1280 --lores-height 720

# IMX296 on Raspberry Pi 4 / Pi 400 / CM4
cinepi-raw --mode 1456:1088:10:P --width 1456 --height 1088 --lores-width 1280 --lores-height 720
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
pi_model 0 rec 0 sensor 0 shutter_a 0 space_left 0 storage_type 0 \
wb 5600 wb_user 5600 width 0 memory_alert 0 \
shutter_a_sync_mode 0 shutter_angle_nom 0 shutter_angle_actual 0 shutter_angle_transient 0 \
exposure_time 0 last_dng_cam1 0 last_dng_cam0 0 \
zoom 0 write_speed_to_drive 0 recording_time 0
redis-cli SETNX sensor_mode 0
```

`sensor_mode` is initialized to `0` only when Redis does not already contain a value.

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

#### storage-automount

Mounts and unmounts removable drives such as SSDs, NVMe enclosures and the CFE HAT.

#### wifi-hotspot

Keeps a simple Wi‑Fi hotspot running via NetworkManager so you can reach the web UI while in the field. The SSID and password come from the `system.wifi_hotspot` section of `settings.json`.

#### redis-log-maintenance

Enables the `redis-log-maintenance.timer`, which periodically trims `/var/log/redis/redis-server.log` and removes old Redis log rotations so the Pi root filesystem does not slowly fill up.

To inspect the Redis log maintenance timer later:

```bash
systemctl status redis-log-maintenance.timer
journalctl -u redis-log-maintenance.service
```

#### cinemate-autostart.service

Starts Cinemate automatically on boot. After you have tested Cinemate manually in the Running cinemate manually section at the end of this guide and confirmed that it runs smoothly, enable the service with:

```shell
cd /home/pi/cinemate/
```

```
sudo make install   # copy service file
sudo make enable    # start on boot
```

After enabling the service, reboot the Pi. Cinemate should autostart on the next boot. If you deliberately want to test the service immediately from SSH, run `sudo systemctl start cinemate-autostart`, but the normal install path is to reboot.

#### Further notes

`sudo make install` also places `/usr/local/bin/camera-ready.sh`, `/usr/local/bin/cinemate-startup-failure-display.sh`, and `/usr/local/bin/cinemate-console-handoff.sh` on the system. The camera-ready helper waits for `cinepi-raw` to report a camera before systemd launches Cinemate, the startup-failure helper preserves early crash diagnostics on `tty1`, and the console-handoff helper restores the CLI on a normal Cinemate stop while leaving `tty1` available for Plymouth during full system shutdown.

You now have a 12 bit RAW image capturing system on your Raspberry Pi!

#### Wi-Fi hotspot handoff

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

### Connect to the Pi (if not already connected):

```shell
ssh pi@10.42.0.1
```

password: 1

## Running cinemate manually

Running Cinemate manually is recommended while you are trying out the system, testing GPIO buttons, checking rotary encoder actions, changing `settings.json`, or doing maintenance and development. When Cinemate is started from a terminal, that terminal also becomes the Cinemate CLI. You can type commands such as `get`, `rec`, `stop`, `set iso 800`, `set resolution`, or `restart camera`. See [Cinemate terminal commands](cli-commands.md) for the full command list.

If `cinemate-autostart.service` is already running, stop it before launching Cinemate manually:

```shell
sudo systemctl stop cinemate-autostart
```

Then start Cinemate manually:

```shell
cd /home/pi/cinemate
cinemate
```

Press Ctrl+C in that terminal to stop the manually started Cinemate process.

During maintenance or development, stopping the service only stops it for the current boot. Disable it if you do not want Cinemate to autostart after the next reboot:

```shell
sudo systemctl disable cinemate-autostart
```

When you want the normal camera boot behavior again, enable it and either reboot or start it directly:

```shell
sudo systemctl enable cinemate-autostart
sudo systemctl start cinemate-autostart
```

To check what the service is doing:

```shell
systemctl status cinemate-autostart
journalctl -fu cinemate-autostart
```
