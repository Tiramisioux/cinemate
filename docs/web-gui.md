# Web GUI

Cinemate includes a small Flask + Socket.IO web interface that mirrors the on-camera HDMI GUI
([hardware-controls.md](hardware-controls.md)) in a browser: same field layout, same status
badges, same live preview.

- the control UI listens on port `5000`, with the URL `http://cinepi.local:5000/`.
- the clean MJPEG preview stream is available on port `8000` with the URL `http://cinepi.local:8000/stream`.

Every control action posts a CLI command line to [`/api/v1/cmd`](web-api.md) — the same dispatcher
the CLI, serial and GPIO paths use, so the browser cannot drift from them. Socket.IO only pushes
live values back to the page; it carries no control events.

The browser UI exposes:

- ISO, shutter angle, FPS, white balance, and resolution selectors
- live preview from the MJPEG stream
- tap/click on the preview area to toggle REC
- CineMate Log toggle (`set log`) and storage unmount button (`unmount`)
- fullscreen toggle
- the same status rail as the HDMI GUI: sensor/aspect/log/DROP/SYNC badges, zoom and anamorphic
  factor, connected USB/mic/keyboard, storage type and filesystem
- live stats such as free space, write speed, buffered frames, buffer size, CPU load, RAM load,
  temperature, and exposure time

The layout is responsive rather than a fixed canvas: on a narrow or portrait screen the status
rail collapses into a horizontal strip above the preview instead of a fixed side column.

!!! note ""

    When using dual sensors, the second camera's preview stream is served on port `8001` and shown
    side-by-side with cam0, with its own status column. The control UI stays on port `5000`.
