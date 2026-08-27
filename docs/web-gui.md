# Web GUI

Cinemate includes a small Flask + Socket.IO web interface that mirrors the on-camera HDMI GUI
([hardware-controls.md](hardware-controls.md)) in a browser: same field layout, same status
badges, same live preview.

- the control UI listens on port `5000`, with the URL `http://cinepi.local:5000/`.
- the clean MJPEG preview stream is available on port `8000` with the URL `http://cinepi.local:8000/stream`.

Every control action posts a CLI command line to [`/api/v1/cmd`](web-api.md) — the same dispatcher
the CLI and serial paths use, so the browser cannot drift from them. GPIO, the analog pots, the
quad rotary encoder, storage pre-roll and the on-camera HDMI GUI call the controller directly and
bypass this dispatcher. The pots now serialise against it through a shared lock, closing the
pot-vs-explicit-set race where a moving pot could out-write an explicit `set` — but the other
bypassing paths do not, and a GPIO press can still race a web command with nothing between them.
Socket.IO only pushes live values back to the page; it carries no control events.

The browser UI exposes:

- ISO, shutter angle, FPS, white balance, and resolution selectors
- live preview from the MJPEG stream
- tap/click on the preview area to toggle REC
- CineMate Log toggle (`set log`) and storage unmount button (`unmount`)
- fullscreen toggle
- the EXPERIMENT drawer (below)
- the same status rail as the HDMI GUI: sensor/aspect/log/DROP/SYNC badges, zoom and anamorphic
  factor, connected USB/mic/keyboard, storage type and filesystem
- live stats such as free space, write speed, buffered frames, buffer size, CPU load, RAM load,
  temperature, and exposure time

The layout is responsive rather than a fixed canvas: on a narrow or portrait screen the status
rail collapses into a horizontal strip above the preview instead of a fixed side column.

## The EXPERIMENT drawer

`EXPERIMENT` opens a panel at the bottom of the page holding the controls the instrument layout
above does not show. It is collapsed by default. The preview stays put while it is open — the
drawer scrolls inside its own height cap rather than pushing the picture off the top — so a
change can be watched on the stream as it is made.

Opening the drawer does not reflow the page. The top row does not move, the status rails keep
their layout, and nothing changes order. The preview scales down to make room and the bottom rows
ride up with it; that is the only movement.

| Group | Controls |
|---|---|
| LIVE VALUES | HDR threshold low/high, HDR blend, HDR gain adder, zoom, nominal shutter angle |
| MODES | ISO/shutter/FPS/combined/all locks, shutter-angle sync, FPS double, dynamic resolution, IR filter |
| FREE STEPPING | Free stepping for ISO, shutter, FPS, WB and each of the four HDR knobs |
| SELECT | Anamorphic factor, HDMI preview source (dual-sensor rigs only) |
| ACTIONS | `mount`, `toggle mount`, `storage preroll`, `set rtc time` |

Notes:

- The HDR knobs are the imx585 ClearHDR live controls. They only do something on a ClearHDR mode;
  see [clear-hdr.md](clear-hdr.md).
- Anamorphic factor restarts the camera. Everything else in the drawer applies live.
- Free stepping changes a parameter's `inc`/`dec` granularity, not its value: it swaps that
  parameter's step table in `settings.jsonc` for continuous stepping by its `free_increment`.
- Each slider has a `↺` arrow that restores that control's startup value from `settings.jsonc`
  (`image_capture.hdr.*` for the HDR knobs, `hdmi_display.preview.default_zoom` for zoom, 180° for
  nominal shutter angle). It greys out when the value is already the default.
- Sliders show the live value, so one moves when a pot, the quad rotary, serial or the CLI changes
  the same parameter. A slider you have just moved holds where you put it until the camera reports
  the same value back — it does not spring back mid-round-trip. If the value never comes back the
  write did not stick, and after a few seconds the slider returns to the true value; the reason
  appears as a banner (`requested 8, live value is 4`).
- `erase`, `format`, `reboot` and `shutdown` are deliberately absent — they are the four commands
  the web API blocks unless `allow_destructive` is set. Use the
  [CLI](cli-commands.md) for those.

!!! note ""

    When using dual sensors, the second camera's preview stream is served on port `8001` and shown
    side-by-side with cam0, with its own status column. The control UI stays on port `5000`.
