# Overview

**Cinemate** is an open-source boilerplate for building your own digital cinema camera on a Raspberry Pi 4 or 5. It records 12-bit CinemaDNG files using off-the-shelf parts.

It pairs a lightweight Python interface with a custom fork of [cinepi-raw](https://github.com/Tiramisioux/cinepi-raw), built on the [CinePi-RAW recorder by Csaba Nagy](https://github.com/cinepi).

<div style="text-align: center;">
  <img src="/cinemate/images/camera-stack3.png" alt="Camera stack exploded" width="60%" />
  <p><em>Figure 1: The Cinemate camera stack — Cinemate (the user interface) running on top of CinePi-RAW (the recorder).</em></p>
</div>

## Installation

Easiest path is to flash the prebuilt image — see the [Quick start](getting-started.md) and the [releases page](https://github.com/Tiramisioux/cinemate/releases).

To build the stack yourself on Raspberry Pi OS Lite (Bookworm), or to use the one-click installer, see [Manual installation](installation-steps.md).

??? note "Installing for a non-default sensor"

    The one-click installer defaults to IMX477 on `cam0`. Override it inline for other sensors:

    ```bash
    SENSOR_MODEL=imx296 CAM_PORT=cam0 ./cinemate-install.sh
    SENSOR_MODEL=imx283 CAM_PORT=cam0 ./cinemate-install.sh
    SENSOR_MODEL=imx585 CAM_PORT=cam0 ./cinemate-install.sh
    ```

## Customisation

GPIO buttons and switches, rotary encoders, potentiometers and the OLED display are optional — see [Additional hardware](hardware-controls.md) for an overview. They are configured via [the settings file](settings-json.md). On the Pi, type `editsettings` in the terminal to open it.


## Compatible sensors

- IMX477 (official Raspberry Pi HQ camera)
- IMX296 (official Raspberry Pi GS camera)
- IMX283 ([OneInchEye](https://www.tindie.com/products/will123321/oneincheye-v20/) by Will Whang)
- IMX585 ([Starlight Eye](https://www.tindie.com/products/will123321/starlighteye/) by Will Whang)

## Preinstalled hardware

- [CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/)
- [Grove Base Hat](https://wiki.seeedstudio.com/Grove_Base_Hat_for_Raspberry_Pi/)
- [Adafruit I2C Quad Rotary Encoder](https://www.adafruit.com/product/5752)

## What's new

See the [changelog](changelog.md) for the latest release notes.

## Community

Join the [CinePi Discord](https://discord.gg/Hr4dfhuK) to discuss and share builds.

## Supporting the project

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G2G21IM9RO)
