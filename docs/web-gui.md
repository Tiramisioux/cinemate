# Web GUI

Cinemate includes a small Flask + Socket.IO web interface that mirrors most of the on-camera
HDMI GUI ([Simple GUI](simple-gui.md)) in a browser: the status badges and live
preview match, and most HDMI fields reach the page — but not all of them. The recording-integrity
counts (frame count, frames-in-sync, missing-frame count, drop-frame flags) and a few host/label
fields are HDMI-only today; run `tools/gui_field_extract.py` for the current, exact list rather
than trusting a number here, since it moves as fields get added to either side.

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
- the page reloads automatically once a resolution change completes, unless a recording is in
  progress
- live preview from the MJPEG stream
- tap/click on the preview area to toggle REC
- CineMate Log toggle (`set log`) and storage unmount button (`unmount`)
- fullscreen toggle
- the EXPERIMENT drawer (below)
- the same status rail as the HDMI GUI: sensor/aspect/log/DROP/SYNC badges, zoom and anamorphic
  factor, connected USB/mic/keyboard, storage type and filesystem
- live stats such as free space, write speed, buffered frames, buffer size, CPU load, RAM load,
  temperature, and exposure time

The layout scales rather than reflows: the same three-column arrangement (left status rail,
preview, right status rail) holds at any width or orientation, with the rails and top-row text
shrinking smoothly on a narrow or portrait screen instead of restacking into a different layout
— the same model `simple_gui.py` already uses for the HDMI GUI, which scales its entire
1920×1080-authored layout by a single `disp_width/1920`, `disp_height/1080` ratio and never
restacks either. Two exceptions to the pure ratio: the clip name and the WAV badge have pixel
floors (10px/8px) so they stay legible on a phone, where the HDMI ratio would shrink them below
readable size.

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
| EXPOSURE | ISO, nominal shutter angle, FPS, white balance |
| CLEARHDR | HDR threshold low/high, HDR blend, HDR gain adder — **only on a sensor with ClearHDR modes** |
| PREVIEW | Zoom |
| MODES | ISO/shutter/FPS/combined/all locks, shutter-angle sync, FPS double, dynamic resolution, IR filter |
| FREE STEPPING | Free stepping for ISO, shutter, FPS and WB, plus the four HDR knobs on a ClearHDR sensor |
| SELECT | Anamorphic factor, HDMI preview source (dual-sensor rigs only) |
| ACTIONS | `mount`, `toggle mount`, `storage preroll`, `set rtc time` |

Notes:

- The CLEARHDR group is absent entirely on a sensor without ClearHDR modes (imx477, imx283 …).
  On an imx585 it is present, but the knobs only do something while a ClearHDR mode is selected;
  see [clear-hdr.md](clear-hdr.md).
- Anamorphic factor restarts the camera. Everything else in the drawer applies live.
- Free stepping changes a parameter's `inc`/`dec` granularity, not its value: it swaps that
  parameter's step table in `settings.jsonc` for continuous stepping by its `free_increment`.
- ISO, shutter angle, FPS and white balance are also in the top row as steppers. The sliders are
  the same commands — use whichever suits the gesture.
- A slider is one of two kinds, decided by what its command does with an arbitrary value:

    | Kind | Controls | Behaviour |
    |---|---|---|
    | Continuous | ISO, zoom | The command clamps to a range, so any position on the track is reachable |
    | Step table | Shutter angle, FPS, WB | The command snaps to a table, so the slider offers exactly that table's values and nothing else |

    The step tables are live. Change the frame rate and the shutter slider re-grids to the new
    flicker-free angles; change sensor mode and the FPS slider re-grids to the new ceiling; toggle a
    free-stepping button and the affected slider swaps its preset table for a continuous grid.
- A slider greys out and stops accepting input when its parameter is locked (`ISO LOCK`, `SHUTTER
  LOCK`, `FPS LOCK`, `ALL LOCK`) — a locked parameter drops the write silently, so the row says so
  rather than appearing to accept a value. The FPS slider also greys out while a resolution switch
  is in flight, because that is the one setter that can block for seconds.
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
