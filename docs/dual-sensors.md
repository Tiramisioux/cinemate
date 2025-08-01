# Dual sensors

CineMate automatically detects each camera connected to the Raspberry Pi and spawns a separate `cinepi-raw` process per sensor. By default:

- **Primary camera** (first detected) displays its preview on HDMI port 0.
- **Secondary cameras** run with `--nopreview` and map to subsequent HDMI outputs (cam1→HDMI 1, cam2→HDMI 2, etc.).
- Preview windows are centered and sized according to your `geometry` settings.

Cameras are synchronized with cam0 being the server and cam1 being the client.

On Raspberry Pi 5 Compute Model carrier boards, the second CSI connector (cam1) may appear as `i2c@70000` in `--list-cameras`. Cinemate maps this path to **cam1** so each sensor gets the correct port assignment.

!!! note ""
    When using the cam1 with the official Raspberry Pi CM carrier board, make sure to connect the JC GPIO pins as described here: [https://www.raspberrypi.com/documentation/computers/compute-module.html#connect-two-cameras](https://www.raspberrypi.com/documentation/computers/compute-module.html#connect-two-cameras)

You can override default HDMI mappings in `settings.json` under the `output` section.