# Settings.jsonc file

This file controls how the camera behaves and how your buttons, switches and displays are mapped. It lives in `~/cinemate/settings.jsonc`. You can edit it with any text editor; the settings take effect the next time you start Cinemate.

!!! note ""
    The prebuilt image works out of the box. You do **not** need to edit `settings.jsonc` to start shooting. This page is a reference for when you want to customise hardware controls and behaviour.

The image ships with a stock `settings.jsonc` that already holds working defaults for every section below — button and switch mappings, preview, and audio (for example, a 2-frame audio timecode offset on both microphone paths). Edit it only to change a mapping or tune behaviour.

!!! tip ""
    For easy editing of settings on the preinstalled image file, type `editsettings` anywhere in Raspberry Pi terminal.

The configuration is JSON with `//` and `/* */` comments and trailing commas allowed (JSONC) — the shipped file uses both to annotate the trickier keys in place. Each top‑level key describes a feature area of the system:

| Key | Covers |
|---|---|
| [`system`](#system) | Splash screen, Wi‑Fi hotspot, web API, storage behaviour |
| [`sensors`](#sensors) | Per-sensor hardware: geometry, HDMI output, name spoofing, phase lock, CineMate Log, sensor database |
| [`settings`](#settings) | Frame-rate conform target, flicker-free input, sync tolerances |
| [`arrays`](#arrays) | One block per cycle-able camera parameter: ISO, shutter angle, FPS, white balance |
| [`image_capture`](#image_capture) | Resolution / bit-depth / HDR filters |
| [`audio_capture`](#audio_capture) | Capture gain and timecode offset, per microphone path |
| [`hdmi_display`](#hdmi_display) | Everything the operator sees: HDMI canvas, GUI overlays, preview zoom/source/pip/anamorphic |
| [`hardware_controls`](#hardware_controls) | Direct-GPIO physical inputs, channel-first: buttons, switches, rotary encoders, combined actions |
| [`input_peripherals`](#input_peripherals) | Grove Base HAT analog pots + the Adafruit quad I2C rotary encoder board |
| [`hardware_outputs`](#hardware_outputs) | Direct-GPIO outputs Cinemate drives: REC tally/relay pins, REC sync tone |
| [`output_peripherals`](#output_peripherals) | The optional I2C OLED status screen |

## system

Splash screen, network, and storage behaviour.

```jsonc
"system": {
  "welcome": {
    "show": true,
    "message": "THIS IS A COOL MACHINE",
    "image": null
  },
  "wifi_hotspot": {
    "name": "CinePi",
    "password": "11111111",
    "enabled": true
  },
  "web_api": {
    "enabled": true,
    "token": "",
    "allow_destructive": false,
    "max_commands_per_sec": 20,
    "max_sse_clients": 4,
    "broadcast": { "enabled": true, "port": 8888, "hz": 5, "keys": ["is_recording", "iso"] }
  },
  "storage": {
    "auto_preroll": true
  }
}
```

### welcome

Text or image displayed briefly when Cinemate starts.

`show` – `true` to display the configured startup splash for at least 3 seconds, `false` to skip it entirely. If Plymouth is active during boot, Cinemate waits until the spinner hands off before it shows the welcome message so the screen transition stays clean.<br>
`message` – the splash text.<br>
`image` – path to a bitmap file to show a logo instead of text, e.g. `/home/pi/welcome_image.bmp`. Overrides `message` when set.

### wifi_hotspot

`name` – the Wi‑Fi network name (SSID) broadcast by the Pi when hotspot mode is enabled.<br>
`password` – password for joining the hotspot.<br>
`enabled` – set to `true` to start the hotspot automatically on boot. If set to `false`, Cinemate can still serve its web UI on whatever network the Pi is connected to, as long as `wlan0` or `eth0` already has an IP address when Cinemate starts.

Use the hotspot when you need a direct connection in the field. Disable it during development so the Pi can join your regular Wi‑Fi and reach the internet. If you are connected to the Pi via Ethernet you can keep the hotspot on.

### web_api

Wireless control API for microcontrollers (ESP32/Pico/M5Stack etc.) over the hotspot — same commands as the Cinemate CLI, over HTTP, plus a UDP status broadcast for tally lights and displays. See [Web API](web-api.md) and [Building control units](building-control-units.md).

`enabled` – turns the API off entirely when `false`.<br>
`token` – when set, requests must carry it in `X-Cinemate-Token`. Leave `""` only on a trusted/isolated hotspot.<br>
`allow_destructive` – when `false` (default), blocks `reboot`/`shutdown`/`erase`/`format` over the API. The hotspot password ships as `11111111`, so this defaults closed.<br>
`max_commands_per_sec` – per-client rate limit.<br>
`max_sse_clients` – concurrent `/events` connections.<br>
`broadcast` – the UDP status line: `enabled`, `port`, `hz` (rate), and `keys` (which Redis keys appear in the broadcast).

### storage

`auto_preroll` – controls the short automatic warm-up recording that prepares mounted media before the first real take. Set it to `true` to run the warm-up on startup and when RAW storage mounts. Set it to `false` to skip only the automatic startup and mount-triggered pre-rolls. Manual `storage preroll` CLI runs remain available either way. See [Storage pre-roll](storage-preroll.md).

## sensors

Per-sensor hardware. All per-port settings live inside a `cam0` or `cam1` block so every option for a given camera port is visible in one place. `raw_buffer_count`, `record_policy`, and `database_file` are the global keys.

```jsonc
"sensors": {
  "raw_buffer_count": 0,
  "record_policy": "follow_preview",
  "cam0": {
    "geometry": {
      "rotate_180": false,
      "horizontal_flip": false,
      "vertical_flip": false
    },
    "output": {
      "hdmi_port": 0
    },
    "override_camera_name": true,
    "camera_name": "cinepi",
    "phase_lock": true,
    "tuning_file_override": { "enabled": false, "path": "resources/tuning_files/imx477.json" },
    "log_encode": false
  },
  "cam1": {
    "geometry": {
      "rotate_180": false,
      "horizontal_flip": false,
      "vertical_flip": false
    },
    "output": {
      "hdmi_port": 1
    },
    "override_camera_name": true,
    "camera_name": "cinepi",
    "phase_lock": true,
    "tuning_file_override": { "enabled": false, "path": "resources/tuning_files/imx477.json" },
    "log_encode": false
  },
  "database_file": "resources/sensors.json"
}
```

`raw_buffer_count` – how many frames `cinepi-raw` keeps in RAM as a write-burst absorber. Leave it at `0` (default); the active storage profile picks the right depth automatically.

??? note "raw_buffer_count / CMA buffer tuning"
    The sensor produces frames at a fixed rate but storage write speed is uneven — exFAT can stall during cluster allocation or directory updates. Frames that land during a stall are held in the RAM ring until the disk catches up; no frames are dropped as long as the stall is shorter than the buffer depth. More buffers = more RAM used, but more tolerance for storage hiccups. `0` (default) lets the active storage profile pick the right depth for your sensor, filesystem, and storage type — this is almost always correct. Raise it only if you see single-frame TC holes (`DROP` flashing) and `grep Cma /proc/meminfo` confirms spare CMA headroom (~25 MB per extra buffer at 4K).

### record_policy

Dual-sensor record policy. `"follow_preview"` (default) makes recording follow the HDMI preview: a full-screen or pip-main sensor records alone, side-by-side records both. `"always_both"` forces both sensors to record every take regardless of the preview. A camera token on `rec` (`rec cam0` / `rec cam1` / `rec both`) overrides either policy for one take. No effect with a single sensor. See [Dual sensors › Recording](dual-sensors.md#recording).

### geometry

Controls image orientation for the camera mounted on this port. These settings let you mount cameras in any orientation and still get an upright preview and recording.

`rotate_180` – flip the image upside-down.<br>
`horizontal_flip` – mirror the image left/right.<br>
`vertical_flip` – mirror the image top/bottom.

### output

Maps the camera to an HDMI connector.

`hdmi_port` – `0` for `HDMI-A-1`, `1` for `HDMI-A-2`.

!!! note ""
    This setting chooses which connector `cinepi-raw` uses at runtime. On Raspberry Pi Bookworm with KMS, the boot framebuffer mode still comes from `/boot/firmware/cmdline.txt`, so headless installs should also set a `video=HDMI-A-1:1920x1080M@60D` or `video=HDMI-A-2:1920x1080M@60D` override there.

### camera name

`override_camera_name` – when `true`, the value of `camera_name` is passed to `cinepi-raw` as `--unique-camera-model` and written into the `UniqueCameraModel` DNG tag of every recorded frame. When `false`, `cinepi-raw` uses its built-in default.<br>
`camera_name` – the string to embed when `override_camera_name` is `true`. The stock file ships `true` with `"cinepi"` — the same tag `cinepi-raw` uses on its own — so changing the embedded name is a one-line edit.

??? note "Why Blackmagic Pocket Cinema Camera 4K"
    DaVinci Resolve uses the `UniqueCameraModel` DNG tag to identify the camera and select the matching decode pipeline. When this tag matches a known Blackmagic camera, Resolve unlocks the full Camera RAW tab — including the ISO slider, colour science selection (Gen 4 / Gen 5), and the corresponding tone curve and noise reduction presets. With an unknown or missing camera model the RAW tab is limited and ISO behaves as a simple exposure offset rather than selecting a proper decode curve.

    Setting `camera_name` to `"Blackmagic Pocket Cinema Camera 4K"` is therefore not cosmetic — it is what makes Resolve treat the footage as genuine BRAW-adjacent DNG and apply the correct ISO-aware decode.

    **Caveat once [CineMate Log](cinemate-log.md) is in use:** the Blackmagic spoof layers BMD colour science and its own tone curve on top of data that CineMate Log has already linearised via the DNG `LinearizationTable`. Keep `camera_name` at `"cinepi"` (the stock value) on any camera recording log — spoofing and log-encoding the same clip confound each other in the grade. The spoof is still fine for a camera you are recording in plain linear DNGs.

### phase_lock

`phase_lock` – `true` (default) keeps audio and video aligned over long takes by locking the recorded frame cadence to the Pi clock. Leave it on.

!!! note "phase_lock internals and multi-camera genlock"

    The phase lock is a per-frame servo: it measures the accumulated frame phase against the nominal FPS (against the Pi wall clock — `FrameWallClock`, the same clock the audio is captured against) and continuously trims `FrameDurationLimits`, dithering the integer line-blanking so the *average* recorded cadence is exact. The result is that the video tracks the Pi clock, so audio and video do not drift apart over long takes (the residual is a bounded sub-frame offset, not an accumulating drift). It pre-converges during preview, so a clip is locked from the first frame.

    Cinemate writes this per-camera flag to the shared `fps_phase_lock` runtime key, which `cinepi-raw` reads (it is off by default in `cinepi-raw` itself when run standalone). The loop is VBLANK-only and holds the recorded cadence on the nominal FPS directly, so no per-sensor FPS-correction table is needed.

    **Multi-camera genlock.** `phase_lock` can stay `true` on a multi-camera `--sync` (beam-splitter / genlock) rig. `cinepi-raw` infers its role from `--sync`: the master (`--sync server`) runs the phase lock and disciplines the pair to the Pi clock, while the `--sync client` automatically suppresses its own phase lock and lets libcamera's `rpi.sync` hold the relative camera-to-camera (A→B) alignment. One setting works for single and dual — no per-camera differentiation. See [Dual sensors](dual-sensors.md).

### tuning_file_override

`enabled` – use `path` instead of the libcamera tuning file Cinemate would otherwise pick for the detected sensor.<br>
`path` – tuning file to use when `enabled` is `true`.

### log_encode

`log_encode` – this camera's [CineMate Log](cinemate-log.md) setting: `false` (default, off), `true` (on, using the live sensor mode's default target), or `10` / `12` to force that target explicitly when the live mode supports it. Only imx585 and imx283 support it; the setting is ignored on every other sensor. See [CineMate Log](cinemate-log.md) for the full picture, including the `set log` CLI command and the per-camera `LOG10`/`LOG12` badge on the Simple GUI.

### database_file

Points Cinemate at the sensor metadata database. It lists the **full** set of modes each sensor supports — every mode stays available to the system — alongside known packing modes and documentation metadata. The [image_capture](#image_capture) filter selects which of those modes appear in the UI.

`database_file` – JSON file containing compatible sensor metadata. The default file is `resources/sensors.json`.

## settings

Frame-rate conform target, flicker-free input, and sync tolerances.

```jsonc
"settings": {
  "conform_frame_rate": 25,
  "light_hz": [50, 60],
  "sync_tolerances": {
    "live_sync_warning_frames": 5,
    "live_sync_startup_guard_frames": 10,
    "final_sync_analysis_frames": 1,
    "tc_drop_jitter_frames": 1
  }
}
```

`conform_frame_rate` – frame rate intended for project conforming in post. This setting is not really used by CineMate except for calculating the recording timecode tracker in redis but might be used in future updates.<br>
`light_hz` – list of mains frequencies used to calculate flicker‑free shutter angles. These are added to the shutter angle steps (see [arrays](#arrays)) and also dynamically calculated upon each fps change. This way, there is always a flicker free shutter angle value close by, when toggling through shutter angles, either via the cli or using buttons/pots/rotary encoder.

`sync_tolerances`:

<br>`live_sync_warning_frames` – frame-slot tolerance for the live magenta `SYNC` warning during a take.
<br>`live_sync_startup_guard_frames` – grace period, in frames, right after recording starts before the live warning can latch.
<br>`final_sync_analysis_frames` – frame tolerance for the end-of-take DNG count analysis after buffered frames have flushed. Kept stricter than the live warning by default.
<br>`tc_drop_jitter_frames` – tolerance for late-but-present frames (TC holes) before they count as a sync concern.

## arrays

One block per cycle-able camera parameter: ISO, shutter angle, frame rate, white balance, and the four ClearHDR live knobs. `steps` is the preset table Cinemate steps through; `free` switches to a continuous runtime range instead — for potentiometers, rotary encoders, CLI inc/dec commands, and the web GUI. `free_increment` sets the step size free stepping counts in (bounds are fixed per parameter; only the increment is configurable).

| parameter | free range | `free_increment` default |
|---|---|---|
| `iso` | 100–3200 | 100 |
| `shutter_a` | 1–360° | 1° |
| `fps` | 1–`fps_max` | 1 |
| `wb` | 2800–6500 K | 100 K |
| `hdr_threshold_low` / `hdr_threshold_high` | 0–4095 | 16 |
| `hdr_blend` | 0–8 | 1 |
| `hdr_gain_adder` | 0–5 | 1 |

`shutter_a` has one more field, `sync_increment` (default 0.1°): the granularity used only while [shutter-angle sync mode](cli-commands.md) (`set shutter a sync`) is on, tracking exposure time continuously across fps changes. It's independent of `free_increment` — the two used to share a single hardcoded 0.1° value, so toggling sync mode and toggling free stepping looked identical; they're now separate knobs for two different jobs (sync mode's continuous exposure tracking vs. free stepping's manual pot/encoder control).

```jsonc
"arrays": {
  "iso": {
    "steps": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],
    "free": false,
    "free_increment": 100
  },
  "shutter_a": {
    "steps": [1, 45, 90, 135, 172.8, 180, 225, 270, 315, 346.6, 360],
    "free": false,
    "free_increment": 1,
    "sync_increment": 0.1
  },
  "fps": {
    "steps": [1, 2, 4, 8, 12, 16, 18, 24, 25, 33, 40, 50],
    "free": true,
    "free_increment": 1
  },
  "wb": {
    "steps": [3200, 4400, 5600],
    "free": false,
    "free_increment": 100
  },
  "hdr_threshold_low": {
    "steps": [0, 512, 1024, 1536, 2048, 2560, 3072, 3584, 4095],
    "free": false,
    "free_increment": 16
  },
  "hdr_threshold_high": {
    "steps": [0, 512, 1024, 1536, 2048, 2560, 3072, 3584, 4095],
    "free": false,
    "free_increment": 16
  },
  "hdr_blend": {
    "steps": [0, 1, 2, 3, 4, 5, 6, 7, 8],
    "free": false,
    "free_increment": 1
  },
  "hdr_gain_adder": {
    "steps": [0, 1, 2, 3, 4, 5],
    "free": false,
    "free_increment": 1
  }
}
```

??? note "How to think about ISO"
    At capture, ISO is real analog gain on the sensor — it changes the raw pixel values written to disk. Setting it too high introduces noise that is baked in and cannot be removed later.

    Once your DNGs are in Resolve's Camera RAW tab, the pixel values are fixed. ISO there is a decode-time parameter: in Gen 4 color science it selects a different log curve that shifts contrast as well as brightness; in Gen 5 it acts as a linear gain equivalent to the Exposure slider. Either way, correcting a wrong ISO in Resolve costs no additional quality — provided the sensor data was not catastrophically over- or underexposed at capture.

    References: [BRAW decode](https://blackmagiccameraapk.pro/blackmagic-raw-explained/) · [Gen 4 vs Gen 5](https://forum.blackmagicdesign.com/viewtopic.php?f=2&t=130645&start=50) · [ISO vs Exposure](https://forum.blackmagicdesign.com/viewtopic.php?f=2&t=123096) · [Resolve Camera RAW manual](https://www.steakunderwater.com/VFXPedia/__man/Resolve18-6/DaVinciResolve18_Manual_files/part202.htm)

## image_capture

Which resolution/bit-depth/HDR modes are practical to expose in the UI when cycling resolutions. This is a filter, not the mode list itself: every mode a sensor supports lives in the sensor database (`resources/sensors.json`, see [sensors.database_file](#database_file) above), and `image_capture` selects the useful subset to show. Hidden modes stay technically available to the system.

```jsonc
"image_capture": {
  "k_steps": [1.5, 2, 3, 4],
  "bit_depths": [10, 12, 16],
  "hdr": {
    "sdr": true,
    "imx585_clear_hdr": true,
    "threshold_low": 0,
    "threshold_high": 0,
    "blend": 0,
    "gain_adder": 1
  },
  "custom_modes": {}
}
```

`k_steps` – K‑style categories for allowed widths. Modes are grouped to the nearest half‑K. Example: 1332×990 counts as **1.5 K**.<br>
`bit_depths` – list of bit depths to expose. `16` covers the imx585 ClearHDR 16-bit modes (see [ClearHDR](clear-hdr.md)).<br>
`hdr.sdr` / `hdr.imx585_clear_hdr` – whitelist of the ClearHDR flag. Both `true` (default) exposes the plain and the imx585 ClearHDR modes; set `imx585_clear_hdr` to `false` to hide the HDR modes, or `sdr` to `false` to show only them. Cinemate detects the HDR modes by probing `cinepi-raw --list-cameras --hdr sensor` alongside the plain list. imx585 has HDR modes at **both** 12-bit and 16-bit, and they are labelled `HDR` (simple GUI) / `:HDR` (web GUI). The legacy `[false, true]` list form still works.<br>
`hdr.threshold_low` / `hdr.threshold_high` / `hdr.blend` / `hdr.gain_adder` – startup values for the four ClearHDR live knobs, seeded into Redis at launch. Adjust them afterwards without a restart via `set hdr threshold low/high`, `set hdr blend`, `set hdr gain adder`, or a pot/quad-rotary channel. See [ClearHDR](clear-hdr.md#live-knobs) for what each one does.<br>
`custom_modes` – per-camera-name list of mode overrides and additions, keyed by sensor name. `fps_max` (from `cinepi-raw --list-cameras`) is an electrical property of the sensor — it says nothing about what your storage and CPU can actually sustain at that mode, and only trial recording can find that ceiling. An entry whose `width`/`height`/`bit_depth`/`hdr` matches an already-detected mode **corrects that mode's `fps_max` in place**; a non-matching entry **adds** a brand-new mode instead. Settings editor → *Per-mode fps ceilings* lists every sensor-detected mode with the override pre-filled if one exists — leave a field blank (or equal to the detected value) to record no override, or lower it to whatever your storage profile actually sustains. Raising it above the detected value is allowed but logged as a warning. `choose_resolution()` needs no separate logic for this: it always selects on `fps_max`, which is now the effective (overridden or detected) value.

!!! note "Design: full capability vs practical exposure"

    `resources/sensors.json` lists **every** mode each sensor supports, so all of them are technically available to the system. `image_capture` then exposes only the **practical** subset in the UI. `k_steps`/`bit_depths` are global across all sensors — the stock `[1.5, 2, 3, 4]` covers every sensor's everyday modes. For the IMX283 that keeps the ≥25 fps 2.7K and 4K modes (the 3 and 4 steps) and hides the 5K modes (~18–21 fps); those stay in `sensors.json` and reappear if you add `5.5`.

Cinemate also always runs **dynamic resolution**: if you select a mode and then raise FPS above what that mode's own sensor-reported maximum (the same number `cinepi-raw --list-cameras` reports) can sustain, Cinemate automatically switches to the highest-resolution mode that can. FPS returns to your selected mode once you dial back down. There is no setting for this — it always uses the sensor's own reported limits, never a separate measured table.

## audio_capture

Audio capture options shared by idle monitoring and recorded WAV input level. The stock file applies a 2-frame timecode offset on both paths.

```jsonc
"audio_capture": {
  "24bit": {
    "capture_gain_db": 6.0,
    "timecode_offset_frames": 2
  },
  "16bit": {
    "capture_gain_db": 6.0,
    "timecode_offset_frames": 2
  }
}
```

Settings are split by the bit depth negotiated with the connected microphone. `24bit` applies when the mic supports 24-bit stereo capture (`mic_24bit` ALSA alias); `16bit` applies when only 16-bit mono is available (`mic_16bit` alias).

`capture_gain_db` – target ALSA capture gain in decibels applied when the microphone is detected. `0.0` means unity gain. Positive values boost the capture level, negative values attenuate it. For 16-bit mics this value is also passed into `cinepi-raw` via Redis so that a post-take software gain can be applied to the WAV if the hardware exposes no writable ALSA control.

`timecode_offset_frames` – frame offset applied to the WAV timecode metadata after each take. A **positive** value moves the WAV timecode later (use when audio arrives *early* relative to video); a negative value moves it earlier. Only the embedded timecode is shifted — the PCM is never moved. `24bit.timecode_offset_frames` is used whenever the capture helper is active (both 24-bit and 16-bit mics going through the helper). `16bit.timecode_offset_frames` applies to 16-bit mics specifically, overriding the 24-bit value for that path.

Some USB microphones expose a writable ALSA capture control and some do not. When the mic supports it, Cinemate applies `capture_gain_db` via `amixer` when the microphone is detected. If the device exposes no compatible control, the setting is silently skipped and the log will note that the mic likely has fixed hardware gain.

## hdmi_display

Everything the operator sees: the HDMI canvas, GUI overlays, and preview zoom/source/pip/anamorphic.

```jsonc
"hdmi_display": {
  "width": 1920,
  "height": 1080,
  "mirror_to_both_ports": false,
  "overlays": {
    "buffer_vu_meter": false,
    "vu_meter_hatch_lines": true
  },
  "preview": {
    "default_zoom": 1.0,
    "zoom_steps": [1.0, 1.5, 2.0],
    "default_hdmi_source": "both",
    "pip": {
      "scale": 0.28,
      "corner": "lower_right",
      "margin": 0.03
    },
    "anamorphic": {
      "default_factor": 1,
      "steps": [1, 1.33, 2.0]
    }
  }
}
```

`width` / `height` – the GUI canvas size Cinemate targets. If the active framebuffer is smaller, Cinemate falls back to the active framebuffer size instead of drawing a clipped layout into a smaller mode.<br>
`mirror_to_both_ports` – single-sensor only: mirror the one sensor's preview (with GUI) onto both HDMI connectors via cinepi-raw's `--same-hdmi`. The dual-sensor compositor already owns both-feed layouts, so this has no effect with two sensors attached.

### overlays

`buffer_vu_meter` – show or hide the vertical RAM-buffer meter on the HDMI GUI.<br>
`vu_meter_hatch_lines` – draw hatch lines inside the buffer meter fill.

### preview

`default_zoom` – magnification factor used at startup.<br>
`zoom_steps` – list of zoom factors you can cycle through with `set zoom`.<br>
`default_hdmi_source` – dual-sensor HDMI preview source at startup: `both`, `cam0`, `cam1`, `pip_cam0`, or `pip_cam1`. Switch it live with [`set preview`](cli-commands.md). No effect with a single sensor.<br>
`pip` – picture-in-picture inset geometry for the `pip_cam0` / `pip_cam1` preview modes. `scale` – inset size as a fraction of the main pane (default `0.28`). `corner` – `lower_right`, `lower_left`, `upper_right`, or `upper_left` (default `lower_right`). `margin` – gap from the edge as a fraction of the pane (default `0.03`). See [Dual sensors](dual-sensors.md#picture-in-picture).<br>
`anamorphic` – stretching the preview for anamorphic lenses. `default_factor` – factor loaded when Cinemate starts. `steps` – selectable squeeze factors; values above `1.0` widen the image.

## hardware_controls

Direct-GPIO physical inputs, channel-first: which pin it's on, then what it does.

### buttons

Defines GPIO push buttons. Each entry describes one button and the actions it triggers.

```jsonc
{
  "pin": 5,
  "pull_up": true,
  "debounce_time": 0.1,
  "press_action": {"method": "rec"}
}
```

`pin` – BCM pin number the button is connected to.<br>`pull_up` – set `true` if the pin idles high (internal pull‑up). Use `false` for pull‑down wiring.<br>`debounce_time` – ignore additional presses within this time window (seconds).<br>`press_action`, `single_click_action`, `double_click_action`, `triple_click_action`, `hold_action` – actions to perform for each type of interaction. Actions call Cinemate CLI commands with optional `args`.

!!! info ""

    Some push-buttons are wired closed = logic 1 and open = 0. At start-up, CineMate automatically detects buttons in state `true` and reverses them. This way the user can use any type of push buttons, both 1-0-1 and 0-1-0 types.

### two_way_switches

Latching on/off switches. Cinemate triggers an action whenever the state changes.

```jsonc
{
  "pin": 27,
  "state_on_action":  {"method": "set_all_lock", "args": [1]},
  "state_off_action": {"method": "set_all_lock", "args": [0]}
}
```

### three_way_switches

Three-position switches made from three GPIO inputs. Cinemate checks which pin is active and then runs the matching action.

```jsonc
{
  "pins": [5, 6, 13],
  "state_0_action": {"method": "set_fps", "args": [24]},
  "state_1_action": {"method": "set_fps", "args": [25]},
  "state_2_action": {"method": "set_fps", "args": [50]}
}
```

`pins` – the three GPIO inputs that represent the switch positions.
<br>`state_0_action`, `state_1_action`, `state_2_action` – commands to run for each detected position.

If none of the three inputs is active, the switch is treated as being in an undefined position and no action is run.

### rotary_encoders

Rotary encoders used for fine adjustment of settings. These can be wired straight to the GPIO pins of the Pi. The optional `button_pin` uses the same action grammar as `buttons`.

```jsonc
{
  "enabled": true,
  "clk_pin": 9,
  "dt_pin": 11,
  "button_pin": 10,
  "pull_up": true,
  "debounce_time": 0.05,
  "button_actions": {
    "press_action": {"method": "set_iso_lock"},
    "hold_action": "None"
  },
  "encoder_actions": {
    "rotate_clockwise":        {"method": "inc_iso"},
    "rotate_counterclockwise": {"method": "dec_iso"}
  }
}
```

<br>`enabled` – optional per-encoder switch; set `false` to keep an example in the file without claiming pins at startup. The stock file ships one disabled example.
<br>`clk_pin` and `dt_pin` – the two pins of the encoder.
<br>`button_pin` – optional BCM pin for the encoder push button.
<br>`button_actions` – optional press/click/hold actions for the encoder push button.
<br>`encoder_actions` – commands to run when turning the dial.

### combined_actions

Combined actions let one button act as a modifier for another button.

```jsonc
"combined_actions": [
  {
    "hold_button_pin": 10,
    "action_button_pin": 26,
    "action_type": "press",
    "action": {"method": "set_pwm_mode"}
  }
]
```

`hold_button_pin` – button that must already be held.
<br>`action_button_pin` – second button that triggers the combined action.
<br>`action_type` – either `press` or `release`.
<br>`action` – Cinemate command to run when the hold/action combination matches.

Combined actions only fire while the hold button is still held down. If the modifier button is not active, the normal per-button actions continue to run.

## input_peripherals

Grove Base HAT analog pots and the Adafruit quad I2C rotary encoder board — separate from [hardware_controls](#hardware_controls) because these are their own peripheral boards, not pins wired straight to the Pi's GPIO header.

### pots

Maps Grove Base HAT ADC channels to analogue dials (potentiometers), channel-first: which channel, then which [array](#arrays) it drives.

```jsonc
"pots": [
  { "channel": 0, "setting": "iso" },
  { "channel": 2, "setting": "shutter_a" },
  { "channel": 4, "setting": "fps" }
]
```

`channel` – the Grove Base HAT ADC channel the pot is wired to.<br>
`setting` – which entry in [`arrays`](#arrays) the pot drives (`iso`, `shutter_a`, `fps`, `wb`, or an HDR knob name like `hdr_threshold_low`).

!!! info ""

    Only list channels actually connected to potentiometers — noise from unused connectors might trigger false readings.

### quad_rotary_controller

Support for the Adafruit Neopixel Quad I2C rotary encoder breakout. Each entry maps one of the four dials to an [array](#arrays) and defines the push button actions similar to `buttons`. The stock settings ship it enabled — safe with no board attached, because the controller is hot-plugged and simply retries — set `enabled` to `false` to turn it off. The stock mapping:

```jsonc
"quad_rotary_controller": {
  "enabled": true,
  "encoders": {
    "0": {"setting_name": "iso", "button": {"press_action": {"method": "set_zoom"}, "hold_action": {"method": "safe_shutdown"}}},
    "1": {"setting_name": "shutter_a", "button": {"press_action": {"method": "set_shutter_a_sync_mode"}}},
    "2": {"setting_name": "fps", "button": {"press_action": {"method": "set_fps_double"}}},
    "3": {
      "setting_name": "wb",
      "button": {
        "press_action": "None",
        "single_click_action": {"method": "set_resolution"},
        "double_click_action": {"method": "restart_cinemate"},
        "triple_click_action": {"method": "reboot"},
        "hold_action": {"method": "toggle_mount"}
      }
    }
  }
}
```

`enabled` – turn the quad rotary controller on or off.<br>`encoders` – mapping of each dial (channel `"0"`–`"3"`) to a `setting_name` from [`arrays`](#arrays) and button actions. An encoder with no `setting_name` is valid too — its button can still drive its own actions without cycling a parameter.

## hardware_outputs

Direct-GPIO outputs Cinemate drives: the REC tally/relay pin(s) and the REC sync tone.

```jsonc
"hardware_outputs": {
  "pwm_pin": 19,
  "rec_out_pin": [6, 21],
  "rec_tone": {
    "pin": [18],
    "frequency_hz": 1000,
    "duty_cycle": 50,
    "relay_drop_frames": false
  }
}
```

`pwm_pin` – outputs a strobe for shutter sync or external devices.<br>
`rec_out_pin` – list of pins pulled high while recording (useful for tally LEDs).

`rec_tone`:

<br>`pin` – optional tone output pin(s) used as recording sync tone. You can pass a single pin or a list of pins. GPIO `18` and `19` use **hardware PWM** (preferred for stable tone generation). Any other pin uses **software PWM** fallback. The tone starts as soon as recording is requested (`is_recording = 1`), even before REC-light write confirmation, stops once writing stops (`is_writing = 0`), and is muted during storage pre-roll. If `pin` is unset or an empty list, Cinemate falls back to `pwm_pin` for backward compatibility.
<br>`frequency_hz` – tone frequency in hertz.
<br>`duty_cycle` – PWM duty cycle percentage (`0–100`).
<br>`relay_drop_frames` – when `true`, each live drop-frame pulse (`drop_frame_relay = 1`) briefly mutes REC tone output for about one frame, then resumes automatically.

## output_peripherals

The optional I2C OLED status screen — separate from [hardware_outputs](#hardware_outputs) because it's its own I2C peripheral board, not a pin wired straight to the Pi's GPIO header. This can be useful for presenting extra information apart from the HDMI/web display.

```jsonc
"output_peripherals": {
  "oled": {
    "enabled": true,
    "width": 128,
    "height": 64,
    "font_size": 30,
    "values": ["write_speed_to_drive"]
  }
}
```

`enabled` – turn the OLED display on or off.<br>
`width` / `height` – pixel dimensions of your screen.<br>
`font_size` – size of the displayed text.<br>
`values` – list of Redis keys or pseudo‑keys to show (for example `cpu_temp`).

Available keys come from `src/module/i2c/i2c_oled.py`. Here are some examples:

`iso`, `fps` – basic camera settings.<br>
`shutter_a` – shown as `SHUTTER` with a `°` suffix.<br>
`wb_user` – shown as `WB` with a trailing `K`.<br>
`space_left` – displayed as `SPACE` in gigabytes.<br>
`write_speed_to_drive` – write speed in MB/s.<br>
`resolution` – prints `width×height@bit_depth` on the first line.<br>
`is_recording` – draws a bullet `●` when recording.<br>
`cpu_load`, `cpu_temp`, `memory_usage` – Pi system statistics.

Other keys will display their name in uppercase and the raw value from Redis.

---
