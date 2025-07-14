# `settings.json` Cheat Sheet

A quick-reference table of every setting in `settings.json`, what it does, and its allowed values.
```json
    {
      "pin": 27,
      "state_on_action": {"method": "set_all_lock", "args": [1]},
      "state_off_action": {"method": "set_all_lock", "args": [0]}
    },
```

```python
if self.button.is_pressed:      # high at rest → treat as “inverse”
    self.inverse = True
```

## Geometry

| JSON Path                             | Description                                         | Values           |
|---------------------------------------|-----------------------------------------------------|------------------|
| `geometry.camX.rotate_180`            | Rotate image 180° on startup                        | `true` / `false` |
| `geometry.camX.horizontal_flip`       | Flip image horizontally on startup                  | `true` / `false` |
| `geometry.camX.vertical_flip`         | Flip image vertically on startup                    | `true` / `false` |

---

## Output

| JSON Path                    | Description                                                          | Values                      |
|------------------------------|----------------------------------------------------------------------|-----------------------------|
| `output.camX.hdmi_port`      | Select DRM connector for HDMI output (`cinepi-raw --hdmi-port`)      | `0`, `1`, or `-1` (auto)    |

---

## GPIO Outputs

| JSON Path                   | Description                            | Values                      |
|-----------------------------|----------------------------------------|-----------------------------|
| `gpio_output.sys_LED[]`     | Single-colour status LEDs              | `pin` + ordered `rules`     |
| `gpio_output.sys_LED_RGB[]` | RGB status LEDs                        | `pins` + ordered `rules`    |
| `gpio_output.pwm_pin`       | PWM pin for strobe / shutter sync      | BCM pin number              |

Each rule maps a Redis key (and optional value) to a behaviour (`steady`, `blink`, `blink_long`, or `pulse`). 

RGB LEDs also take a `color` using one of: red, green, blue, yellow, cyan, magenta, white.

`type` can be `common_cathode` (default) or `common_anode` to match your LED wiring.

---

## Fixed-Palette Arrays

| JSON Path               | Description                                  | Values                              |
|-------------------------|----------------------------------------------|-------------------------------------|
| `arrays.iso_steps`      | ISO step presets (if `iso_free = false`)     | `[100,…,sensor_native]`             |
| `arrays.shutter_a_steps`| Shutter angles (if `shutter_a_free = false`) | `[1.0,…,360.0]` (degrees)           |
| `arrays.fps_steps`      | Frame-rate presets (if `fps_free = false`)   | integers ≤ sensor-mode `fps_max`    |
| `arrays.wb_steps`       | White-balance Kelvin presets                 | `[2000,…,9000]` (Kelvin)            |

---

## Flicker Suppression

| JSON Path             | Description                                                      | Values               |
|-----------------------|------------------------------------------------------------------|----------------------|
| `settings.light_hz`   | Frequencies used to calculate flicker-free shutter angles        | `[50]`, `[60]`, or `[50,60]` |

---

## Analog Controls

| JSON Path                   | Description                                               | Values      |
|-----------------------------|-----------------------------------------------------------|-------------|
| `analog_controls.*_pot`     | ADC channel for ISO, shutter, FPS, or WB (Grove HAT)      | `0–7` or `null` |

---

## Free-Mode Overrides

When `true`, ignores the fixed arrays and exposes full legal ranges.

| JSON Path                    | Description                      | Values           |
|------------------------------|----------------------------------|------------------|
| `free_mode.iso_free`         | Full ISO range                   | `true` / `false` |
| `free_mode.shutter_a_free`   | Full shutter-angle range         | `true` / `false` |
| `free_mode.fps_free`         | Full frame-rate range            | `true` / `false` |
| `free_mode.wb_free`          | Full white-balance range         | `true` / `false` |

> **Free ranges:** ISO 100–3200, Shutter 1.0°–360.0°, FPS 1–fps_max, WB 1000–10000 K

---

## Anamorphic Preview

| JSON Path                                     | Description                                | Values               |
|-----------------------------------------------|--------------------------------------------|----------------------|
| `anamorphic_preview.anamorphic_steps`         | Anamorphic squeeze factors                 | list of floats ≥ 1.0 |
| `anamorphic_preview.default_anamorphic_factor`| Initial factor stored in Redis on power-up | one of the above     |

---

## Buttons & Switches

| JSON Path                 | Description                                                   | Values                            |
|---------------------------|---------------------------------------------------------------|-----------------------------------|
| `buttons[]`               | SmartButton entries: `press_action`, `click_action`, `hold_action`, etc. | List of BCM pins + args          |
| `two_way_switches[]`      | Latching switches: `state_on_action` / `state_off_action`      | `pin` + optional `pull_up`       |
| `three_way_switches[]`    | 3-position switches: `state_0/1/2_action`                     | `pins`: [low, mid, high]         |

---

## Encoders

| JSON Path                  | Description                                               | Values                        |
|----------------------------|-----------------------------------------------------------|-------------------------------|
| `rotary_encoders[]`        | GPIO rotary (CLK/DT) + optional button                    | `clk_pin`, `dt_pin` BCM pins  |
| `quad_rotary_encoders`     | I²C RGB Encoder breakout (0x49) with four dials/buttons  | Indices `"0"`–`"3"`           |

---

## OLED Status Screen

| JSON Path           | Description                                              | Values                              |
|---------------------|----------------------------------------------------------|-------------------------------------|
| `i2c_oled.width`    | OLED panel width in pixels                               | integer                             |
| `i2c_oled.height`   | OLED panel height in pixels                              | integer                             |
| `i2c_oled.values`   | Redis keys or pseudo-keys to display (e.g. `cpu_temp`)   | ordered list                        |

```python
if self.button.is_pressed:      # high at rest → treat as “inverse”
    self.inverse = True
```

---

## GUI

| JSON Path                 | Description                                     | Values                 |
|---------------------------|-------------------------------------------------|------------------------|
| `gui.recording_indicator` | Recording indicator style (`frame` or `dot`)    | `"frame"` / `"dot"`