# `settings.json` Reference

The configuration file lives at `/home/pi/cinemate/src/settings.json`. It controls GPIO assignments, recording arrays and other options. Below is a summary of the main keys and the default values shipped with the project.

## Geometry and Output

```json
"geometry": {
  "cam0": {"rotate_180": false, "horizontal_flip": false, "vertical_flip": false},
  "cam1": {"rotate_180": false, "horizontal_flip": false, "vertical_flip": false}
},
"output": {
  "cam0": {"hdmi_port": 0},
  "cam1": {"hdmi_port": 1}
}
```

## GPIO Outputs

```json
"gpio_output": {"pwm_pin": 19, "rec_out_pin": [6, 21]}
```

## Arrays

```json
"arrays": {
  "iso_steps": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],
  "shutter_a_steps": [1, 45, 90, 135, 172.8, 180, 225, 270, 315, 346.6, 360],
  "fps_steps": [1, 2, 4, 8, 12, 16, 18, 24, 25, 33, 40, 50],
  "wb_steps": [3200, 4400, 5600]
}
```

## Misc settings

- **`settings.light_hz`** – `[50, 60]` values used to compute flicker‑free shutter angles.
- **`free_mode.*`** – when `true`, bypasses the fixed arrays and allows full ranges.
- **`anamorphic_preview`** – defines selectable anamorphic factors.

For a complete table of every key see `settings.schema.json` in the source tree.

## Default controls

- **Record button:** GPIO 5
- **Increase ISO:** GPIO 13 (momentary)
- **Decrease ISO:** GPIO 10
- **Double FPS:** GPIO 16
- **Resolution / system actions:** GPIO 26 with multiple click interactions
- **Rec LED output:** GPIO 6 and 21

These defaults can be edited directly in `settings.json` to match your hardware wiring.
