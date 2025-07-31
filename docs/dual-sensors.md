# Dual sensors

CineMate automatically detects each camera connected to the Raspberry Pi and spawns a separate `cinepi-raw` process per sensor. By default:

- **Primary camera** (first detected) displays its preview on HDMI port 0.
- **Secondary cameras** run with `--nopreview` and map to subsequent HDMI outputs (cam1→HDMI 1, cam2→HDMI 2, etc.).
- Preview windows are centered and sized according to your `geometry` settings.

Cameras are synchronized with cam0 being the server and cam1 being the client.

On Raspberry Pi 5 carrier boards, the second CSI connector may appear as `i2c@70000` in `--list-cameras`. Cinemate maps this path to **cam1** so each sensor gets the correct port assignment.

You can override default HDMI mappings in `settings.json` under the `output` section.