# Dual sensors

CineMate automatically detects each camera connected to the Raspberry Pi and spawns a separate `cinepi-raw` process per sensor. Cameras are synchronized with cam0 being the server and cam1 being the client.

## HDMI preview

With two sensors, both previews appear together on the on-camera HDMI monitor (HDMI-0), side-by-side, each with a white frame and a centre divider. The simple GUI columns keep their room on the left and right.

Switch which sensor(s) the monitor shows with the `set preview` command — the change is live, no restart:

| Command | Shows |
|---|---|
| `set preview both` | both side-by-side (default; `cam0+cam1` is an alias) |
| `set preview cam0` | cam0 full-screen |
| `set preview cam1` | cam1 full-screen |
| `set preview pip_cam0` | cam0 full-screen, cam1 as a corner inset (`pip` / `pip0` alias) |
| `set preview pip_cam1` | cam1 full-screen, cam0 as a corner inset (`pip1` alias) |
| `set preview` | cycles both → cam0 → cam1 → pip_cam0 → pip_cam1 |

A single selected sensor fills the preview area just like a single-sensor setup. The default source is `preview.default_hdmi_source` in [settings.json](settings-json.md); the live value is the `hdmi_preview_source` [Redis key](redis-keys.md).

### Picture-in-picture

The two `pip_*` modes show one sensor full-screen with the other shrunk into a corner. The inset geometry is set in [settings.json](settings-json.md) under `preview.pip`:

| Key | Default | Meaning |
|---|---|---|
| `scale` | `0.28` | inset size as a fraction of the main pane |
| `corner` | `lower_right` | `lower_right`, `lower_left`, `upper_right`, `upper_left` |
| `margin` | `0.03` | gap from the edge as a fraction of the pane |

If the secondary sensor hasn't produced a frame yet, pip falls back to cam0 full-screen so the monitor is never blank.

!!! note ""
    One monitor, both feeds. DRM master is exclusive per GPU, so the primary `cinepi-raw` process owns the display and composites both sensors; the secondary runs with `--nopreview` and hands its frame to the primary.

## Recording

Which sensor(s) record a take depends on the `lock_dual_recording` setting in [settings.json](settings-json.md) and, when it is off, on the preview:

**`false` — recording follows the preview.** _Note that if preview is changed while the Pi is recording, the recording has to be stopped and commenced again in order to start recording on the previewed sensor. Side-by-side records both._

**`true` — force dual.** Both sensors always record, whatever the preview shows. 

Each sensor writes to its own clip folder (`..._cam0` / `..._cam1`).

!!! note ""
    When using the cam1 with the official Raspberry Pi CM carrier board, make sure to connect the JC GPIO pins as described here: [https://www.raspberrypi.com/documentation/computers/compute-module.html#connect-two-cameras](https://www.raspberrypi.com/documentation/computers/compute-module.html#connect-two-cameras)

You can override geometry, HDMI port, camera name, and FPS correction for each port independently in `settings.json` under `camera.cam0` and `camera.cam1`. See [settings](settings-json.md#camera).
