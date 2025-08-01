# Quick start

## Hardware requirements
- Raspberry Pi 5 or 4
- Official HQ or Global Shutter camera
- HDMI monitor or a phone/tablet for monitoring

!!! tip ""

    For most users the 4GB or even 2GB models are sufficient. More RAM gives you a larger frame buffer. But ideally you don’t want to have to use the framebuffer anyway, as realtime writing to storage is preferred.
    
    There could be some rare high speed slomo cases you would want faster frame capture for short bursts but in most cases, the 4GB models will do fine.

## Installation

Burn the latest [Cinemate image](https://github.com/Tiramisioux/cinemate/releases/tag/3.1) to an SD card (8 GB or larger).

Connect the Pi and the camera sensor board, connect power an boot the Pi. Cinemate should autstart on boot. 
    
!!! danger ""   

    Ensure the Pi is powered off before attaching the camera ribbon cable. Hot-swapping may damage the hardware.

## Preview
- Plug in an HDMI monitor **or** 
- Connect your phone/tablet to the Wi‑Fi network `CinePi` (password `11111111`).
Open a browser and go to `cinepi.local:5000` to see the interface. A clean video feed without the GUI is available at `cinepi.local:8000/stream`.

## Recording
- Attach a high‑speed drive: an **SSD** (Samsung T7 recommended), an **NVMe drive**, or the **[CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/)**. Make sure storage medoa is formatted as `ext4` and labeled `RAW`.

- Connect a button between **GPIO5** and **GND** (or briefly short these pins with a paper clip). When using the phone preview, you can also start/stop recording by tapping the preview.

That's it—your bare‑bones Cinemate build is ready!

!!! danger ""

    Remember to power everything down before disconnecting hardware!