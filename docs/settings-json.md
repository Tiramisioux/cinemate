# Settings file

This file controls how the camera behaves and how your buttons, switches and displays are mapped. It lives in `~/cinemate/src/settings.json`. You can edit it with any text editor; the settings take effect the next time you start Cinemate.

!!! tip ""
    For easy editing of settings on the preinstalled image file, type `editsettings` anywhere in Raspberry Pi terminal.

The configuration is structured as JSON. Each top‑level key describes a feature area of the system. Below is a tour of every section and what the options do.

## welcome message

Text or image displayed briefly when Cinemate starts.

```json
"show_welcome_message": true,
"welcome_image": null,
"welcome_message": "THIS IS A COOL MACHINE"
```

Set `show_welcome_message` to `true` to display the configured startup splash for at least 3 seconds. Set it to `false` to skip the startup message entirely. If the key is missing, Cinemate defaults to showing the startup message. Older installs that still use `show_startup_message` continue to work as a fallback.

If Plymouth is active during boot, Cinemate waits until the spinner hands off before it shows the welcome message so the screen transition stays clean.
Set `welcome_image` to the path of a bitmap file to show a logo instead of text. 

Example path: `/home/pi/welcome_image.bmp`. 

If `welcome_image` is set, it overrides the text message.

## system

```json
"system": {
  "wifi_hotspot": {
    "name": "CinePi",
    "password": "11111111",
    "enabled": false
  }
}
```

`name` – the Wi‑Fi network name (SSID) broadcast by the Pi when hotspot mode is enabled.
`password` – password for joining the hotspot.
`enabled` – set to `true` to start the hotspot automatically on boot. If set to `false`, Cinemate can still serve its web UI on whatever network the Pi is connected to, as long as `wlan0` or `eth0` already has an IP address when Cinemate starts.

Use the hotspot when you need a direct connection in the field. Disable it during development so the Pi can join your regular Wi‑Fi and reach the internet. If you are connected to the Pi via Ethernet you can keep the hotspot on.

## geometry

Controls image orientation for each camera port (`cam0`, `cam1`, etc.). These settings let you mount cameras in any orientation and still get an upright preview and recording. Example:

```json
"geometry": {
  "cam0": { "rotate_180": false, "horizontal_flip": false, "vertical_flip": false },
  "cam1": { "rotate_180": false, "horizontal_flip": false, "vertical_flip": false }
}
```

`rotate_180` – flip the image upside‑down.<br>`horizontal_flip` – mirror the image left/right.<br>`vertical_flip` – mirror the image top/bottom.


## output

Maps each camera to an HDMI connector. Use `-1` for automatic selection.

```json
"output": {
  "cam0": { "hdmi_port": 0 },
  "cam1": { "hdmi_port": 1 }
}
```

Use HDMI port `0` for `HDMI-A-1` and HDMI port `1` for `HDMI-A-2`.

!!! note ""
    This setting chooses which connector `cinepi-raw` uses at runtime. On Raspberry Pi Bookworm with KMS, the boot framebuffer mode still comes from `/boot/firmware/cmdline.txt`, so headless installs should also set a `video=HDMI-A-1:1920x1080M@60D` or `video=HDMI-A-2:1920x1080M@60D` override there.

## hdmi_gui

Controls optional HDMI GUI overlays.

```json
"hdmi_gui": {
  "buffer_vu_meter": false,
  "vu_meter_hatch_lines": true
}
```

`buffer_vu_meter` – show or hide the vertical RAM-buffer meter on the HDMI GUI.
<br>`vu_meter_hatch_lines` – draw hatch lines inside the buffer meter fill.

## hdmi_display

Sets the preferred HDMI GUI canvas size.

```json
"hdmi_display": {
  "width": 1920,
  "height": 1080
}
```

Use this to tell Cinemate what size GUI canvas you want to target. If the active framebuffer is smaller, Cinemate now falls back to the active framebuffer size instead of drawing a clipped `1920x1080` layout into a smaller mode.

## preview

Adjusts zoom levels for the HDMI/browser preview.

```json
"preview": {
  "default_zoom": 1.0,
  "zoom_steps": [1.0, 1.5, 2.0]
}
```

`default_zoom` – magnification factor used at startup.<br>`zoom_steps` – list of zoom factors you can cycle through with the `set_zoom_step` command.

## audio

Audio capture options shared by idle monitoring, recorded WAV input level, and ADC clock correction.

```json
"audio": {
  "capture_gain_db": 0.0,
  "plain_arecord_timecode_offset_frames": 2,
  "timecode_offset_frames": 2,
  "clock_correction": {
    "enabled": false,
    "database": "resources/audio_clock_correction.json"
  }
}
```

`capture_gain_db` – target ALSA capture gain in decibels for the detected microphone input. `0.0` means unity gain. Positive values boost the capture level, negative values attenuate it.

`plain_arecord_timecode_offset_frames` – frame offset passed to `cinepi-raw` for the 16-bit plain `arecord` fallback WAV metadata path. `2` corrects the current 16-bit USB mic calibration, `0` disables the correction, and negative values are allowed for future calibration. This changes only WAV timecode metadata; recorded PCM is not shifted.

`timecode_offset_frames` – the same kind of frame offset for the **24-bit USB capture path** (the default for most USB mics, including the clock-correction path). Use it to nudge audio that lands a fixed number of frames early or late relative to video. A **positive** value moves the WAV timecode later (use it when the sound is *early*); a negative value moves it earlier. `2` is the current calibration, `0` disables it. Like the 16-bit knob, this changes only WAV timecode metadata — the PCM is never shifted — and it is independent of (and stacks with) clock correction. Passed to `cinepi-raw` as `--audio-timecode-offset-frames`.

Use this when the Pi is hearing the mic too quietly or too hot and you want the idle VU, recording VU, and recorded WAV to move together. Cinemate mirrors this value into the Redis key `audio_capture_gain_db` at startup so future runtime controls can target the same setting.

Some USB microphones expose a writable capture control and some do not. When the mic does support it, Cinemate applies this gain when the microphone is detected. If the device exposes no compatible capture control, the setting stays harmlessly ignored and the log will tell you that the mic likely has fixed gain.

### ADC clock correction

Some USB audio devices run their internal ADC clock slightly off the nominal 48 000 Hz sample rate. A mic that captures 47 946 Hz instead of 48 000 Hz will produce a WAV that drifts ahead of video by roughly 10 frames over a 6-minute take, with no xruns and no other symptoms.

`clock_correction.enabled` – set to `true` to activate correction. Correction is only applied when this is `true` **and** the connected mic matches an entry in the database file. Default is `false` — no resampling occurs.

`clock_correction.database` – path to the device database file, relative to the Cinemate repo root. Default is `resources/audio_clock_correction.json`.

When enabled, Cinemate queries `arecord -l` at each `cinepi-raw` launch and passes the matched ppm value to `cinepi-raw` as `--audio-clock-ppm`. After each take, `cinepi-raw` applies the correction within the single post-take `ffmpeg` metadata pass — correcting the duration without altering the BWF timecode anchor and without writing an intermediate WAV. The 16-bit plain-arecord path is never resampled regardless of this setting.

To add a new microphone, see the instructions at the top of `resources/audio_clock_correction.json`. To disable correction globally without editing the database, set `enabled` to `false` here.

## anamorphic_preview

For stretching the preview when using anamorphic lenses.

```json
"anamorphic_preview": {
  "default_anamorphic_factor": 1,
  "anamorphic_steps": [1, 1.33, 2.0]
}
```

`default_anamorphic_factor` – factor loaded when Cinemate starts.
<br>`anamorphic_steps` – selectable squeeze factors; values above `1.0` widen the image.

## gpio_output

Defines pins used for visual feedback or sync signals.

```json
"gpio_output": {
  "pwm_pin": 19,
  "rec_out_pin": [6, 21],
  "rec_tone_pin": [18],
  "rec_tone_frequency_hz": 1000,
  "rec_tone_duty_cycle": 50
}
```

* `pwm_pin` – outputs a strobe for shutter sync or external devices.

* `rec_out_pin` – list of pins pulled high while recording (useful for tally LEDs).

* `rec_tone_pin` – optional tone output pin(s) used as recording sync tone. You can pass a single pin or a list of pins.
  GPIO `18` and `19` use **hardware PWM** (preferred for stable tone generation). Any other pin uses **software PWM** fallback. The tone starts as soon as recording is requested (`is_recording = 1`), even before REC-light write confirmation, stops once writing stops (`is_writing = 0`), and is muted during storage pre-roll. If `rec_tone_pin` is unset or an empty list, Cinemate falls back to `pwm_pin` for backward compatibility.

* `rec_tone_frequency_hz` – tone frequency in hertz.

* `rec_tone_duty_cycle` – PWM duty cycle percentage (`0–100`).
* `rec_tone_relay_drop_frames` – when `true`, each live drop-frame pulse (`drop_frame_relay = 1`) briefly mutes REC tone output for about one frame, then resumes automatically.

## settings

General options for runtime behaviour.

```json
"settings": {
  "auto_storage_preroll": true,
  "light_hz": [50, 60],
  "conform_frame_rate": 24,
  "live_sync_warning_tolerance_frames": 2,
  "final_sync_analysis_tolerance_frames": 1
}
```

`auto_storage_preroll` – controls the short automatic warm-up recording that prepares mounted media before the first real take. Set it to `true` to run the warm-up on startup and when RAW storage mounts. Set it to `false` to skip only the automatic startup and mount-triggered pre-rolls. Manual `storage preroll` CLI runs remain available either way.
<br>
`light_hz` – list of mains frequencies used to calculate flicker‑free shutter angles. These are added to the shutter angle array and also dynamically calculated upon each fps change. This way, there is always a flicker free shutter angle value close by, when toggling through shutter angles, either via the cli or using buttons/pots/rotary encoder.
<br>`conform_frame_rate` – frame rate intendend for project conforming in post. This setting is not really used by CineMate except for calculating the recording timecode tracker in redis but might be used in future updates.
<br>`live_sync_warning_tolerance_frames` – frame-slot tolerance for the live magenta `SYNC` warning during a take. The default is `2`, so brief +/- 2 frame live drift is allowed before the warning latches.
<br>`final_sync_analysis_tolerance_frames` – frame tolerance for the end-of-take DNG count analysis after buffered frames have flushed. The default is `1`, keeping the final result stricter than the live warning.

## arrays

Preset lists for exposure and frame‑rate settings. Cinemate will step through these values unless you enable free mode, either in the settings file or during runtime.

```json
"arrays": {
  "iso_steps": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],
  "shutter_a_steps": [1, 45, 90, 135, 172.8, 180, 225, 270, 315, 346.6, 360],
  "fps_steps": [1, 2, 4, 8, 12, 16, 18, 24, 25, 33, 40, 50],
  "wb_steps": [3200, 4400, 5600]
}
```

!!! note "How to think about ISO"
    At capture, ISO is real analog gain on the sensor — it changes the raw pixel values written to disk. Setting it too high introduces noise that is baked in and cannot be removed later.

    Once your DNGs are in Resolve's Camera RAW tab, the pixel values are fixed. ISO there is a decode-time parameter: in Gen 4 color science it selects a different log curve that shifts contrast as well as brightness; in Gen 5 it acts as a linear gain equivalent to the Exposure slider. Either way, correcting a wrong ISO in Resolve costs no additional quality — provided the sensor data was not catastrophically over- or underexposed at capture.

    References: [BRAW decode](https://blackmagiccameraapk.pro/blackmagic-raw-explained/) · [Gen 4 vs Gen 5](https://forum.blackmagicdesign.com/viewtopic.php?f=2&t=130645&start=50) · [ISO vs Exposure](https://forum.blackmagicdesign.com/viewtopic.php?f=2&t=123096) · [Resolve Camera RAW manual](https://www.steakunderwater.com/VFXPedia/__man/Resolve18-6/DaVinciResolve18_Manual_files/part202.htm)

## analog_controls

Maps Grove Base HAT ADC channels to analogue dials (potentiometers). Use `null` to disable a dial.

```json
"analog_controls": {
  "iso_pot": 0,
  "shutter_a_pot": 2,
  "fps_pot": 4,
  "wb_pot": "None"
}
```

!!! info ""

    When using a Grove Base Hat with potentiometers, make sure to define only channels actually connected to potentiometers, since noise from unused connectors might trigger false readings.

## free_mode

When enabled, ignores the preset arrays and exposes the expanded runtime step tables used by potentiometers, rotary encoders, CLI commands, and the web GUI. White balance free mode uses 100 K steps from 2800 K through 6500 K.

```json
"free_mode": {
  "iso_free": false,
  "shutter_a_free": false,
  "fps_free": true,
  "wb_free": false
}
```

## resolutions

Limit which sensor modes appear when cycling resolutions.

```json
"resolutions": {
  "k_steps": [1.5, 2, 4],
  "bit_depths": [10, 12],
  "custom_modes": {
    "imx283": [
      {"width": 3936, "height": 2176, "bit_depth": 12, "fps_max": 24}
    ]
  }
}
```

`k_steps` – K‑style categories for allowed widths. Modes are grouped to the nearest half‑K. Example: 1332×990 counts as **1.5 K**.
<br>`bit_depths` – list of bit depths to expose.
<br>`custom_modes` – optional extra modes per sensor if the driver advertises none.

!!! note ""

    The stock Cinemate 3.3.1 setting is `[1.5, 2, 4]`, so 4K-class modes are visible by default when the sensor reports them. Remove `4` from `k_steps`, for example `[1.5, 2]`, when you intentionally want to hide 4K-class modes in the UI.

## sensors

Points Cinemate at the sensor metadata database used for known packing modes, documentation metadata, and sustainable FPS annotations.

```json
"sensors": {
  "database_file": "resources/sensors.json"
}
```

`database_file` – JSON file containing compatible sensor metadata. The default file is `resources/sensors.json`.

## camera

Low-level camera runtime options passed directly to `cinepi-raw`.

```json
"camera": {
  "override_camera_name": false,
  "camera_name": "Blackmagic Pocket Cinema Camera 4K",
  "raw_buffer_count": 0
}
```

`override_camera_name` – when `true`, the value of `camera_name` is passed to `cinepi-raw` as `--unique-camera-model` and written into the `UniqueCameraModel` DNG tag of every recorded frame. Set to `false` (default) to use the built-in default, which is `"Blackmagic Pocket Cinema Camera 4K"`. This tag is what NLEs such as DaVinci Resolve display as the camera identifier and use for BRAW/DNG color science look-up.<br>
`camera_name` – the string to embed when `override_camera_name` is `true`. Has no effect when `override_camera_name` is `false`.<br>
`raw_buffer_count` – override the number of in-flight sensor buffers allocated by `cinepi-raw`. `0` (default) defers to the active storage-profile value. Raise this only when you see single-frame TC holes on a slow filesystem and `grep Cma /proc/meminfo` confirms available CMA headroom (~25 MB per extra buffer at 4K).

## dynamic_resolution

Automatically chooses the highest measured sustainable resolution for the user-selected frame rate, detected sensor, storage type, and storage filesystem.

```json
"dynamic_resolution": {
  "enabled": false,
  "profile": "default",
  "profiles_file": "resources/dynamic_resolution_profiles.json",
  "policy": "highest_sustainable_resolution",
  "safety_margin_fps": 0,
  "match_tolerance_px": 32
}
```

`enabled` – set to `true` to allow Cinemate to switch resolution automatically when the current desired resolution cannot sustain the selected FPS.
<br>`profile` – named standard measurement profile to load from `profiles_file`. The stock profile is `default`.
<br>`profiles_file` – JSON file containing measured sustainable-FPS rows. The stock file is `resources/dynamic_resolution_profiles.json`.
<br>`policy` – selection strategy. The current policy, `highest_sustainable_resolution`, chooses the largest measured mode that can sustain the requested FPS.
<br>`safety_margin_fps` – subtract this many FPS from every measured row before deciding whether it is safe.
<br>`match_tolerance_px` – pixel tolerance used when matching measured rows to driver modes. This lets a measured `3856 x 2180` row match a nearby driver mode such as `3840 x 2160`.

Cinemate remembers the user's desired resolution. If you select a 4K mode and then raise FPS above that mode's measured sustainable limit, Cinemate switches to the highest measured mode that can sustain the FPS. When FPS returns to the desired mode's measured limit or below, Cinemate switches back. If no matching profile row exists for the detected sensor, storage type, filesystem, desired mode, and requested FPS, Cinemate leaves the current resolution unchanged.

When dynamic resolution is enabled, the maximum FPS shown by Cinemate comes from the measured dynamic-resolution profile for the current sensor, storage type, and filesystem, but only when the desired mode itself has a measured row. When dynamic resolution is disabled, maximum FPS comes from the sensor readout reported by `cinepi-raw`, as before.

The storage type comes from the mounted RAW device and is usually `ssd`, `cfe`, `nvme`, or `unknown`. The filesystem comes from the mounted RAW volume and is usually `ext4`, `exfat`, or `ntfs`.

Each profile row has this shape:

```json
{
  "sensor": "imx585",
  "sensor_aliases": ["imx585_mono"],
  "storage_type": "cfe",
  "filesystem": "ext4",
  "media_model": "CFE Hat / NVMe",
  "width": 3856,
  "height": 2180,
  "bit_depth": 12,
  "sustainable_fps": 40,
  "max_fps_no_buffer": 40,
  "test_duration_seconds": null,
  "buffer_peak_frames": 0,
  "drop_frames": 0,
  "confidence": "empirical",
  "notes": "4K desired-mode threshold for dynamic resolution."
}
```

`sustainable_fps` is the preferred field for new rows and means recording without dropped frames. `max_fps_no_buffer` is still accepted for older rows and for rows where you have verified no buffer growth as well.

Dynamic-resolution limits are determined by the selected stock JSON profile only. To change the lookup table, update `resources/dynamic_resolution_profiles.json`.

## buttons

Defines GPIO push buttons. Each entry describes one button and the actions it triggers.

```json
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


## two_way_switches

Latching on/off switches. Cinemate triggers an action whenever the state changes.

```json
{
  "pin": 27,
  "state_on_action":  {"method": "set_all_lock", "args": [1]},
  "state_off_action": {"method": "set_all_lock", "args": [0]}
}
```

## three_way_switches

Three-position switches made from three GPIO inputs. Cinemate checks which pin is active and then runs the matching action.

```json
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

## combined_actions

Combined actions let one button act as a modifier for another button.

```json
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

## rotary_encoders

Rotary encoders used for fine adjustment of settings. These can be wired straight to the GPIO pins of the Pi. The optional `button_pin` uses the same action grammar as the `buttons` section.

```json
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

<br>`enabled` – optional per-encoder switch; set `false` to keep an example in the file without claiming pins at startup.
<br>`clk_pin` and `dt_pin` – the two pins of the encoder.
<br>`button_pin` – optional BCM pin for the encoder push button.
<br>`button_actions` – optional press/click/hold actions for the encoder push button.
<br>`encoder_actions` – commands to run when turning the dial.

## quad_rotary_controller

Support for the Adafruit Neopixel Quad I2C rotary encoder breakout. Each entry maps one of the four dials to a setting and defines the push button actions similar to the `buttons` section. The stock settings include this mapping with `enabled` set to `false`; set it to `true` only when the board is connected.

```json
"quad_rotary_controller": {
  "enabled": true,
  "encoders": {
    "0": {"setting_name": "iso", "button": {"press_action": {"method": "rec"}}},
    "1": {"setting_name": "shutter_a", "button": {"press_action": {"method": "set_fps_double"}}},
    "2": {
      "setting_name": "fps",
      "button": {
        "press_action": "None",
        "single_click_action": {"method": "set_resolution"},
        "double_click_action": {"method": "restart_cinemate"},
        "triple_click_action": {"method": "reboot"},
        "hold_action": {"method": "toggle_mount"}
      }
    },
    "3": {"setting_name": "wb", "button": {"press_action": {"method": "rec"}}}
  }
}
```

`enabled` – turn the quad rotary controller on or off.<br>`encoders` – mapping of each dial to a setting and button actions.

## i2c_oled

Configuration for the optional OLED status screen. This can be useful for presenting extra information appart from the HDMI/web display.

```json
"i2c_oled": {
  "enabled": true,
  "width": 128,
  "height": 64,
  "font_size": 30,
  "values": ["write_speed_to_drive"]
}
```

`enabled` – turn the OLED display on or off.
`width / height` – pixel dimensions of your screen.
`font_size` – size of the displayed text.
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
