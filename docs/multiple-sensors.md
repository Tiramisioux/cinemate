# Multi camera support <img src="https://img.shields.io/badge/cinepi--raw%20fork-ff69b4?style=flat" height="14">

CineMate automatically detects each camera connected to the Raspberry Pi and spawns a separate `cinepi-raw` process per sensor. By default:

- **Primary camera** (first detected) displays its preview on HDMI port 0.
- **Secondary cameras** run with `--nopreview` and map to subsequent HDMI outputs (cam1→HDMI 1, cam2→HDMI 2, etc.).
- Preview windows are centered and sized according to your `geometry` settings.

You can override default HDMI mappings in `settings.json` under the `output` section: