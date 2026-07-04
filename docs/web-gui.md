# Web GUI

Cinemate includes a small Flask + Socket.IO web interface that mirrors the live preview and exposes the main camera controls in a browser.

- the control UI listens on port `5000`, with the URL `http://cinepi.local:5000/`.
- the clean MJPEG preview stream is available on port `8000` with the URL `http://cinepi.local:8000/stream`.

The browser UI exposes:

- ISO, shutter angle, FPS, white balance, and resolution selectors
- live preview from the MJPEG stream
- tap/click on the preview area to toggle REC
- storage unmount button
- fullscreen toggle
- live stats such as free space, write speed, buffered frames, buffer size, CPU load, RAM load, temperature, and exposure time

!!! note ""

    When using dual sensors, the second camera's preview stream is served on port `8001`. The control UI stays on port `5000`.
