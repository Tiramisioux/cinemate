# What is it?
**Cinemate** is a boilerplate cinema camera system for Raspberry Pi 5. Builds upon CinePi-raw, authored by Csaba Nagy for enabling 12 bit Cinema DNG recordings using off-the-shelf components.  

Cinemate provides a minimal starting point that you can extend with your own controls and accessories. 

The project combines a Python UI with a custom fork of [cinepi-raw](https://github.com/Tiramisioux/cinepi-raw/tree/rpicam-apps_1.7_custom_encoder).

## New features in version 3.3.2

### libcamera

- Cinemate now uses its own fork of libcamera.

### imx283 driver

- Cinemate now uses its own fork of the imx283 driver.
- 2 additional modes: 3840 x 2160 (4K UHD, native crop) and 2736 x 1538 (2.7K 16:9, binned).

### imx585 driver

- Cinemate now uses its own fork of the imx585 driver.

### CinePi-RAW recorder updates

- **Frame-rate phase lock** — DNG timecode is locked to the Pi's wall clock, making audio sync more accurate. On by default.
- **More reliable audio sync on 4K / exFAT** — the capture path was reworked (protected helper, dedicated writer thread, wall-clock reconciliation, real-time scheduling) for more reliable WAV sync on demanding modes.
- **Wall clock embedded timecode** — timecode is anchored to the first frame's wall-clock time and follows the Pi's real-time clock.
- **Correct Pi 4 RAW** — CSI2-packed frames decode correctly on Pi 4-family boards; raw packing (P/U) is chosen per Pi model automatically.
- **Compiles on 2GB version of Raspberry Pi 4/5**
- **Camera model** — set the camera model manually for each attached sensor.

### Cinemate

- **Storage / media** — multi-drive RAW hot-swap with a standby drive and automatic promotion. Default format is exFAT.

### Raspberry Pi / Bookworm

- **Boot / install** — faster boot-to-preview on Pi 4/5 (about 10-15 seconds).

## Compatible sensors

- IMX477 (official Raspberry Pi HQ camera)
- IMX296 (official Raspberry Pi GS camera)
- IMX283 ([OneInchEye](https://www.tindie.com/products/will123321/oneincheye-v20/) by Will Whang)
- IMX585 ([Starlight Eye](https://www.tindie.com/products/will123321/starlighteye/) by Will Whang)

## Preinstalled hardware

- [CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/)
- [Grove Base Hat](https://wiki.seeedstudio.com/Grove_Base_Hat_for_Raspberry_Pi/)
- [Adafruit I2C Quad Rotary Encoder](https://www.adafruit.com/product/5752)

## Camera stack
<img src="docs/images/camera-stack3.png" alt="Camera stack exploded" width="250"><br>
Apps change settings by updating Redis keys. CinePi-RAW listens for those updates and captures frames accordingly while Cinemate provides the camera user interface.

## Hardware
For a basic Cinemate setup you need:
- Raspberry Pi 4 or 5. The 2GB RAM version works with the prebuilt image, but 4GB is recommended if you plan to compile `cinepi-raw` on the Pi.
- Official HQ or GS camera module
- SSD drive such as a Samsung T7 formatted as `exFAT` or `ext4` and labelled `RAW`
- HDMI monitor or a phone/tablet connected to the Pi hotspot for preview

## Installation
There are three options for installing Cinemate:

### 1. Use the prebuilt image file

See the [releases section](https://github.com/Tiramisioux/cinemate/releases) for the preinstalled image and Quick Start Guide.

### 2. Clone the repo and run the one-click installer

Start from a fresh Raspberry Pi OS Lite Bookworm image. SSH to the Pi (Terminal on macOS, PowerShell on Windows):

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

### 3. Manual install

For the full manual install, configuration steps, and CLI reference, please see the [documentation/manual installation steps](https://tiramisioux.github.io/cinemate/installation-steps/).

## Customization
GPIO buttons and switches, rotary encoders and oled display for controlling camera settings such as recording, iso etc. are configured in the `~/cinemate/src/settings.json` file. On the Pi, type `editsettings` in the terminal to open this file.

## Documentation
Full manual installation instructions, configuration guides in the [documentation](https://tiramisioux.github.io/cinemate/).

## Community

Join the [CinePi Discord](https://discord.gg/Hr4dfhuK) for discussions and sharing builds.

## Acknowledgements

The [**Cinemate**](https://github.com/Tiramisioux/cinemate) stack is built on top of several open-source projects. Special thanks to all authors!

- [**CinePi-raw**](https://github.com/cinepi/cinepi-raw) – Csaba Nagy
- [**IMX585 and IMX283 drivers**](https://github.com/will127534) – Will Whang
- [**libcamera**](https://libcamera.org) – Ideas on board
- [**cpp-mjpeg-streamer**](https://github.com/nadjieb/cpp-mjpeg-streamer) – Nadjieb Mohammadi
- [**lgpio**](https://github.com/joan2937/lg) – Joan
- [**PiShrink**](https://github.com/Drewsif/PiShrink) - Drew Bonasera 

Also thanks to Simon at [Altcinecam](https://altcinecam.com) for support and assistance!

Get your sensors and CFE Hats here: https://www.tindie.com/stores/will123321/

## Supporting the project

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G2G21IM9RO)
