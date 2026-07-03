# Storage pre-roll warm-up

When starting up, or when storage media is attached, Cinemate records and discards a quick test clip to warm up the storage media.

To disable it, set `"auto_storage_preroll": false` in the `settings` section of `settings.json`.

You can still warm up media on demand: type `storage preroll` in the Cinemate CLI.



Each run follows a five-step snapshot/restore sequence:

1. The helper aborts if no media is mounted or if a real recording is already in progress. It will try again after the next trigger.

2. Before recording, it snapshots the current user-facing state: the selected FPS, `last_dng_cam0`, `last_dng_cam1`, `recording_time`, `recording_tc_rec`, `recording_time_tod`, and the clip directories already present on the mounted volume.

3. It switches the camera to the maximum FPS supported by the current mode, raises the preroll-active flag, starts recording, waits until `rec` is live, records for the configured duration (two seconds by default), and then waits for all file buffers to flush.

4. After the run, it restores the previous FPS, deletes any new pre-roll clip directories, and writes the saved `last_dng_*` and recording-timer values back to Redis. This keeps the deleted warm-up take from becoming the "latest recording" shown in the GUI or CLI.

5. While pre-roll is active, Cinemate skips final frame-sync analysis and drop-frame/SYNC warnings. The Simple GUI hides clip names and recording time while showing a blue background.
