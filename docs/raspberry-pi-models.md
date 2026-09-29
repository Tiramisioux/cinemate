# Raspberry Pi models

CineMate runs on the Pi 5 family and the Pi 4 family. The two use different camera hardware, so a few things depend on your board. Check this page before you connect a sensor.

## Which model do you have

| | Pi 5 / CM5 | Pi 4 / Pi 400 / CM4 |
|---|---|---|
| Camera pipeline | PiSP (RP1 southbridge) | VC4 (unicam) |
| Camera connector | 22-pin, 0.5 mm | 15-pin, 1 mm |
| Camera ports | 2 (`cam0`, `cam1`), both 4-lane | Pi 4 / Pi 400: 1 port. CM4 IO board: 2 ports, `cam0` is 2-lane, `cam1` is 4-lane |
| Raw packing | unpacked (`U`) | packed (`P`) for IMX296 and IMX477 |
| ClearHDR 16-bit | supported (kernel 6.12.93+rpt or newer) | not supported |
| RP1 overclock | supported | not applicable, there is no RP1 |
| Tuning files | `pisp` | `vc4` |

CineMate picks the packing, the tuning target and the launch options for your board. You do not set them.

Not sure what you have? Run:

```bash
cat /proc/device-tree/model
```

## First: connector and cable

| Board | Camera port | Cable to the sensor |
|---|---|---|
| Pi 5, CM5 IO board | 22-pin | Use the 22-pin cable that comes with the sensor, or a 15-pin to 22-pin adapter cable |
| Pi 4, Pi 400, CM4 IO board | 15-pin | Use a standard 15-pin cable |

- Power the Pi off before you connect or disconnect the ribbon.
- Push the ribbon in fully and close the latch. Check your sensor board's own guide for the contact orientation.
- A ribbon that is a little loose still lets the sensor answer on I2C, so the driver loads and the modes list normally. No frames arrive.

## What to think about, per model

### Raspberry Pi 5 and CM5

- **Kernel.** CineMate is validated on **6.12.93+rpt**. An older kernel silently corrupts 16-bit CSI capture. Check with `uname -r`. See [Manual installation](installation-steps.md).
- **RAM.** 4 GB or more. A 2 GB board trips the memory guard at UHD and 4K.
- **Both ports are 4-lane.** Any sensor can go on `cam0` or `cam1`. Name the port in the overlay, for example `dtoverlay=imx585,cam1`.
- **RP1 overclock.** Optional, and it raises the imx585 ClearHDR frame rates. See [Overclocking](overclocking.md).
- **Carrier boards (CM5).** Check that your carrier exposes the camera connector you plan to use, and that any camera-enable jumpers it has are fitted (see the next section).

### Raspberry Pi 4 and Pi 400

- **One camera port**, 15-pin, and no `cam0` or `cam1` choice. Leave the port name out of the overlay: `dtoverlay=imx477`.
- **The port is 2-lane.** A sensor that needs four lanes for its faster modes will not reach them here.
- **No ClearHDR 16-bit and no RP1 overclock.** Both need the Pi 5.
- **Packed raw.** CineMate switches IMX296 and IMX477 to packed mode on its own. See [Camera sensors and frame rates](sensors.md).
- **Dual sensors** are not possible on a board with one port.

### Compute Module 4 (CM4)

The CM4 behaves like a Pi 4 but depends on the carrier board.

- **Port names matter.** On the official CM4 IO board, `cam0` is wired for **2 lanes** and `cam1` for **4 lanes**. Put a 4-lane sensor on `cam1`.
- **Jumpers.** Fit the camera jumpers on the carrier (`J6` on the official IO board). Without them the sensor may not get its control lines. Third-party carriers differ, so read your carrier's documentation.
- **Cable.** Both ports are 15-pin.
- **Check `config.txt`.** A `config.txt` written for another board can still say `cam0`. Change it to match the port you use. See [Boot config](config-txt.md).

!!! note "Verified on hardware, 2026-09-29"
    An IMX283 on a CM4 Rev 1.1 carrier with `dtoverlay=imx283,cam0` loaded the driver and negotiated its modes, but no frames arrived. CineMate logged `Camera frontend has timed out`, and this happened on every mode, so it was not a mode problem. Moving the ribbon to `cam1` and using `dtoverlay=imx283` fixed it. Whether `cam0`'s 2-lane wiring or the `J6` jumpers was the cause was not separated.

## Symptoms and what they mean

| What you see | Likely cause |
|---|---|
| The preview is black. CineMate logs `Camera frontend has timed out`. | No frames from the sensor. Reseat the cable, check the port and the overlay, check the jumpers. |
| The sensor is listed and the modes look right, but nothing arrives | The same. I2C worked, the data link did not. Suspect the cable, the port's lane count and the jumpers, in that order. |
| No sensor is listed at all | Wrong overlay, wrong port name, or a cable that is not seated. See [Boot config](config-txt.md). |
| 16-bit ClearHDR looks like noise on a Pi 5 | An old kernel. Check `uname -r` against 6.12.93+rpt. |

!!! tip "Test the link without CineMate"
    Stop CineMate, then run
    `timeout 15 v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=10 --stream-to=/dev/null; echo "exit=$?"`.
    `exit=0` means frames arrive and the problem is higher up. `exit=124` means the sensor sends nothing, so look at the cable, the port and the jumpers.
