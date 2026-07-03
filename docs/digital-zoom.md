# Digital zoom

Digital zoom is a **preview punch-in**. It magnifies the monitor image so you can check focus and framing — it does not change the optics or the recorded sensor area.

## Controls

From the terminal:

| Command            | What it does                                              |
| ------------------ | -------------------------------------------------------- |
| `set zoom <float>` | Set the zoom factor, e.g. `set zoom 2`                   |
| `set zoom`         | Cycle through the configured zoom steps                  |
| `inc zoom`         | Step to the next zoom level                              |
| `dec zoom`         | Step to the previous zoom level                          |

You can also map these to a button or rotary encoder in `settings.json`.

## Settings

The zoom behaviour lives in the `preview` section of [`settings.json`](settings-json.md):

- `default_zoom` – the zoom factor applied at startup (default `1.0`).
- `zoom_steps` – the list of factors that `set zoom`, `inc zoom`, and `dec zoom` cycle through.
