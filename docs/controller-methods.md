# CinePi Controller Methods

CineMate exposes most of its runtime features through the `CinePiController` class in `src/module/cinepi_controller.py`. Buttons, the pseudo‑CLI and the web UI all call these methods. Below is an overview of the most useful ones and what they do.

## Recording

- `rec()` – Toggle recording on or off depending on the current state.
- `start_recording()` – Begin recording if storage is mounted and space is available.
- `stop_recording()` – Stop the current recording.

## Exposure settings

These methods adjust ISO, shutter angle and frame rate. Increment/decrement helpers step through the arrays defined in `settings.json` unless free mode is active.

- `set_iso(value)` – Set ISO to a specific value.
- `inc_iso()` / `dec_iso()` – Step ISO up or down.
- `set_shutter_a(value)` – Set the *actual* shutter angle. In normal mode the value snaps to the nearest valid angle.
- `inc_shutter_a()` / `dec_shutter_a()` – Cycle through shutter angles.
- `set_shutter_a_nom(value)` – Set the *nominal* shutter angle used for motion‑blur calculations.
- `inc_shutter_a_nom()` / `dec_shutter_a_nom()` – Step the nominal shutter angle.
- `set_fps(value)` – Apply a new frame rate while respecting locks and sync mode.
- `inc_fps()` / `dec_fps()` – Step through the configured FPS list.

## White balance

- `set_wb(kelvin=None, direction='next')` – Set white balance to a specific Kelvin temperature or cycle through presets if no value is given.
- `inc_wb()` / `dec_wb()` – Move to the next or previous white balance preset.

## Resolution and preview

- `set_resolution(value=None)` – Switch sensor mode. Passing `None` cycles through the available modes.
- `set_anamorphic_factor(value=None)` – Change the preview’s anamorphic stretch. Omit the value to toggle between presets.
- `set_zoom(value=None, direction="next")` – Adjust the digital zoom factor. Without a value it steps through `preview.zoom_steps`.
- `inc_zoom()` / `dec_zoom()` – Convenience wrappers around `set_zoom()`.

## Storage control

- `mount()` / `unmount()` – Mount or unmount the external drive.
- `toggle_mount()` – Convenience method that mounts when no drive is present and unmounts otherwise.

## System information

- `print_settings()` – Log all current Redis parameters.
- `ssd_monitor.space_left()` – Report remaining disk space (used by the `space` CLI command).
- `reboot()` – Safely reboot the Pi.
- `safe_shutdown()` – Shut the Pi down cleanly.
- `restart_cinemate()` – Restart the Cinemate Python process without rebooting.

## Locks and sync modes

These helpers prevent accidental changes or keep shutter speed in sync with FPS:

- `set_shutter_a_sync_mode(value=None)` – Enable exposure‑sync mode (1) or normal mode (0). Omitting the value toggles the state.
- `set_iso_lock(value=None)` – Toggle or explicitly set the ISO lock.
- `set_shutter_a_nom_lock(value=None)` – Lock or unlock the nominal shutter angle.
- `set_shu_fps_lock(value=None)` – Lock both shutter angle and FPS together.
- `set_fps_lock(value=None)` – Lock or unlock the frame rate.
- `set_all_lock(value=None)` – Toggle all three locks at once.
- `set_fps_double(value=None)` – Temporarily double the frame rate. Omit the value to toggle.

## Free‑mode toggles

When free mode is enabled, the preset arrays from `settings.json` are ignored and you can dial any value supported by the sensor.

- `set_iso_free(value=None)`
- `set_shutter_a_free(value=None)`
- `set_fps_free(value=None)`
- `set_wb_free(value=None)`

## Sensor‑specific tools

- `set_filter(value=None)` – Enable or disable the StarlightEye IR cut filter (IMX585 sensors only).

