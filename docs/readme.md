# What is it?
**Cinemate** is a boilerplate cinema camera system for Raspberry Pi 4 or 5 building on [CinePi‑RAW recorder by Csaba Nagy](https://github.com/cinepi) for enabling 12 bit (or even 16 bit) Cinema DNG recordings using off-the-shelf components.

Cinemate provides a minimal starting point that you can extend with your own controls and accessories. 

The project combines a Python UI with a custom fork of [cinepi-raw](https://github.com/Tiramisioux/cinepi-raw/tree/rpicam-apps_1.7_custom_encoder).

<div style="text-align: center;">
  <img src="/cinemate/images/camera-stack3.png" alt="Camera stack exploded" width="60%" />
  <p><em>Figure 1: Camera stack exploded view. Apps change settings by updating Redis keys. CinePi-RAW listens for those updates and captures frames accordingly while Cinemate provides the camera user interface.</em></p>
</div>

## New features in version 3.3.1

`cinepi-raw` recorder updates:

- new Cinemate fork of `cinepi-raw`, reducing CPU load and temperature dramatically and reducing dropped frames

- resolution can now be changed in `cinepi-raw` without restarting the recorder process, enabling faster mode changes and dynamic resolution switching

- better USB microphone sync

Cinemate workflow updates:

- exFAT support and filesystem-aware storage profiles for efficient media writes, including IMX585 25 fps at 4K to SSD without frame drops

- dynamic resolution switching to match the observed sustainable frame rate for the attached sensor and storage media; for example, IMX585 automatically switches to HD above 25 fps when SSD is used for storage

- hot-swapping between 16-bit and 24-bit USB microphones

- 4K-class recording modes are visible by default

- storage pre-roll can be disabled in `settings.json`

## Installation
See the [releases section](https://github.com/Tiramisioux/cinemate/releases) for preinstalled image file and [Quick Start Guide](https://tiramisioux.github.io/cinemate/getting-started/). 

For a repo-root one-click install or a manual install of the camera stack on Raspberry Pi OS Lite (Bookworm), see the [installation guide](https://tiramisioux.github.io/cinemate/installation-steps/). The one-click installer defaults to IMX477 on `cam0`; override it inline for other sensors:

```bash
SENSOR_MODEL=imx296 CAM_PORT=cam0 ./cinemate-install.sh
SENSOR_MODEL=imx283 CAM_PORT=cam0 ./cinemate-install.sh
SENSOR_MODEL=imx585 CAM_PORT=cam0 ./cinemate-install.sh
```

## Compatible sensors

- IMX477 (official Raspberry Pi HQ camera)
- IMX296 (official Raspberry Pi GS camera)
- IMX283 ([OneInchEye](https://www.tindie.com/products/will123321/oneincheye-v20/) by Will Whang)
- IMX585 ([Starlight Eye](https://www.tindie.com/products/will123321/starlighteye/) by Will Whang)

## Preinstalled hardware

- [CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/)
- [Grove Base Hat](https://wiki.seeedstudio.com/Grove_Base_Hat_for_Raspberry_Pi/)
- [Adafruit I2C Quad Rotary Encoder](https://www.adafruit.com/product/5752)

## Customization
GPIO buttons and switches, rotary encoders and oled display are optional and configured via [the settings file](https://tiramisioux.github.io/cinemate/settings-json/). On the Pi, type `editsettings` in the terminal to open this file.

<!-- ## Documentation
Full manual installation instructions, configuration guides and CLI reference live [here](https://tiramisioux.github.io/cinemate/). -->

Join the [CinePi Discord](https://discord.gg/Hr4dfhuK) for discussions and sharing builds.

## Supporting the project

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G2G21IM9RO)
