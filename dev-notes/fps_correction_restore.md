# Restoring `sensor_fps_correction`

The per-(sensor, mode, fps) FPS correction-factor pipeline was removed in commit
**`2f79397`** ("Remove sensor_fps_correction factor mechanics") because the
cinepi-raw **frame-rate phase lock** supersedes it: the closed-loop servo holds the
recorded cadence on the nominal fps directly (Pi-verified dead-on, 0 drops, on
imx283 + imx585), so the static factor table is no longer needed.

## Bring it back

**Option A — revert the commit (preferred, restores the engine):**

```sh
git revert 2f79397
```

**Option B — apply the restore patch:**

```sh
git apply dev-notes/fps_correction_restore.patch   # from the repo root
```

Either re-creates `src/module/sensor_correction_factors.py`, the
`SensorDetect.get_fps_correction_factor()` lookup, the `set_fps()` factor multiply,
the redis_listener post-take correction-suggestion engine, and `docs/fps-correction.md`.

## Also re-add the per-camera setting keys (optional)

These trivial keys were dropped in the *settings-cleanup* commit, not in `2f79397`.
`set_fps` reads the flag with a `True` default, so correction works without them —
re-add them only to expose the toggle in `settings.json` again:

- `src/settings.json` and `resources/settings/settings_default.json`, under
  `camera.cam0` / `camera.cam1`:
  `"sensor_fps_correction": true,`
- `src/module/config_loader.py` (per-camera defaults loop):
  `cam.setdefault("sensor_fps_correction", True)`
- `src/module/cinepi_multi.py` (`CameraProcess` init):
  `self.sensor_fps_correction = cam_cfg.get('sensor_fps_correction', True)`
