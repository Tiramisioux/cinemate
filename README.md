# What is it?

**Cinemate** is a boilerplate cinema camera system for Raspberry Pi 5.  builds upon CinePi-raw, authored by Csaba Nagy for enabling 12bit (or even 16 bit) Cinema DNG recordings using off-the-shelf components.  

Cinemate provides a minimal starting point that you can extend with your own controls and accessories. The project pairs a small Python UI with a custom fork of [cinepi-raw](https://github.com/Tiramisioux/cinepi-raw/tree/rpicam-apps_1.7_custom_encoder).

## Camera stack

1. **Camera sensor** connected to the Raspberry Pi
2. Raspberry Pi SoC running **libcamera**
3. **cinepi-raw** recorder (C++)
4. **Redis** key-value store
5. **Cinemate** (Python)

Apps change settings by updating Redis keys. CinePi-raw listens for those updates and captures frames accordingly while Cinemate provides the camear user interface.

## Bare-bones build
To try Cinemate you need:
- Raspberry Pi&nbsp;5
- Official HQ or GS camera module
- SSD drive such as a Samsung T7 formatted `ext4` and labelled `RAW`
- HDMI monitor or a phone/tablet connected to the Pi hotspot for preview

## Customization
Buttons, encoders and oled display are optional and configured via `cinemate/src/settings.json`.

CineMate is compatible with Raspberry Pi HQ camera (IMX477), Global Shutter camera (IMX296), OneInchEye (IMX283), StarlightEye (IMX585) color and monochrome variants.

## Installation

A ready-made SD card image is available from the [releases page](https://github.com/Tiramisioux/cinemate/releases).

## Documentation
Full manual installation instructions, configuration guides and CLI reference live here: https://tiramisioux.github.io/cinemate/.

Join the [CinePi Discord](https://discord.gg/Hr4dfhuK) for discussions and sharing builds.

## Acknowledgements

The [**Cinemate**](https://github.com/Tiramisioux/cinemate) stack is built on top of several open-source projects. Spåecial thanks to all authors!

- [**CinePi-raw**](https://github.com/cinepi/cinepi-raw) – Csaba Nagy
- [**IMX585 and IMX283 drivers**](https://github.com/will127534) – Will Whang
- [**libcamera**](https://libcamera.org) – Ideas on board
- [**cpp-mjpeg-streamer**](https://github.com/nadjieb/cpp-mjpeg-streamer) – Nadjieb Mohammadi
- [**lgpio**](https://github.com/joan2937/lg) – Joan
