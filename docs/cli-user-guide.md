# CinePi-raw CLI User Guide

This guide explains how to start **CinePi-raw** from the command line. The tool is a fork of the `rpicam-apps` project and allows capturing CinemaDNG files using Raspberry Pi cameras. The examples below assume you have installed the software and its dependencies as described in the repository README.

## 1. Checking available options

Before running the program you can view all command‑line flags with:

```bash
cinepi-raw -h
```

This prints a long list of options supported by the application. It includes the standard parameters from `rpicam-apps` (such as resolution and exposure settings) plus additional flags specific to the CinePi project. If you just want to confirm that your build works, you can also display the version number using:

```bash
cinepi-raw --version
```

## 2. Camera modes

CinePi-raw uses **Libcamera** to talk to your Raspberry Pi camera module. Each sensor supports one or more *modes*, which define the resolution and bit depth of the RAW images that the sensor can produce. A mode is written as:

```
<width>:<height>:<bit-depth>[:<packing>]
```

- `width` and `height` select the active pixel area of the sensor.
- `bit-depth` is usually 12 or 16 bits per pixel.
- `packing` can be `P` for packed or `U` for unpacked data. 

The mode must match the sensor you are using. For example, an IMX477 camera can run at `4056:3040:12` (full sensor) or at smaller cropped resolutions. When specifying a mode you typically also set the output `--width` and `--height` which control the size of the image written to disk. These can be equal to the mode values or smaller when scaling is applied.

## 3. Low‑resolution (lores) stream

CinePi-raw can produce a secondary low‑resolution stream alongside the full‑resolution RAW frames. This is useful for monitoring or for algorithms that need a lighter image to work with. You enable it using:

```
--lores-width <pixels> --lores-height <pixels>
```

Setting either width or height to `0` disables the lores output.

## 4. Preview window

By default the program opens an HDMI preview so you can see what the camera captures. The size and position of this window are controlled with:

```
-p x,y,width,height
```

For example `-p 0,30,1920,1020` positions the preview 30 pixels from the top of the screen with a 1920×1020 window. If you do not want any preview, use `--nopreview`.

CineMate (the companion project) uses the preview window for its graphical interface, so you can adjust it to fit your monitor or leave it fullscreen with `--fullscreen`.

## 5. Post‑processing and tuning files

Two JSON files influence how frames are processed:

1. **Tuning file** – describes the camera’s colour and lens characteristics. Use `--tuning-file <path>` to point to a file supplied with Libcamera (for example `imx477.json` for the HQ camera or `imx585.json` for the Sony IMX585 sensor).
2. **Post‑process file** – for cinepi-raw, this file defines the port used by cpp-mjpeg-streamer (default :8000)


## 6. Cinemate‑specific flags

The CineMate fork introduces several extra options:

| Flag | Description |
|------|-------------|
| `--cam-port <string>` | Select the physical CSI port to use (`cam0` or `cam1`). |
| `--hdmi-port <int>` | Choose the HDMI connector for the preview: `0` = HDMI‑0, `1` = HDMI‑1, `-1` = auto. |
| `--same-hdmi` | Force both capture and controller GUI to share the same HDMI output. |
| `--keep16` | Save full 16‑bit DNGs instead of 12‑bit packed files. |

>At this moment though, Cinemate is 12bit only. The flag is for future updates of the IMX585 16bit clear HDR modes.

## 7. Example commands

Below are sample commands for different sensors and modes. 

### IMX477 (12‑bit, full width)

```bash
cinepi-raw --mode 4056:2160:12 --width 4056 --height 2160 \
           --lores-width 1280 --lores-height 720 \
           -p 0,30,1920,1020 \
           --post-process-file /home/pi/post-processing.json \
           --tuning-file /home/pi/libcamera/src/ipa/rpi/pisp/data/imx477.json \
```

### IMX585 (12‑bit unpacked)

```bash
cinepi-raw --mode 1928:1090:12:U --width 1928 --height 1090 \
           --lores-width 1280 --lores-height 720 \
           -p 0,30,1920,1020 \
           --post-process-file /home/pi/post-processing.json \
           --tuning-file /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585.json \
```

Now, with an SSH shell running redis-cli you should be able to capture RAW footage from the command line!
