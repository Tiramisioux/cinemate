# Settings file

This file controls how the camera behaves and how your buttons, switches and displays are mapped. It lives in `~/cinemate/src/settings.json`. You can edit it with any text editor; the settings take effect the next time you start Cinemate.

!!! tip ""
    For easy editing of settings on the preinstalled image file, type `editsettings` anywhere in Raspberry Pi terminal.

The configuration is structured as JSON. Each top‑level key describes a feature area of the system. Below is a tour of every section and what the options do.

## welcome message

Text or image displayed briefly when Cinemate starts.

```yaml
"welcome_image": null
"welcome_message": "THIS IS A COOL MACHINE",
```

Set `welcome_image` to the path of a bitmap file to show a logo instead of text. 

Example path: `/home/pi/welcome_image.bmp`. 

If `welcome image` path is set, this will override the text message.

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
`enabled` – set to `true` to start the hotspot automatically on boot. If set to `false`, CineMate will still start its web ui but stream it on whatever network the Pi is connected to.

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

## preview

Adjusts zoom levels for the HDMI/browser preview.

```json
"preview": {
  "default_zoom": 1.0,
  "zoom_steps": [1.0, 1.5, 2.0]
}
```

`default_zoom` – magnification factor used at startup.<br>`zoom_steps` – list of zoom factors you can cycle through with the `set_zoom_step` command.

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
  "rec_out_pin": [6, 21]
}
```

* `pwm_pin` – outputs a strobe for shutter sync or external devices.

* `rec_out_pin` – list of pins pulled high while recording (useful for tally LEDs).

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

## settings

General options for runtime behaviour.

```json
"settings": {
  "light_hz": [50, 60],
  "conform_frame_rate": 24
}
```

`light_hz` – list of mains frequencies used to calculate flicker‑free shutter angles. These are added to the shutter angle array and also dynamically calculated upon each fps change. This way, there is always a flicker free shutter angle value close by, when toggling through shutter angles, either via the cli or using buttons/pots/rotary encoder.
<br>`conform_frame_rate` – frame rate intendend for project conforming in post. This setting is not really used by CineMate except for calculating the recording timecode tracker in redis but might be used in future updates.

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

When enabled, ignores the preset arrays and exposes the full range supported by the sensor.

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

## rotary_encoders

Rotary encoders used for fine adjustment of settings. These can be wired straight to the GPIO pins of the Pi.

```json
{
  "clk_pin": 9,
  "dt_pin": 11,
  "detents_per_pulse": 2,
  "encoder_actions": {
    "rotate_clockwise":        {"method": "inc_iso"},
    "rotate_counterclockwise": {"method": "dec_iso"}
  }
}
```

<br>`clk_pin` and `dt_pin` – the two pins of the encoder.<br>`detents_per_pulse` – number of mechanical clicks per electrical pulse (use 2 for encoders that require two detents for one pulse). This scales the action count to match the detents you feel.<br>`encoder_actions` – commands to run when turning the dial.

## quad_rotary_controller

Support for the Adafruit Neopixel Quad I2C rotary encoder breakout. Each entry maps one of the four dials to a setting and defines the push button actions similar to the `buttons` section.

```json
"quad_rotary_controller": {
  "enabled": true,
  "encoders": {
    "0": {"setting_name": "iso", "detents_per_pulse": 2, "button": {"press_action": {"method": "rec"}}},
    "1": {"setting_name": "shutter_a", "detents_per_pulse": 1, "button": {"press_action": {"method": "set_fps_double"}}},
    "2": {
      "setting_name": "fps",
      "detents_per_pulse": 2,
      "button": {
        "press_action": "None",
        "single_click_action": {"method": "set_resolution"},
        "double_click_action": {"method": "restart_cinemate"},
        "triple_click_action": {"method": "reboot"},
        "hold_action": {"method": "toggle_mount"}
      }
    },
    "3": {"setting_name": "wb", "detents_per_pulse": 1, "button": {"press_action": {"method": "rec"}}}
  }
}
```

`enabled` – turn the quad rotary controller on or off.<br>`encoders` – mapping of each dial to a setting and button actions.<br>`detents_per_pulse` – number of mechanical clicks per electrical pulse; multiply the setting changes per pulse so each detent feels like one step.

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
