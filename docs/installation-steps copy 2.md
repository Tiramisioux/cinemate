# Installation

Here is how you can manually install libcamera, cinepi-raw, cinemate and accompanying software on the Raspberry Pi.

>Although Raspberry Pi 4 (and even 3) has been known to work with the stack below, a Raspopberry Pi 5B or Compute Module 5 is recommended. Also note that for high speed USB 3, a Raspberry Pi 4 or 5 is needed.

This guide assumes fresh Raspbery Pi Bookworm installation running kernel 6.12.34 (this is what you get with the official Raspberry Pi imager and doing a sudo apt update && sudo apt upgrade).

If you run Raspberry Pi OS Lite, begin by installing the following packages:

```bash
sudo apt-get install python3-jinja2 python3-ply python3-yaml
```

## Manual install

### Tools & dependencies

```
sudo apt update && sudo apt upgrade
```

```
sudo apt install -y cmake libepoxy-dev libavdevice-dev build-essential cmake libboost-program-options-dev libdrm-dev libexif-dev libcamera-dev libjpeg-dev libtiff5-dev libpng-dev redis-server libhiredis-dev libasound2-dev libjsoncpp-dev libpng-dev meson ninja-build libavcodec-dev libavdevice-dev libavformat-dev libswresample-dev && sudo apt-get install libjsoncpp-dev && cd ~ && git clone https://github.com/sewenew/redis-plus-plus.git && cd redis-plus-plus && mkdir build && cd build && cmake .. && make && sudo make install && cd ~
```

### libcamera 1.7.0 <img src="https://img.shields.io/badge/raspberry pi-fork-red" height="12" >

```shell
sudo apt install -y python3-pip git python3-jinja2 libboost-dev libgnutls28-dev openssl pybind11-dev qtbase5-dev libqt5core5a meson cmake python3-yaml python3-ply libglib2.0-dev libgstreamer-plugins-base1.0-dev libgstreamer1.0-dev libavdevice59
```

```shell
sudo apt-get install --reinstall libtiff5-dev && sudo ln -sf $(find /usr/lib -name "libtiff.so" | head -n 1) /usr/lib/aarch64-linux-gnu/libtiff.so.5 && export LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu:$LD_LIBRARY_PATH && sudo ldconfig
```

```shell
git clone https://github.com/raspberrypi/libcamera.git && \
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
sudo ninja -C build install
```

```shell
cd ~/libcamera/utils && sudo chmod +x *.py *.sh && sudo chmod +x ~/libcamera/src/ipa/ipa-sign.sh && cd ~/libcamera && sudo ninja -C build install
```

### cpp-mjpeg-streamer

```bash
sudo apt install -y libspdlog-dev libjsoncpp-dev && cd /home/pi && git clone https://github.com/nadjieb/cpp-mjpeg-streamer.git && cd cpp-mjpeg-streamer && mkdir build && cd build && cmake .. && make && sudo make install && cd
```

### CinePi-raw <img src="https://img.shields.io/badge/cinemate-fork-gren" height="12" >

```bash
git clone https://github.com/Tiramisioux/cinepi-raw.git --branch rpicam-apps_1.7_custom_encoder
cd cinepi-raw
sudo rm -rf build
sudo meson setup build
sudo ninja -C build
sudo meson install -C build
cd
```

```
redis-cli <<EOF
SET cg_rb 2.5,2.2
PUBLISH cp_controls cg_rb
EOF
```

### imx585 driver <img src="https://img.shields.io/badge/cinemate-fork-gren" height="12" >

```shell
sudo apt install linux-headers dkms git
```

```
git clone https://github.com/will127534/imx585-v4l2-driver.git --branch 6.12.y
cd imx585-v4l2-driver/
./setup.sh
```

>The imx585 is written by Will Whang. For original drivers and startup guides, visit https://github.com/will127534/StarlightEye

### Add the IMX585 tuning files (optional)

```bash
curl -L -o /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585.json \
  https://raw.githubusercontent.com/will127534/libcamera/master/src/ipa/rpi/pisp/data/imx585.json
sed -i '8s/"black_level": *[0-9]\+/"black_level": 0/' /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585.json
cp /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585.json /usr/local/share/libcamera/ipa/rpi/pisp/
```
```
curl -L -o /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585_mono.json https://raw.githubusercontent.com/will127534/libcamera/master/src/ipa/rpi/pisp/data/imx585_mono.json && sudo cp /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585_mono.json /usr/local/share/libcamera/ipa/rpi/pisp/
```
 
### IR filter switch script (optional)

```bash
sudo wget https://raw.githubusercontent.com/will127534/StarlightEye/master/software/IRFilter -O /usr/local/bin/IRFilter
sudo chmod +x /usr/local/bin/IRFilter
```

>Cinemate has its own way of handling the IR switch but the installation above can be convenient for use outside of Cinemate

### imx283 driver <img src="https://img.shields.io/badge/cinemate-fork-gren" height="12" >

```shell
sudo apt install linux-headers dkms git
```

```
git clone https://github.com/Tiramisioux/imx283-v4l2-driver.git
cd imx283-v4l2-driver/
./setup.sh
```

>The imx283 is written by Will Whang. For original drivers and startup guides, visit https://github.com/will127534/imx283-v4l2-driver


### Enabling I²C

```bash
sudo raspi-config nonint do_i2c 0
```
>Enabling I2C is needed for using the camera modules.

### Setting hostname

```bash
sudo hostnamectl set-hostname cinepi
```
>You will find the pi as `cinepi.local` on the local network, or at the hotspot Cinemate creates

### Add camera modules to config.txt

```shell
sudo nano /boot/firmware/config.txt
```

Paste this into your file, and uncomment the sensor you are using.

Also specify which physical camera port you have connected your sensor to.

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

### Change the console font (optional)

```bash
sudo apt update
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

> This can be useful if running the Pi on a small HD field monitor

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

>PiShrink is a great tool for compressing SD image file backups of the SD card. See here for instructions

### Reboot:

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

### Create a Python virtual environment

```bash
sudo apt update && sudo apt install -y python3-venv
python3 -m venv /home/pi/.cinemate-env
echo "source /home/pi/.cinemate-env/bin/activate" >> ~/.bashrc
source /home/pi/.cinemate-env/bin/activate
```

### Grant sudo privileges and enable I²C

```bash
echo "pi ALL=(ALL) NOPASSWD: /home/pi/.cinemate-env/bin/*" | sudo tee /etc/sudoers.d/cinemate-env
sudo chown -R pi:pi /home/pi/.cinemate-env
sudo chown -R pi:pi /media && chmod 755 /media
sudo usermod -aG i2c pi
sudo modprobe i2c-dev && echo i2c-dev | sudo tee -a /etc/modules
echo "pi ALL=(ALL) NOPASSWD: /home/pi/run_cinemate.sh" | sudo tee -a /etc/sudoers.d/pi_cinemate
```
Reboot so the group changes take effect:

```bash
reboot
```

### Dependencies

```bash
python3 -m pip install --upgrade pip setuptools wheel
sudo apt-get install -y i2c-tools portaudio19-dev build-essential python3-dev python3-pip python3-smbus python3-serial git
pip3 install adafruit-circuitpython-ssd1306 watchdog psutil Pillow redis keyboard pyudev sounddevice smbus2 gpiozero RPI.GPIO evdev termcolor pyserial inotify_simple numpy rpi_hardware_pwm
pip3 uninstall -y Pillow && pip3 install Pillow
pip3 install sugarpie flask_socketio adafruit-blinka adafruit-circuitpython-seesaw luma.oled grove.py pigpio-encoder gpiod
sudo apt install python3-systemd e2fsprogs ntfs-3g exfatprogs console-terminus
```
> If you previously installed the `board` Python package, remove it with `pip3 uninstall board`.

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
  git clone https://github.com/Tiramisioux/cinemate.git
```

### Allow Cinemate to run with sudo

Edit the sudoers file:

```shell
sudo visudo
```

add this to the end of the file:
```text
pi ALL=(ALL) NOPASSWD: /home/pi/cinemate/src/main.py
pi ALL=(ALL) NOPASSWD: /bin/mount, /bin/umount, /usr/bin/ntfs-3g
pi ALL=(ALL) NOPASSWD: /home/pi/cinemate/src/logs/system.log
pi ALL=(ALL) NOPASSWD: /sbin/mount.ext4
```

Exit with Ctrl+x

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

```bash
redis-cli <<'EOF'
SET anamorphic_factor 1.0
PUBLISH cp_controls anamorphic_factor
SET bit_depth 12
PUBLISH cp_controls bit_depth
EOF
```

(See the settings guide for the full list.)

### Add a convenience alias

```shell
nano ~/.bashrc
```

# add to the end of the file

```shell
alias cinemate='python3 /home/pi/cinemate/src/main.py'
```

Exit with Ctrl+x

Reload .bashrc

```shell
source ~/.bashrc
```

### Cinemate services

Cinemate with two small helper services under `services/`:

#### storage-automount

Mounts and unmounts removable drives such as SSDs, NVMe enclosures and the CFE HAT. Partitions named `RAW` are attached at
  `/media/RAW`; all others are mounted under `/media/<LABEL>`.

#### wifi-hotspot

keeps a simple Wi‑Fi hotspot running via NetworkManager so
  you can reach the web UI even without other networking. The SSID and password
  come from the `system.wifi_hotspot` section of `settings.json`.

Install and enable both services with:

```bash
cd /home/pi/cinemate/services

sudo make install
sudo make enable
```

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
...
```

Connect to the Pi:

```
ssh pi@10.42.0.1

# password: 1
```


### Starting Cinemate

#### Initializing Redis Keys

This has only to be done once on your system:

```shell
redis-cli MSET \
anamorphic_factor 0 bit_depth 0 buffer 0 buffer_size 0 cam_init 0 cameras 0 cg_rb 2.5,2.2 \
file_size 0 fps 1 fps_actual 1 fps_last 1 fps_max 1 fps_user 1 framecount 0 \
gui_layout 0 height 0 ir_filter 0 is_buffering 0 is_mounted 0 is_recording 0 \
is_writing 0 is_writing_buf 0 tc_cam0 0 tc_cam1 0 iso 0 lores_height 0 lores_width 0 \
pi_model 0 rec 0 sensor 0 sensor_mode 0 shutter_a 0 space_left 0 storage_type 0 \
trigger_mode 0 wb 0 wb_user 0 width 0 memory_alert 0 \
shutter_a_sync_mode 0 shutter_angle_nom 0 shutter_angle_actual 0 shutter_angle_transient 0 \
exposure_time 0 last_dng_cam1 0 last_dng_cam0 0 \
zoom 0 write_speed_to_drive 0 recording_time 0
```

Now, back on the Pi, anywhere in the terminal, type:

```shell
cinemate
```

Make sure things are running smoothly and then you can move on to enabling the cinemate-autostart service:

#### cinemate-autostart.service

```bash
cd /home/pi/cinemate/

sudo make install   # copy service file
sudo make enable    # start on boot
make start          # launch now
```

After enabling the service, Cinemate should autostart on boot.

> **Tip:** `sudo make install` also places `/usr/local/bin/camera-ready.sh` on the system. The script waits for `cinepi-raw` to report a camera before systemd launches Cinemate, preventing the black-screen-on-boot issue that occurred when the GUI started before the sensor initialised.

!!! info "Thinking about the wifi-hotspot service"

    The optional `wifi-hotspot` service gives the Pi its own wireless network so you
    can always connect to the web interface. It is great for field work where there
    may be no existing network. Simply join the **CinePi** network on your phone or
    laptop and browse to the GUI.

    During development you might prefer the Pi to use your normal Wi‑Fi instead so
    you remain online while tinkering. Disable the hotspot by setting
    `system.wifi_hotspot.enabled` to `false` in `settings.json` or by stopping the
    service with `sudo systemctl stop wifi-hotspot`.

    If you plug in an Ethernet cable you can keep the hotspot active while the wired
    connection provides internet access. See [Hotspot logic](hotspot-logic.md) for
    more details on how the hotspot works.


