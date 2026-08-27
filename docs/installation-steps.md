# Manual installation

## One-click installer

The one-click installer is a single script that builds and configures the whole stack.

Start from a fresh Raspberry Pi OS Lite Bookworm 64 bit image. SSH to the Pi (Terminal on macOS, PowerShell on Windows):

```bash
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
```

```bash
./cinemate-install.sh
```

The installer defaults to an `imx477` on camera port `cam0`. To install directly for another sensor, pass `SENSOR_MODEL` and `CAM_PORT` inline:

```bash
SENSOR_MODEL=imx296 CAM_PORT=cam0 ./cinemate-install.sh
SENSOR_MODEL=imx283 CAM_PORT=cam0 ./cinemate-install.sh
SENSOR_MODEL=imx585 CAM_PORT=cam0 ./cinemate-install.sh
SENSOR_MODEL=imx585_mono CAM_PORT=cam1 ./cinemate-install.sh
```

!!! note ""

    You can adjust sensor and camera port later by editing `/boot/firmware/config.txt`. See [Switching sensors](config-txt.md).

After installing, reboot the system and Cinemate should start automatically.

## Manual install

Start from a fresh Raspberry Pi OS Lite (Bookworm) install before continuing.

```
sudo apt update -y
sudo apt upgrade -y
```

### Kernel baseline (Raspberry Pi 5 / CM5)

Cinemate pins the Pi 5 kernel to a validated baseline: **6.12.93+rpt**. Install it before building `libcamera`, `cinepi-raw`, or the IMX585 driver, and make the boot files stick in `/boot/firmware`.

The baseline matters in both directions. Older kernels — including the previous 6.12.25 pin — ship an `rp1-cfe` driver that corrupts 16-bit CSI-2 capture, which breaks imx585 ClearHDR (10/12-bit recording is unaffected). The fixes landed mid-2025 (`cfe: Avoid unpack operation for 16-bit formats` plus a 16-bit hardware mismatch workaround), so any kernel from 6.12.93+rpt onward works; the pin keeps the fleet on one tested version.

Skip this section on Pi 4.

```bash
mkdir -p ~/kernel-baseline-6.12.93
cd ~/kernel-baseline-6.12.93

curl -LO https://archive.raspberrypi.com/debian/pool/main/l/linux/linux-support-6.12.93+rpt_6.12.93-1+rpt1_all.deb
curl -LO https://archive.raspberrypi.com/debian/pool/main/l/linux/linux-image-6.12.93+rpt-rpi-2712_6.12.93-1+rpt1_arm64.deb
curl -LO https://archive.raspberrypi.com/debian/pool/main/l/linux/linux-image-rpi-2712_6.12.93-1+rpt1_arm64.deb
curl -LO https://archive.raspberrypi.com/debian/pool/main/l/linux/linux-headers-6.12.93+rpt-rpi-2712_6.12.93-1+rpt1_arm64.deb
curl -LO https://archive.raspberrypi.com/debian/pool/main/l/linux/linux-headers-rpi-2712_6.12.93-1+rpt1_arm64.deb
curl -LO https://archive.raspberrypi.com/debian/pool/main/r/raspi-firmware/raspi-firmware_1.20260521-1~bookworm_all.deb

sudo apt install -y --allow-downgrades ./*.deb
sudo update-initramfs -u -k 6.12.93+rpt-rpi-2712
sudo cp /boot/vmlinuz-6.12.93+rpt-rpi-2712 /boot/firmware/kernel_2712.img
sudo cp /boot/initrd.img-6.12.93+rpt-rpi-2712 /boot/firmware/initramfs_2712
sudo apt-mark hold \
  raspi-firmware \
  linux-support-6.12.93+rpt \
  linux-image-6.12.93+rpt-rpi-2712 \
  linux-image-rpi-2712 \
  linux-headers-6.12.93+rpt-rpi-2712 \
  linux-headers-rpi-2712
sudo reboot
```

After the reboot, verify the baseline before continuing:

```bash
uname -r
```

Expected output on Pi 5:

```text
6.12.93+rpt-rpi-2712
```

### Install dependencies 


```bash
sudo apt-get install python3-jinja2 python3-ply python3-yaml ffmpeg
```

```
sudo apt install -y git cmake libepoxy-dev libavdevice-dev build-essential cmake libboost-program-options-dev libdrm-dev libexif-dev libcamera-dev libjpeg-dev libtiff5-dev libpng-dev redis-server libhiredis-dev libasound2-dev libjsoncpp-dev libpng-dev meson ninja-build libavcodec-dev libavdevice-dev libavformat-dev libswresample-dev ffmpeg && sudo apt-get install libjsoncpp-dev && cd ~ && git clone https://github.com/sewenew/redis-plus-plus.git && cd redis-plus-plus && mkdir build && cd build && cmake .. && make && sudo make install && cd ~
```



### Libcamera  <img src="https://img.shields.io/badge/cinemate-fork-gren" height="12" >


```shell
sudo apt install -y python3-pip python3-jinja2 libboost-dev libgnutls28-dev openssl pybind11-dev qtbase5-dev libqt5core5a meson cmake python3-yaml python3-ply libglib2.0-dev libgstreamer-plugins-base1.0-dev libgstreamer1.0-dev libavdevice59 libyaml-dev
```

```shell
sudo apt-get install --reinstall libtiff5-dev && sudo ln -sf $(find /usr/lib -name "libtiff.so" | head -n 1) /usr/lib/aarch64-linux-gnu/libtiff.so.5 && export LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu:$LD_LIBRARY_PATH && sudo ldconfig
```


```shell
git clone https://github.com/Tiramisioux/libcamera.git && \
cd libcamera && \
git config core.fileMode false && \
git checkout cinemate && \
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
  -Dpycamera=disabled && \
ninja -C build && \
sudo ninja -C build install && \
sudo ldconfig
```

### cpp-mjpeg-streamer

```bash
sudo apt install -y libspdlog-dev libjsoncpp-dev && cd /home/pi && git clone https://github.com/nadjieb/cpp-mjpeg-streamer.git && cd cpp-mjpeg-streamer && mkdir build && cd build && cmake .. && make && sudo make install && cd
```

### CinePi-RAW <img src="https://img.shields.io/badge/cinemate-fork-gren" height="12" >



```bash
git clone https://github.com/Tiramisioux/cinepi-raw.git
cat > /home/pi/compile-raw.sh <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

CINEPI_RAW_DIR="${CINEPI_RAW_DIR:-/home/pi/cinepi-raw}"
CPP_MJPEG_STREAMER_DIR="${CPP_MJPEG_STREAMER_DIR:-/home/pi/cpp-mjpeg-streamer}"
BUILD_JOBS="${BUILD_JOBS:-$(c=$(nproc 2>/dev/null || echo 4); mb=$(awk '/^MemTotal:/{print int($2/1024); exit}' /proc/meminfo 2>/dev/null || echo 0); j=$c; if [ "$mb" -gt 0 ] && [ "$mb" -lt 3000 ]; then j=$(( mb / 1536 )); if [ "$j" -lt 1 ]; then j=1; fi; if [ "$j" -gt "$c" ]; then j=$c; fi; fi; echo "$j")}"
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

# Temporary build swap for 1-2 GB boards: cinepi_raw.cpp needs ~2 GB at -O3 and
# OOM-kills cc1plus. Use compressed RAM (zram) -- no SD/eMMC writes -- removed on
# exit, so the running camera never swaps. Skipped when swap is already active
# or on boards with 4 GB+ RAM (>= 3000 MB).
CR_ZRAM_DEV=""
cr_cleanup_zram() {
    [[ -n "${CR_ZRAM_DEV:-}" ]] || return 0
    sudo swapoff "$CR_ZRAM_DEV" 2>/dev/null || true
    sudo zramctl --reset "$CR_ZRAM_DEV" 2>/dev/null || true
    CR_ZRAM_DEV=""
}
trap cr_cleanup_zram EXIT
cr_mem_mb=$(awk '/^MemTotal:/{print int($2/1024); exit}' /proc/meminfo 2>/dev/null || echo 0)
cr_swap_lines=$(wc -l < /proc/swaps 2>/dev/null || echo 1)
if [[ "$cr_mem_mb" -gt 0 && "$cr_mem_mb" -lt 3000 && "$cr_swap_lines" -le 1 ]]; then
    sudo modprobe zram 2>/dev/null || true
    CR_ZRAM_DEV=$(sudo zramctl --find --size 4G --algorithm zstd 2>/dev/null || sudo zramctl --find --size 4G 2>/dev/null || true)
    if [[ -n "$CR_ZRAM_DEV" ]] && sudo mkswap "$CR_ZRAM_DEV" >/dev/null 2>&1 && sudo swapon -p 100 "$CR_ZRAM_DEV" 2>/dev/null; then
        printf '[compile-raw] Low-RAM board (%s MB): added 4 GB zram build swap on %s (removed on exit)\n' "$cr_mem_mb" "$CR_ZRAM_DEV"
    else
        [[ -n "$CR_ZRAM_DEV" ]] && sudo zramctl --reset "$CR_ZRAM_DEV" 2>/dev/null || true
        CR_ZRAM_DEV=""
        printf '[compile-raw] WARNING: could not set up zram build swap; low-RAM build may OOM\n'
    fi
fi

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

You can rerun `/home/pi/compile-raw.sh` later whenever you need to rebuild `cinepi-raw`. 

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

### IMX283 and IMX585 sensors

```shell
sudo apt install dkms -y
```

```shell
git clone https://github.com/Tiramisioux/imx283-v4l2-driver.git --branch 6.12.y
cd imx283-v4l2-driver/
./setup.sh
sudo dkms autoinstall -k 6.12.25+rpt-rpi-2712
cd
```

```shell
git clone https://github.com/Tiramisioux/imx585-v4l2-driver.git --branch 6.12.y
cd imx585-v4l2-driver/
./setup.sh
sudo dkms autoinstall -k 6.12.25+rpt-rpi-2712
cd
```

#### Mechanical IR filter switch script

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

After the line 

```
# Additional overlays and parameters are documented
# /boot/firmware/overlays/README
```

Replace the file contents with this:

```
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
    This boot-time `video=` setting pins the framebuffer mode. Cinemate still reads the preferred HDMI canvas and runtime HDMI port from `settings.jsonc`.

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

### Make the console font larger (optional)

This can be useful if running the Pi on a small HD field monitor

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

PiShrink is a handy tool for compressing SD image file backups of the SD card.


```bash
sudo wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh -O /usr/local/bin/pishrink.sh
sudo chmod +x /usr/local/bin/pishrink.sh
```


### Install Cinemate

#### System wide packages

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

#### Create a Python virtual environment

```bash
python3 -m venv ~/.cinemate-env
source /home/pi/.cinemate-env/bin/activate
echo "source /home/pi/.cinemate-env/bin/activate" >> ~/.bashrc
```

#### Grant sudo privileges and enable I²C

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

#### Python packages

```bash
pip install \
    gpiozero \
    adafruit-blinka adafruit-circuitpython-ssd1306 adafruit-circuitpython-seesaw \
    luma.oled grove.py pigpio-encoder smbus2 rpi_hardware_pwm \
    watchdog psutil pillow redis keyboard pyudev numpy termcolor sounddevice \
    evdev inotify_simple sysv_ipc flask_socketio sugarpie
```

#### Alternative GPIO back-end

```bash
sudo apt install -y swig python3-dev build-essential git
git clone https://github.com/joan2937/lg
cd lg && make
sudo make install
cd .. && pip install lgpio
```

#### Clone the Cinemate repo

```bash
sudo apt install -y git
git clone https://github.com/Tiramisioux/cinemate.git
```

#### Allow Cinemate to run with sudo

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

#### Enable NetworkManager

```bash
sudo systemctl enable NetworkManager --now
```

#### Rotate logs

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

#### Seed Redis with default keys

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

#### Add aliases

```shell
nano ~/.bashrc
```

Add to the end of the file:

```shell
alias cinemate-env='source /home/pi/.cinemate-env/bin/activate'
alias cinemate='/home/pi/run_cinemate.sh'
alias editboot='sudo nano /boot/firmware/config.txt'
alias editcmdline='sudo nano /boot/firmware/cmdline.txt'
alias editsettings='sudo nano /home/pi/cinemate/settings.jsonc'
```

Exit with Ctrl+x. System will ask you to save the file. Press "y" and then enter.

Reload .bashrc

```shell
source ~/.bashrc
```

#### Add nano syntax highlighting for `settings.jsonc`

nano's stock JSON rule only matches `.json`, not `.jsonc`, so `editsettings` opens with no colors until you add a syntax file for it:

```shell
sudo nano /usr/share/nano/jsonc.nanorc
```

Paste:

```
syntax "jsonc" "\.jsonc$"
comment "//"
color green "\"(\\.|[^\"])*\""
color cyan "\"(\\.|[^\"])*\"[[:space:]]*:"
color magenta "-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?"
color yellow "\<(true|false|null)\>"
color brightwhite "[]{}[,:]"
color white "//.*"
color white start="/\*" end="\*/"
```

Save with Ctrl+x, y, enter. Debian's nano already includes `/usr/share/nano/*.nanorc`, so no further config is needed — `editsettings` will show colors the next time you open it.


#### Install Plymouth for the boot spinner

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

 ```
 sudo nano /boot/firmware/cmdline.txt
 ````

At the en of the single line, add a blank space and then:

```text
quiet splash loglevel=1 plymouth.ignore-serial-consoles vt.global_cursor_default=0 logo.nologo
```

Keep the `video=HDMI-A-1:1920x1080M@60D` or `video=HDMI-A-2:1920x1080M@60D` override from the HDMI setup above on that same line as well.

Apply the Plymouth theme and rebuild the initramfs:

```bash
sudo plymouth-set-default-theme cinemate
sudo update-initramfs -u
```


### Cinemate services

Install and enable the support services with:

```bash
cd /home/pi/cinemate/services
```

```
sudo make install
sudo make start  # starts storage-automount and wifi-hotspot now, and runs one redis cleanup pass
sudo make enable # enables storage-automount, wifi-hotspot, and redis-log-maintenance.timer on boot
```

#### cinemate-autostart.service

Starts Cinemate automatically on boot. After you have tested Cinemate manually in the Running cinemate manually section at the end of this guide and confirmed that it runs smoothly, enable the service with:

```shell
cd /home/pi/cinemate/
```

```
sudo make install   # copies service file
sudo make enable    # enables start on boot
```

After enabling the service, reboot the Pi. Cinemate should autostart on the next boot. If you deliberately want to test the service immediately from SSH, run `sudo systemctl start cinemate-autostart`, but the normal install path is to reboot.

The Cinemate manual install is now finished!

# Further notes

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

During development/building your rig you might prefer the Pi to use your normal Wi‑Fi instead of its own hotspot so you remain online while tinkering. Disable the hotspot by setting `system.wifi_hotspot.enabled` to `false` in `settings.jsonc` _and_ by stopping the service with: 

```
sudo systemctl stop wifi-hotspot
```

To stop the hotspot from starting on boot, type 

```
sudo systemctl disable wifi-hotspot
```

See [Hotspot logic](hotspot-logic.md) for more details on how the hotspot works.

#### Connect to the Pi (if not already connected):

```shell
ssh pi@10.42.0.1
```

password: 1

## Running cinemate manually

Running Cinemate manually is recommended while you are trying out the system, testing GPIO buttons, checking rotary encoder actions, changing `settings.jsonc`, or doing maintenance and development. When Cinemate is started from a terminal, that terminal also becomes the Cinemate CLI. You can type commands such as `get`, `rec`, `stop`, `set iso 800`, `set resolution`, or `restart camera`. See [Cinemate terminal commands](cli-commands.md) for the full command list.

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

## Boot time optimization

These changes bring typical boot-to-live-preview time down to approximately 10 seconds on both Raspberry Pi 4 and Raspberry Pi 5. The one-click installer applies all of them automatically. If you used the manual install path, apply each step separately after the rest of the install is complete.

### Disable unnecessary background services

The following services and timers are not used by the camera stack. Disabling them removes stall points on the boot critical path.

```bash
# Stop the network-online gate — the hotspot creates its own AP and does not need upstream internet
sudo systemctl disable --now NetworkManager-wait-online.service

# Disable swap — not needed on Pi 4/5, and saves SD card writes
sudo systemctl disable --now dphys-swapfile.service

# Background daemons the camera never uses
sudo systemctl disable --now triggerhappy.service
sudo systemctl disable --now ModemManager.service
sudo systemctl disable --now systemd-rfkill.service

# Background maintenance timers — not on the boot critical path
sudo systemctl disable --now man-db.timer
sudo systemctl disable --now apt-daily.timer
sudo systemctl disable --now apt-daily-upgrade.timer
sudo systemctl disable --now e2scrub_all.timer
```

!!! note ""
    Some of these units may not be present on a minimal Bookworm Lite image. `systemctl disable` prints a warning and continues if the unit does not exist.

### Skip filesystem check on boot

Add `fsck.mode=skip` to `/boot/firmware/cmdline.txt`. The file must stay on a single line:

```bash
sudo nano /boot/firmware/cmdline.txt
```

Append a blank space and then `fsck.mode=skip` to the end of the existing line:

```text
... video=HDMI-A-1:1920x1080M@60D fsck.mode=skip
```

!!! note ""
    `cmdline.txt` must stay on a single line. Do not add line breaks.

### Skip HDMI CEC handshake

Add `hdmi_ignore_cec_init=1` to the `[all]` block of `/boot/firmware/config.txt`, below `avoid_warnings=1`:

```bash
sudo nano /boot/firmware/config.txt
```

Inside the `[all]` block:

```text
[all]
auto_initramfs=1
avoid_warnings=1
disable_splash=1
hdmi_ignore_cec_init=1
```

This skips the HDMI CEC handshake during boot, removing a short delay on HDMI-connected displays.
