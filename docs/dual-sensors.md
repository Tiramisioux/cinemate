# Dual sensors

CineMate automatically detects each camera connected to the Raspberry Pi and spawns a separate `cinepi-raw` process per sensor. Cameras are synchronized with cam0 being the server and cam1 being the client.

## HDMI preview

With two sensors, both previews appear together on the on-camera HDMI monitor (HDMI-0), side-by-side, each with a white frame and a centre divider. The simple GUI columns keep their room on the left and right.

Switch which sensor(s) the monitor shows with the `set preview` command — the change is live, no restart:

| Command | Shows |
|---|---|
| `set preview cam0` | cam0 full-screen |
| `set preview cam1` | cam1 full-screen |
| `set preview cam0+cam1` | both side-by-side (default) |
| `set preview` | cycles both → cam0 → cam1 |

A single selected sensor fills the preview area just like a single-sensor setup. The default source is `preview.default_hdmi_source` in [settings.json](settings-json.md); the live value is the `hdmi_preview_source` [Redis key](redis-keys.md).

!!! note ""
    One monitor, both feeds. DRM master is exclusive per GPU, so the primary `cinepi-raw` process owns the display and composites both sensors; the secondary runs with `--nopreview` and hands its frame to the primary.

On Raspberry Pi 5 Compute Model carrier boards, the second CSI connector (cam1) may appear as `i2c@70000` in `--list-cameras`. Cinemate maps this path to **cam1** so each sensor gets the correct port assignment.

!!! note ""
    When using the cam1 with the official Raspberry Pi CM carrier board, make sure to connect the JC GPIO pins as described here: [https://www.raspberrypi.com/documentation/computers/compute-module.html#connect-two-cameras](https://www.raspberrypi.com/documentation/computers/compute-module.html#connect-two-cameras)

You can override geometry, HDMI port, camera name, and FPS correction for each port independently in `settings.json` under `camera.cam0` and `camera.cam1`. See [settings](settings-json.md#camera).
