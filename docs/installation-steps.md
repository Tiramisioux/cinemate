# Installation
Here is how you can manually install libcamera, cinepi-raw, cinemate and accompanying software on the Raspberry Pi.

!!! Note

     Stack works on Raspberry Pi 4 and 5 models. 2 GB RAM is sufficient, while more RAM will give you a larger framebuffer. Useful at high frame rates.

!!! Note

     Cinemate is using Linux kernel version 6.12.25. Recommended OS is Bookworm Lite.

### Tools & dependencies


```
sudo apt update -y
sudo apt upgrade -y
```

```bash
sudo apt-get install python3-jinja2 python3-ply python3-yaml
```

```
sudo apt install -y git cmake libepoxy-dev libavdevice-dev build-essential cmake libboost-program-options-dev libdrm-dev libexif-dev libcamera-dev libjpeg-dev libtiff5-dev libpng-dev redis-server libhiredis-dev libasound2-dev libjsoncpp-dev libpng-dev meson ninja-build libavcodec-dev libavdevice-dev libavformat-dev libswresample-dev && sudo apt-get install libjsoncpp-dev && cd ~ && git clone https://github.com/sewenew/redis-plus-plus.git && cd redis-plus-plus && mkdir build && cd build && cmake .. && make && sudo make install && cd ~
```

### libcamera 1.7.0 <img src="https://img.shields.io/badge/raspberry pi-fork-red" height="12" >

```shell
sudo apt install -y python3-pip  python3-jinja2 libboost-dev libgnutls28-dev openssl pybind11-dev qtbase5-dev libqt5core5a meson cmake python3-yaml python3-ply libglib2.0-dev libgstreamer-plugins-base1.0-dev libgstreamer1.0-dev libavdevice59
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

### CinePi-RAW <img src="https://img.shields.io/badge/cinemate-fork-gren" height="12" >

```bash
git clone https://github.com/Tiramisioux/cinepi-raw.git --branch rpicam-apps_1.7_custom_encoder
cd cinepi-raw
sudo rm -rf build
sudo meson setup build
sudo ninja -C build
sudo meson install -C build
cd
sudo ldconfig
```

### Seed Redis with white balance default keys

```
redis-cli <<EOF
SET cg_rb 2.5,2.2
PUBLISH cp_controls cg_rb
EOF
```

### IMX585 driver (optional)

```shell
sudo apt install linux-headers dkms -y
```

```
git clone https://github.com/will127534/imx585-v4l2-driver.git --branch 6.12.y
cd imx585-v4l2-driver/
./setup.sh
cd

```

>The imx585 is written by Will Whang. For original drivers and startup guides, visit https://github.com/will127534/StarlightEye

#### Add IMX585 tuning files 

```bash
curl -L -o /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585.json \
  https://raw.githubusercontent.com/will127534/libcamera/master/src/ipa/rpi/pisp/data/imx585.json
sed -i '8s/"black_level": *[0-9]\+/"black_level": 0/' /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585.json
sudo cp /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585.json /usr/local/share/libcamera/ipa/rpi/pisp/
```
```
curl -L -o /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585_mono.json https://raw.githubusercontent.com/will127534/libcamera/master/src/ipa/rpi/pisp/data/imx585_mono.json && sudo cp /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585_mono.json /usr/local/share/libcamera/ipa/rpi/pisp/
```
 
#### IR filter switch script

```bash
sudo wget https://raw.githubusercontent.com/will127534/StarlightEye/master/software/IRFilter -O /usr/local/bin/IRFilter
sudo chmod +x /usr/local/bin/IRFilter
```

>Cinemate has its own way of handling the IR switch but the installation above can be convenient for use outside of Cinemate

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
sudo wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh -O /usr/local/bin/pishrink.sh
sudo chmod +x /usr/local/bin/pishrink.sh
```

>PiShrink is a handy tool for compressing SD image file backups of the SD card. See here for instructions

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
echo "pi ALL=(ALL) NOPASSWD: /home/pi/run_cinemate.sh" | sudo tee -a /etc/sudoers.d/pi_cinemate
```
Reboot so the group changes take effect:

```bash
sudo reboot
```

### Python packages

> If you previously installed the `board` Python package, remove it with `pip3 uninstall board`.

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

Exit with Ctrl+x. System will ask you to save the file. Press "y" and then enter.

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

### Add alias

```shell
nano ~/.bashrc
```

Add to the end of the file:

```shell
alias cinemate='python3 /home/pi/cinemate/src/main.py'
```

Exit with Ctrl+x. System will ask you to save the file. Press "y" and then enter.

Reload .bashrc

```shell
source ~/.bashrc
```

### Cinemate services

#### storage-automount

Mounts and unmounts removable drives such as SSDs, NVMe enclosures and the CFE HAT. 

#### wifi-hotspot

Keeps a simple Wi‑Fi hotspot running via NetworkManager so you can reach the web UI while in the field. The SSID and password come from the `system.wifi_hotspot` section of `settings.json`.

Install and enable both services with:

```bash
cd /home/pi/cinemate/services

sudo make install
sudo make start  # starts the service
sudo make enable # makes the service start on boot

```
You can also start and enable the service individually, by entering their respective folders and issuing the `sudo make` command

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

!!! info ""

    During development/building your rig you might prefer the Pi to use your normal Wi‑Fi instead of its own hotspot so you remain online while tinkering. 
    
    Disable the hotspot by setting `system.wifi_hotspot.enabled` to `false` `settings.json` _and_ by stopping the service with `sudo systemctl stop wifi-hotspot`.

    To stop the hotspot from starting on boot, type `sudo systemctl disable wifi-hotspot`.

    If you plug in an Ethernet cable you can keep the hotspot active while the wired connection provides internet access. See [Hotspot logic](hotspot-logic.md) for more details on how the hotspot works.

### Connect to the Pi (if not already connected):

```shell
ssh pi@10.42.0.1

# password: 1
```


### Starting Cinemate

Now, back on the Pi, anywhere in the terminal, type:

```shell
cinemate
```

Make sure things are running smoothly and then you can move on to enabling the cinemate-autostart service:

#### cinemate-autostart.service

```shell
cd /home/pi/cinemate/

sudo make install   # copy service file
sudo make enable    # start on boot
make start          # launch now
```

After enabling the service, Cinemate should autostart on boot.

You now have a 12 bit RAW image capturing system on your Raspberry Pi!




