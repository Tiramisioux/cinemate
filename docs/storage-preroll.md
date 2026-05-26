# Storage pre-roll warm-up

Cinemate includes an automatic "storage pre-roll" that records and discards a short clip to make sure new media can keep up. The warm-up runs the recorder at full speed so SSDs spin up, controllers cache their write tables, and the rest of the pipeline has a chance to stabilise before the first real take.

Set `"auto_storage_preroll": false` inside the `settings` section of `settings.json` to disable automatic startup and mount-triggered warm-ups. The manual `storage preroll` CLI command still works in this mode, so you can warm up media on demand. The rest of the recording path remains normal because Cinemate still clears the `storage_preroll_active` Redis flag during startup.

## When the pre-roll runs

- **On startup:** the warm-up no longer arms immediately in `StoragePreroll.__init__()`. Instead, `main.py` calls `mark_startup_ready()` after the welcome-message/Plymouth handoff, GUI startup, and preview rebind are finished. This keeps the warm-up clip from racing the boot splash or the first camera restart.

- **If storage mounts during startup:** mount-triggered warm-up is deferred until startup is marked ready. In that case the first run is scheduled as a `startup-mount` warm-up instead of firing immediately.

- **Whenever storage mounts after startup:** the SSD monitor schedules another warm-up so freshly attached drives are exercised before you use them.

- **On demand:** you can type `storage preroll` in the Cinemate CLI to queue a run manually. Repeated requests do not stack up while a pre-roll is already active.

Only one warm-up can run at a time. While active, Cinemate raises the `storage_preroll_active` Redis key so the GUI, CLI, and recording logic can treat the temporary take as a warm-up rather than a user clip.

## What happens during a run

1. The helper aborts if no media is mounted or if a real recording is already in progress. It will try again after the next trigger.

2. Before recording, it snapshots the current user-facing state: the selected FPS, `last_dng_cam0`, `last_dng_cam1`, `recording_time`, `recording_tc_rec`, `recording_time_tod`, and the clip directories already present on the mounted volume.

3. It switches the camera to the maximum FPS supported by the current mode, raises the preroll-active flag, starts recording, waits until `rec` is live, records for the configured duration (two seconds by default), and then waits for all file buffers to flush.

4. After the run, it restores the previous FPS, deletes any new pre-roll clip directories, and writes the saved `last_dng_*` and recording-timer values back to Redis. This keeps the deleted warm-up take from becoming the "latest recording" shown in the GUI or CLI.

5. While pre-roll is active, Cinemate skips final frame-sync analysis and drop-frame/SYNC warnings. The Simple GUI hides clip names and recording time while showing a blue background.
