# Quick start

## Hardware requirements
- Raspberry Pi 5 or 4
- Official HQ or Global Shutter camera
- HDMI monitor or a phone/tablet for monitoring

## Installation

Burn the latest [Cinemate image](https://github.com/Tiramisioux/cinemate/releases/tag/3.1) to an SD card (8 GB or larger).

Connect the Pi and the camera sensor board.
    
!!! warning   

    Ensure the Pi is powered off before attaching the camera ribbon cable. Hot-swapping the cable is not advised.

Boot the Pi. 

## Starting Cinemate

Start Cinemate by typing `cinemate` anywhere in the terminal. To connect to the Pi from another computer, see the [ssh section](ssh.md). To enable autostart on boot, see [this section](system-services.md/#cinemate-autostartservice).

## Previewing the image
Plug in an HDMI monitor **or** connect your phone/tablet to the Wi‑Fi network `CinePi` (password `11111111`).
Open a browser and go to `cinepi.local:5000` to see the interface. A clean video feed without the GUI is available at `cinepi.local:8000/stream`.

## **Recording**
Attach a high‑speed drive: an **SSD** (Samsung T7 recommended), an **NVMe drive**, or the **[CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/)**. Make sure storage medoa is formatted as `ext4` and labeled `RAW`.

Connect a button between **GPIO5** and **GND** (or briefly short these pins with a paper clip). When using the phone preview, you can also start/stop recording by tapping the preview.

That's it—your bare‑bones Cinemate build is ready!

!!! warning

    Remember to power everything down before disconnecting hardware!