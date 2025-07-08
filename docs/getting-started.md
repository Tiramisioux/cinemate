# Getting Started

This quick guide walks through building a minimal CineMate setup using only a Raspberry Pi and a camera sensor. The preview is viewed from a phone connected over Wi‑Fi.

## Requirements

- Raspberry Pi 4/5 (or CM4)
- Camera sensor such as the HQ or Global Shutter camera
- microSD card (16 GB or larger) with the CineMate image
- Phone or tablet for preview

## Assemble the hardware

1. **Connect the camera** while the Pi is powered off.
2. Insert the microSD card and boot the Pi. CineMate starts automatically.
3. The Pi creates a Wi‑Fi hotspot named `CinePi` with password `11111111`.
4. Join the hotspot on your phone and open `http://cinepi.local:5000` in a browser. A clean feed is available at `http://cinepi.local:8000/stream`.

## Recording basics

- Tap the preview screen in the browser or run `rec` over SSH to start/stop recording.
- Footage is written to a drive labeled `RAW`.

For more details see the [overview](overview.md) and the rest of this documentation.
