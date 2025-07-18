# Quick start

## Hardware requirements
- Raspberry Pi 5
- Official HQ or Global Shutter camera
- HDMI monitor or a phone/tablet for monitoring

## Installation
1. **Burn the Cinemate image** to an SD card (8&nbsp;GB or larger).
2. **Connect the Pi and the camera sensor board.**
   > **Important:** Ensure the Pi is powered off before attaching the camera ribbon cable. Hot-swapping the cable is not advised.
3. **Boot the Pi.** CineMate should start automatically.
4. **Previewing the image**
   - Plug in an HDMI monitor **or** connect your phone/tablet to the Wi‑Fi network `CinePi` (password `11111111`).
   - Open a browser and go to `cinepi.local:5000` to see the interface. A clean video feed without the GUI is available at `cinepi.local:8000/stream`.
5. **Recording footage**
   - Attach a high‑speed drive: an **SSD** (Samsung T7 recommended), an **NVMe drive**, or the **[CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/)**.
   - Format the drive as `ext4` and give it the label `RAW`.
   - Connect a button between **GPIO5** and **GND** (or briefly short these pins with a paper clip). When using the phone preview, you can also start/stop recording by tapping the preview.

That's it—your bare‑bones CineMate build is ready. 

>Remember to power everything down before disconnecting hardware!