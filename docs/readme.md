# What is it?
**Cinemate** is a boilerplate cinema camera system for Raspberry Pi 5 building on [CinePi‑RAW recorder by Csaba Nagy](https://github.com/cinepi) for enabling 12 bit (or even 16 bit) Cinema DNG recordings using off-the-shelf components.  

Cinemate provides a minimal starting point that you can extend with your own controls and accessories. 

The project combines a Python UI with a custom fork of [cinepi-raw](https://github.com/Tiramisioux/cinepi-raw/tree/rpicam-apps_1.7_custom_encoder).

<div style="text-align: center;">
  <img src="/cinemate/images/camera-stack3.png" alt="Camera stack exploded" width="60%" />
  <p><em>Figure 1: Camera stack exploded view. Apps change settings by updating Redis keys. CinePi-RAW listens for those updates and captures frames accordingly while Cinemate provides the camera user interface.</em></p>
</div>



!!! tip ""
    ## New features in version 3.1

    - fast uncompressed dng encoder, supporting both IMX 585 color and mono sensors (normal SSD's working well for HD @ 25 fps)
    - redesigned HDMI ui
    - sound recording activated
    - dual sensor support
    - punch in digital zoom of preview
    - i2c oled module and enum enhanced Redis key handling by [tevey](https://github.com/tevey)
    - selection of physical camera port cam0 or cam1
    - choose specific HDMI output port, 0 or 1
    - adapted to libcamera 0.5/rpicam-apps 1.7

## Installation
See the [releases section](https://github.com/Tiramisioux/cinemate/releases) for preinstalled image file and [Quick Start Guide](https://tiramisioux.github.io/cinemate/getting-started/). 

For manual install of the camera stack on Raspberry Pi Bookworm, see the [here](https://tiramisioux.github.io/cinemate/installation-steps/).

## Compatible sensors

- IMX477 (official Raspberry Pi HQ camera)
- IMX294 (official Raspberry Pi GS camera)
- IMX585 ([Starlight Eye](https://www.tindie.com/products/will123321/starlighteye/) by Will Whang)
- IMX283 ([OneInchEye](https://www.tindie.com/products/will123321/oneincheye-v20/) by Will Whang)

## Preinstalled hardware

- [CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/)
- [Grove Base Hat](https://wiki.seeedstudio.com/Grove_Base_Hat_for_Raspberry_Pi/)
- [Adafruit I2C Quad Rotary Encoder](https://www.adafruit.com/product/5752)

## Customization
Buttons, encoders and oled display are optional and configured via [the settings file](https://tiramisioux.github.io/cinemate/settings-json/).

<!-- ## Documentation
Full manual installation instructions, configuration guides and CLI reference live [here](https://tiramisioux.github.io/cinemate/). -->

Join the [CinePi Discord](https://discord.gg/Hr4dfhuK) for discussions and sharing builds.

## Supporting the project

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G2G21IM9RO)
