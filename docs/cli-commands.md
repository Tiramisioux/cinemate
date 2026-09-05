# Commands reference

Type `cinemate` in the Raspberry Pi CLI to start CineMate manually. This stops any autostarted instance, shows the camera startup sequence and opens the CineMate pseudo-CLI, where you type the commands below.

The same strings reach the camera three other ways:

- Over serial, on the Tx/Rx pins or over USB — see [Building control units](building-control-units.md).
- Over the camera's Wi-Fi hotspot, as a POST to the [Web API](web-api.md).
- From a GPIO button, rotary encoder or potentiometer. Hardware bindings name the **method**, not the command string: put the method from the same row into a `hardware_controls` block in `settings.jsonc`. See [Additional hardware](hardware-controls.md).

!!! note ""

    Commands without an explicit argument toggle the current state when possible (e.g. `set fps lock` flips the lock; `set fps lock 1` forces it on).

!!! note ""

    `inc` / `dec` move one place through the parameter's step table and stop at its ends — they do not wrap. The two exceptions are `inc wb` / `dec wb` and `inc zoom` / `dec zoom`, which cycle around their lists.

## Recording

| Command | Argument | Method | What it does |
|---|---|---|---|
| `rec` | – | `rec` | Toggle recording. Ignored while a storage pre-roll is running. The `rec` handler also parses optional leading tokens that the argument column does not cover: a camera token (`cam0`, `cam1`, `both`) forces which sensor(s) record on a dual rig, and `s <seconds>` / `f <frames>` arm a timed stop. See [Timed recording shortcuts](#timed-recording-shortcuts). |
| `stop` | – | `rec` | Alias for the same toggle — it stops a running take and starts one when idle. It takes no arguments; the camera and timed tokens work only on `rec`. |

## ISO

| Command | Argument | Method | What it does |
|---|---|---|---|
| `set iso <value>` | int | `set_iso` | Set ISO, clamped to the low and high ends of the current step table (the value is not snapped to a step). Ignored while the ISO lock is on. |
| `inc iso` / `dec iso` | – | `inc_iso` / `dec_iso` | Step ISO up or down through `arrays.iso.steps`, or by `arrays.iso.free_increment` in free stepping. |

## Shutter angle

| Command | Argument | Method | What it does |
|---|---|---|---|
| `set shutter a <angle>` | float | `set_shutter_a` | Set the actual shutter angle. Snaps to the nearest valid angle unless free stepping or sync mode is on. Updates the exposure-time readout. |
| `inc shutter a` / `dec shutter a` | – | `inc_shutter_a` / `dec_shutter_a` | Cycle through shutter angles; `arrays.shutter_a.free_increment` in free stepping. |
| `set shutter a nom <angle>` | float | `set_shutter_a_nom` | Set the nominal shutter angle used for motion-blur calculations. Ignored while the nominal shutter lock is on. |
| `inc shutter a nom` / `dec shutter a nom` | – | `inc_shutter_a_nom` / `dec_shutter_a_nom` | Step the nominal shutter angle. |

## Frame rate

| Command | Argument | Method | What it does |
|---|---|---|---|
| `set fps <value>` | float | `set_fps` | Apply a new frame rate, respecting `fps_max`, the FPS lock and sync mode. Snaps to the FPS list unless free stepping or sync mode is on. May pick a lower sensor mode when dynamic resolution is enabled. |
| `inc fps` / `dec fps` | – | `inc_fps` / `dec_fps` | Step through the FPS list; `arrays.fps.free_increment` in free stepping. |

## White balance

| Command | Argument | Method | What it does |
|---|---|---|---|
| `set wb [<Kelvin>]` | int or none | `set_wb` | Set white balance to the nearest active WB step. Omit the value to cycle to the next step. |
| `inc wb` / `dec wb` | – | `inc_wb` / `dec_wb` | Move to the next or previous WB step, wrapping at the ends; `arrays.wb.free_increment` (100 K default) in free stepping. |

## ClearHDR

Startup values come from `image_capture.hdr` in `settings.jsonc`. All four knobs apply live to a streaming sensor — no camera restart. See [ClearHDR](clear-hdr.md).

| Command | Argument | Method | What it does |
|---|---|---|---|
| `set hdr threshold low <n>` | int | `set_hdr_threshold_low` | HG→LG data-selection threshold, low side. Clamped to 0–4095. |
| `inc hdr threshold low` / `dec hdr threshold low` | – | `inc_hdr_threshold_low` / `dec_hdr_threshold_low` | Step the low threshold; `arrays.hdr_threshold_low.free_increment` in free stepping. |
| `set hdr threshold high <n>` | int | `set_hdr_threshold_high` | HG→LG data-selection threshold, high side. Clamped to 0–4095. |
| `inc hdr threshold high` / `dec hdr threshold high` | – | `inc_hdr_threshold_high` / `dec_hdr_threshold_high` | Step the high threshold; `arrays.hdr_threshold_high.free_increment` in free stepping. |
| `set hdr blend <n>` | int | `set_hdr_blend` | Blending mode, driver menu index. Clamped to 0–8. |
| `inc hdr blend` / `dec hdr blend` | – | `inc_hdr_blend` / `dec_hdr_blend` | Step the blending mode; `arrays.hdr_blend.free_increment` in free stepping. |
| `set hdr gain adder <n>` | int | `set_hdr_gain_adder` | Low-gain gain adder, driver menu index. Clamped to 0–5 (2 = +12 dB). |
| `inc hdr gain adder` / `dec hdr gain adder` | – | `inc_hdr_gain_adder` / `dec_hdr_gain_adder` | Step the gain adder; `arrays.hdr_gain_adder.free_increment` in free stepping. |

## CineMate Log and DNG thumbnails

| Command | Argument | Method | What it does |
|---|---|---|---|
| `set log [<10\|12\|on\|off>]` | int, string or none | `set_log_encode` | Toggle [CineMate Log](cinemate-log.md) using each camera's default target for its live bit depth (16-bit → 12, 12-bit → 10). `set log 10` / `set log 12` force a target where the live bit depth supports it; `set log on` / `set log off` force a state (`yes`/`no`, `true`/`false` work too). A number other than 10 or 12 is rejected, so `set log 1` is not a synonym for `on`. Restarts the camera when idle; while recording the request is stored and applied on the next launch. |
| `set thumbnail <n>` | int | `set_thumbnail` | Embedded DNG thumbnail mode: `0` off, `1` mono, `2` colour. Applied live on the next frame, no camera restart. Affects new takes only. `thumbnail_size` is not exposed here — its handler restarts the camera. |

## Resolution and preview

| Command | Argument | Method | What it does |
|---|---|---|---|
| `set resolution [<mode>]` | int or none | `set_resolution` | Apply a sensor mode; omit the value to cycle. An aspect-ratio change relaunches cinepi-raw so the preview window is rebuilt; same-aspect changes stay seamless. With dynamic resolution on, the value becomes the desired mode. |
| `set dynamic resolution [0/1]` | 0/1 or none | `set_dynamic_resolution_enabled` | Allow or block substituting a lower-resolution mode when the requested fps exceeds the desired mode's own `fps_max`. Omit the value to toggle. |
| `set anamorphic factor [<float>]` | float or none | `set_anamorphic_factor` | Set the preview's anamorphic stretch, or omit the value to step to the next preset. The value must be one of `hdmi_display.preview.anamorphic.steps`; anything else is rejected. Restarts the camera. |
| `set zoom [<float>]` | float or none | `set_zoom` | Set the live-view digital zoom factor, clamped to `hdmi_display.preview.zoom_steps`. Omit the value to step through those steps. See [Digital zoom](digital-zoom.md). |
| `inc zoom` / `dec zoom` | – | `inc_zoom` / `dec_zoom` | Step the preview zoom factor forwards or backwards, wrapping at the ends. |
| `set preview [cam0\|cam1\|both\|pip_cam0\|pip_cam1]` | text or none | `set_preview_source` | Dual-sensor HDMI source: full screen, side-by-side, or picture-in-picture with the other sensor as a corner inset. Omit the value to cycle all five. Applied live. Mid-take it can only add sensors to the record gate, never drop one. No visible effect with a single sensor. |

## Locks and sync modes

| Command | Argument | Method | What it does |
|---|---|---|---|
| `set shutter a sync [0/1]` | 0/1 or none | `set_shutter_a_sync_mode` | Enable exposure-sync mode, keeping exposure time constant across fps changes. Pots and encoders then step in `arrays.shutter_a.sync_increment` (0.1° default), independent of `free_increment`. |
| `set iso lock [0/1]` | 0/1 or none | `set_iso_lock` | Lock or unlock ISO. |
| `set shutter a nom lock [0/1]` | 0/1 or none | `set_shutter_a_nom_lock` | Lock or unlock the nominal shutter angle. |
| `set shutter a nom fps lock [0/1]` | 0/1 or none | `set_shu_fps_lock` | Lock nominal shutter and FPS together. |
| `set fps lock [0/1]` | 0/1 or none | `set_fps_lock` | Lock or unlock the frame rate. |
| `set all lock [0/1]` | 0/1 or none | `set_all_lock` | Set ISO, nominal shutter and FPS locks at once. |
| `set fps double [0/1]` | 0/1 or none | `set_fps_double` | Double the frame rate and restore it again. Refused while recording if the doubled fps needs a different sensor mode. |

## Free stepping

Free stepping stops landing on the preset stops in `settings.jsonc` and sweeps between the lowest and highest entry of the parameter's own array instead, in `free_increment` steps. Frame rate is the exception: its ceiling is the sensor mode's `fps_max`, which the array cannot raise. Each command toggles when the argument is omitted.

| Command | Argument | Method | What it does |
|---|---|---|---|
| `set iso free [0/1]` | 0/1, text or none | `set_iso_free` | Any ISO in 100-unit steps (100–3200) instead of the presets. |
| `set shutter a free [0/1]` | 0/1, text or none | `set_shutter_a_free` | Any shutter angle in 1° steps (1–360°); values are no longer snapped. |
| `set fps free [0/1]` | 0/1, text or none | `set_fps_free` | Any FPS in 1 fps steps (1–`fps_max`). |
| `set wb free [0/1]` | 0/1, text or none | `set_wb_free` | 100 K WB steps from 2800 K to 6500 K. |
| `set hdr threshold low free [0/1]` | 0/1, text or none | `set_hdr_threshold_low_free` | 16-unit steps across the full 0–4095 range. |
| `set hdr threshold high free [0/1]` | 0/1, text or none | `set_hdr_threshold_high_free` | 16-unit steps across the full 0–4095 range. |
| `set hdr blend free [0/1]` | 0/1, text or none | `set_hdr_blend_free` | 1-unit steps across the full 0–8 range. |
| `set hdr gain adder free [0/1]` | 0/1, text or none | `set_hdr_gain_adder_free` | 1-unit steps across the full 0–5 range. |

!!! warning ""

    These eight commands also accept a text argument, but the handler stores whatever it is given and any non-empty string is truthy — `set iso free off` switches free stepping **on**. Use `0`, `1`, or no argument at all.

All step sizes above are the shipped defaults and are configurable per parameter via `arrays.<name>.free_increment` in [settings.jsonc](settings-json.md#arrays).

## Storage

| Command | Argument | Method | What it does |
|---|---|---|---|
| `mount` | – | `mount` | Mount the external RAW drive. |
| `unmount` | – | `unmount` | Unmount the external RAW drive. |
| `toggle mount` | – | `toggle_mount` | Mount when no drive is present, unmount otherwise. |
| `erase` | – | `erase_drive` | Delete every clip on the mounted RAW volume without reformatting. |
| `format [ext4\|exfat\|ntfs]` | text or none | `format_drive` | Reformat the RAW drive and remount it. Defaults to `exfat`. |

## Sensor tools

| Command | Argument | Method | What it does |
|---|---|---|---|
| `set filter <0/1>` | 0/1 | `set_filter` | Enable (`1`) or disable (`0`) the StarlightEye IR-cut filter. IMX585 only; on any other sensor the command returns immediately and changes nothing. The parser lets the argument be omitted, but the handler rejects a bare `set filter`, so always pass `0` or `1`. |

## System

| Command | Argument | Method | What it does |
|---|---|---|---|
| `get` | – | `print_settings` | Print every Redis parameter with its current value. |
| `reboot` | – | `reboot` | Stop any running recording, then reboot the Pi. |
| `shutdown` | – | `safe_shutdown` | Stop any running recording, then halt the Pi. |
| `restart cinemate` | – | `restart_cinemate` | Restart the CineMate process through systemd, without rebooting. |

### CLI commands without a controller method

These are handled by the CLI and other components rather than by `CinePiController`, so there is no method name to bind in `settings.jsonc`:

- `time` — show system and RTC time.
- `set rtc time` — copy system time to the RTC.
- `space` — report remaining space on the mounted drive.
- `restart camera` — restart the libcamera/cinepi-raw pipeline.
- `storage preroll` — run the storage warm-up recording (see below).

## Timed recording shortcuts

Use the timed modes to walk away from the camera while it captures a precisely bounded take. They are parsed by the `rec` handler only — `stop` takes no arguments.

- `rec s <seconds>` stops after the requested duration. Short forms such as `sec`, `secs` and `seconds` also work.
- `rec f <frames>` stops after the requested number of frame slots. Dropped frames still count toward that limit, so the take ends when that many frames should have been recorded, not when that many DNGs were successfully written. You can type `frame` or `frames` instead of `f`.

If recording is not already running, the CLI starts it before arming the timer. An invalid or zero value is ignored so you cannot accidentally stop a clip immediately.

On a dual-sensor rig you can prepend a camera token — `cam0`, `cam1`, or `both` (`dual` is an alias) — to force which sensor(s) capture the take, overriding the [record policy](dual-sensors.md#recording) for that one clip. It combines with the timed modes: `rec cam1`, `rec cam0 s 10`, `rec both f 48`. With a single sensor the token has no effect.

## Storage maintenance commands

`erase` and `format` prepare removable media directly from the CLI. Both require the RAW drive to be mounted; otherwise CineMate logs an error and leaves the media untouched.

- `erase` empties the mounted RAW volume without touching the filesystem structure, so you can clear cards quickly between takes. It is also refused while a take is recording or while buffered frames are still flushing.
- `format [ext4|exfat|ntfs]` reformats the drive with the chosen filesystem (`exfat` by default), remounts it and refreshes the free-space monitor.

## Storage pre-roll warm-up

`storage preroll` triggers the same warm-up clip that CineMate runs automatically on startup or when you mount new storage. During the pre-roll, CineMate temporarily drives the sensor at its maximum FPS, records a short burst, waits for buffers to flush and removes the test clip so the media is primed for the next real take. The manual command stays available even when `system.storage.auto_preroll` is set to `false` in `settings.jsonc`.

See [Storage pre-roll warm-up](storage-preroll.md) for a detailed walkthrough of the workflow and tips on when to run it manually.

## Wiring a command to hardware

Any method in the Method column can be named in a `hardware_controls` block in `settings.jsonc` — buttons, rotary encoders, switches and potentiometers all dispatch to these same methods, so anything you can type you can also bind to a control. Methods that take no argument suit buttons and encoder detents; the `set_*` methods that accept a value suit pots and analog inputs. See [Additional hardware](hardware-controls.md) for the block format and pin wiring, and [settings.jsonc](settings-json.md) for the full settings file.
