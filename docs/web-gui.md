# Web GUI

Cinemate includes a small Flask + Socket.IO web interface that mirrors the live preview and exposes the main camera controls in a browser.

## When it starts

The web module starts only if the Pi already has an IPv4 address on `wlan0` or `eth0`. If neither interface has an address yet, Cinemate skips the web server for that boot and the HDMI GUI continues to run on its own. Because that check currently happens only during startup, bringing networking up later requires restarting Cinemate if you want the web UI to appear.

When the web module is active:

- the control UI listens on port `5000`
- the clean MJPEG preview stream is available on port `8000`

Typical URLs are:

- `http://<ip-address>:5000/`
- `http://<ip-address>:8000/stream`

## What it does

The browser UI exposes:

- ISO, shutter angle, FPS, white balance, and resolution selectors
- live preview from the MJPEG stream
- tap/click on the preview area to toggle REC
- storage unmount button
- fullscreen toggle
- live stats such as free space, write speed, buffered frames, buffer size, CPU load, RAM load, temperature, and exposure time

The page background follows the same status colour changes as the Simple GUI through Socket.IO events.

## Live updates and reloads

On connect, the browser receives the current camera state, available resolution modes, and the current GUI values.

Socket.IO then pushes:

- parameter changes such as ISO, shutter angle, FPS, white balance, frame buffer, and background colour
- updated shutter-angle and FPS option lists when those arrays change
- browser reload requests after pipeline-affecting changes such as resolution changes
