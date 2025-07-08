# Module Overview

CineMate is organised into a collection of small modules that communicate through Redis. At the core is the `cinepi-raw` capture binary which handles all camera I/O. The Python modules orchestrate `cinepi-raw`, manage hardware controls and expose a simple GUI.

## Main pieces

- **`main.py`** – launches all services and loads `settings.json`.
- **`cinepi_controller.py`** – talks to `cinepi-raw` and forwards camera state changes to Redis.
- **`simple_gui.py`** – lightweight GUI served over Flask and displayed on HDMI or in a browser.
- **`redis_controller.py`** – central interface for publishing and reading parameters.
- **`mediator.py`** – coordinates events across modules so that button presses, CLI commands and network messages all interact consistently.

Other helpers monitor the SSD, Wi‑Fi hotspot and GPIO pins. Each component is optional and can be modified to suit a custom build.

CineMate relies on [`cinepi-raw`](https://github.com/cinepi/cinepi-raw) for image capture. The Python code starts one `cinepi-raw` process per sensor and feeds it parameters such as resolution, ISO and shutter angle.
