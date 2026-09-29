# The CineMate stack explained


![The CineMate camera stack, exploded](images/camera-stack3.png)

## The layers

| Layer | What it is | Responsible for | Documented in |
| --- | --- | --- | --- |
| Sensor kernel driver | A V4L2 kernel module, selected by a `dtoverlay=` line in `config.txt` | Register writes to the sensor, the readout modes it offers, sensor-specific controls such as ClearHDR | [Boot config](config-txt.md), [Camera sensors and frame rates](sensors.md) |
| libcamera | The libcamera camera framework, in Raspberry Pi's fork of it, built here from this project's own fork (`Tiramisioux/libcamera`, branch `cinemate`) | Configuring streams, applying controls such as analogue gain and frame duration, delivering completed frame requests | [Manual installation](installation-steps.md) |
| cinepi-raw | A C++ fork of `rpicam-apps`, built on [CinePi RAW](https://github.com/cinepi) | The capture loop, the CinemaDNG writer, the HDMI and MJPEG previews, and a separate audio-capture process | [Recompiling cinepi-raw](compiling-cinepi-raw.md), [CinePi RAW terminal commands](cli-user-guide.md) |
| Redis | In-memory key-value store with publish/subscribe channels | Holding live state (`iso`, `fps`, `is_recording`, …), carrying control changes down on the `cp_controls` channel and per-frame stats up on `cp_stats` | [Redis API](redis-guide.md), [Redis key reference](redis-keys.md) |
| CineMate | A Python program, `src/main.py` | All operator surfaces, storage handling, settings, and launching cinepi-raw | [Simple GUI](simple-gui.md), [Web GUI](web-gui.md), [Terminal commands](cli-commands.md) |

## What runs as what

Six systemd units, and the important thing about them is what does *not* depend on CineMate.

| Unit                          | What it is                                                                 |
| ----------------------------- | -------------------------------------------------------------------------- |
| `cinemate-autostart.service`  | CineMate itself, started at boot                                           |
| `redis-server`                | The key-value store both programs depend on. Enabled by the installer      |
| `storage-automount.service`   | Mounts removable drives, `RAW`-labelled ones at `/media/RAW`               |
| `wifi-hotspot.service`        | The `CinePi` access point. Independent of CineMate, so it survives a crash |
| `cinemate-recovery.service`   | A root-run console on port `8080` for a camera that will not start         |
| `redis-log-maintenance.timer` | Keeps the Redis log from filling the root filesystem                       |

Fore more information on each unit, check [System
services](system-services.md).
