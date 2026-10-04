# Raspberry Pi models

CineMate runs on the Pi 5 family and the Pi 4 family. There are however a couple of things differing between the platforms (model B, compute models, carrier boards etc)

## Raspberry Pi 5 and CM5

- **Kernel.** CineMate is validated on **6.12.93+rpt**. An older kernel silently corrupts 16-bit CSI capture. Check with `uname -r`. See [Manual installation](installation-steps.md).
- **RAM.** 4 GB or more. A 2 GB board trips the memory guard at UHD and 4K.
- **Both ports are 4-lane.** Any sensor can go on `cam0` or `cam1`. Name the port in the overlay, for example `dtoverlay=imx585,cam1`.
- **RP1 overclock.** Optional, raises the imx585 ClearHDR frame rates. See [Overclocking](overclocking.md).
- **Carrier boards (CM5).** Check that your carrier exposes the camera connector you plan to use, and that camera-enable jumpers are connected (see the next section).

## Raspberry Pi 4B

- **One camera port**, 15-pin, and no `cam0` or `cam1` choice. Leave the port name out of the overlay: `dtoverlay=imx477`.
- **The port is 2-lane.** A sensor that needs four lanes for its faster modes will not reach them here.
- **No ClearHDR 16-bit and no RP1 overclock.** Both need the Pi 5.
- **Packed raw.** CineMate switches IMX296 and IMX477 to packed mode on its own. See [Camera sensors and frame rates](sensors.md).

## Compute Module 4 (CM4)

The CM4 behaves like a Pi 4 but depends on the carrier board.

- **For imx283 and 585, use cam port 1.** On the official CM4 IO board, `cam0` is wired for **2 lanes** and `cam1` for **4 lanes**. Put a 4-lane sensor on `cam1`.
- **Jumpers.** Fit the camera jumpers on the carrier (`J6` on the official IO board). Without them the sensor may not get its control lines. Third-party carriers differ, so read your carrier's documentation.

The [Pinefeat CEF168 lens adapter](pinefeat/index.md#platforms) works on all of the boards above. The overlay line differs per board.
