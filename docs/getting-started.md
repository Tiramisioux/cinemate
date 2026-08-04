# Quick start

## Hardware requirements
- Raspberry Pi 4 or 5 / CM5. **4 GB RAM or more.** 2 GB boards run, but are not recommended for UHD/4K.
- Official HQ or Global Shutter camera
- HDMI monitor or a phone/tablet for monitoring

!!! warning "2 GB boards and UHD/4K"

    Cinemate buffers raw frames in RAM before they reach the disk. A watchdog
    polls total RAM use and **auto-stops recording at 80 %** — the HDMI GUI
    turns yellow and `memory_alert` is set.

    At UHD/4K a 2 GB board reaches that threshold quickly, so takes stop on
    their own. 4 GB is the practical minimum for 4K work. Compiling
    `cinepi-raw` on the Pi also wants 4 GB (the installer adds a temporary zram
    swap below 3 GB).

## Installation

Burn the latest [Cinemate image](https://github.com/Tiramisioux/cinemate/releases/latest) to an SD card.

Connect the Pi and the camera sensor board, connect power and boot the Pi. Cinemate autostarts on boot.

!!! danger ""

    Ensure the Pi is powered off before attaching the camera ribbon cable. Hot-swapping may damage the hardware.

## Preview
- Plug in an HDMI monitor **or** 
- Connect your phone/tablet to the Wi‑Fi network `CinePi` (password `11111111`).
Open a browser and go to `cinepi.local:5000` to see the interface. A clean video feed without the GUI is available at `cinepi.local:8000/stream`.


## Recording
- Attach a high‑speed drive: an **SSD** (Samsung T7 recommended), an **NVMe drive**, or the **[CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/)**. Make sure storage media is formatted as `exFAT` and labeled `RAW`.

- Connect a button between **GPIO7** and **GND** — physical pins 26 and 25, right next to each other, so you can also briefly short them with a paper clip. When using the phone preview, you can also start/stop recording by tapping the preview. More buttons and dials can be added later — see [Additional hardware](hardware-controls.md).

That's it—your bare‑bones Cinemate build is ready!

!!! danger ""

    Remember to power everything down before disconnecting hardware!
