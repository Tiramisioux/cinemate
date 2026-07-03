# Using CinePi-RAW from the terminal

## Checking available options

Before running the program you can view all command‑line flags with:

```bash
cinepi-raw -h
```

This prints a long list of options supported by the application. It includes the standard parameters from `rpicam-apps` (such as resolution and exposure settings) plus additional flags specific to the Cinemate.

## Camera modes

CinePi-Raw uses **Libcamera** to talk to your Raspberry Pi camera module. Each sensor supports one or more *modes*, which define the resolution and bit depth of the RAW images that the sensor can produce. A mode is written as:

```
--mode 2028:1080:12:U
```

- `width` and `height` select the active pixel area of the sensor.
- `bit-depth` is usually 10, 12 or 16 bits per pixel.
- `packing` can be `P` for packed or `U` for unpacked data. 

The mode must match the sensor you are using. For example, an IMX477 camera can run at `4056:3040:12` (full sensor) or at smaller cropped resolutions. When specifying a mode you typically also set the output `--width` and `--height` which control the size of the image written to disk. These can be equal to the mode values or smaller when scaling is applied.

!!! note ""

    On Raspberry Pi 5 / CM5, the cinepi-raw flag for the HQ sensor is `--mode 2028:1080:12:U`. On Raspberry Pi 4 / Pi 400 / CM4 it should read `--mode 2028:1080:12:P`. IMX296 follows the same packing rule, but with its 10-bit sensor mode: `1456:1088:10:U` on Pi 5 and `1456:1088:10:P` on Pi 4.


## Low‑resolution (lores) stream

```
--lores-width 1280 --lores-height 720
```

CinePi-raw can produce a secondary low‑resolution stream alongside the full‑resolution RAW frames.

## Preview window

By default the program opens an HDMI preview so you can see what the camera captures. The size and position of this window are controlled with:

```
-p 0,30,1920,1020
```

This positions the preview 30 pixels from the top of the screen with a 1920×1020 window.

## Tuning file

```
--tuning-file /home/pi/libcamera/src/ipa/rpi/pisp/data/{model_key}.json
```

Describes the camera’s colour and lens characteristics. Point to a file supplied with Libcamera (for example `/home/pi/libcamera/src/ipa/rpi/pisp/data/imx477.json` for the HQ camera)

## Post processing

```
--post-process-file /home/pi/post-processing.json
```

For cinepi-raw, this file defines the port used by cpp-mjpeg-streamer (default cinepi.local:8000)

!!! note ""

    If you have more than one camera connected to the Pi, and activated in `boot/firmware/config.txt`, the camera connected to physical cam0 will use `/home/pi/post-processing0.json` and the camera connected to cam1 will use `/home/pi/post-processing1.json`.

## Cinemate‑specific flags

The CineMate fork introduces several extra options:

| Flag               | Argument               |Description                 |
| ------------------ | ---------------------- | -------------------------- |
| `--cam-port`  | `cam0` \| `cam1`   | Select which CSI camera port to use.                                                        |
| `--hdmi-port` | `0` \| `1` \| `-1` | Choose the HDMI connector for the preview (`0` = HDMI-0, `1` = HDMI-1, `-1` = auto-detect). |
| `--same-hdmi` | *(none)*           | Force both capture and controller GUI to share the same HDMI output.                        |
| `--keep16`    | `true` \| `false`  | Save full 16-bit DNGs instead of 12-bit packed files.                                       |

!!! note ""

    At this moment though, Cinemate is 12bit only. The flag is for future updates of the IMX585 16bit clear HDR modes.

## Example commands

Below are sample commands for different sensors and modes. 

### IMX477 (12-bit, full width)

```bash
cinepi-raw --mode 4056:2160:12:U --width 4056 --height 2160 \
           --lores-width 1280 --lores-height 720 \
           -p 0,30,1920,1020 \
           --post-process-file /home/pi/post-processing.json \
           --tuning-file /home/pi/libcamera/src/ipa/rpi/pisp/data/imx477.json
```

On Raspberry Pi 4 / Pi 400 / CM4, use `--mode 4056:2160:12:P` and omit the PiSP tuning file path.

### IMX296 (10-bit)

```bash
# Raspberry Pi 5 / CM5
cinepi-raw --mode 1456:1088:10:U --width 1456 --height 1088 \
           --lores-width 1280 --lores-height 720 \
           -p 0,30,1920,1020 \
           --post-process-file /home/pi/post-processing.json \
           --tuning-file /home/pi/libcamera/src/ipa/rpi/pisp/data/imx296.json

# Raspberry Pi 4 / Pi 400 / CM4
cinepi-raw --mode 1456:1088:10:P --width 1456 --height 1088 \
           --lores-width 1280 --lores-height 720 \
           -p 0,30,1920,1020 \
           --post-process-file /home/pi/post-processing.json
```

### IMX283 (12-bit unpacked)

```bash
cinepi-raw --mode 2736:1538:12:U --width 2736 --height 1538 \
           --lores-width 1280 --lores-height 720 \
           -p 0,30,1920,1020 \
           --post-process-file /home/pi/post-processing.json \
           --tuning-file /home/pi/libcamera/src/ipa/rpi/pisp/data/imx283.json
```

### IMX585 (12-bit unpacked)

```bash
cinepi-raw --mode 1928:1090:12:U --width 1928 --height 1090 \
           --lores-width 1280 --lores-height 720 \
           -p 0,30,1920,1020 \
           --post-process-file /home/pi/post-processing.json \
           --tuning-file /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585.json
```

Now, with an SSH shell running redis-cli you should be able to capture RAW footage from the command line!

```shell
redis-cli
> set is_recording 1
> publish cp_controls is_recording
```
