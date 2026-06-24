# Storage pre-roll warm-up

A short blue screen at startup, or when you insert a drive, is normal. Cinemate records and discards a quick test clip to warm up your media. This makes your first real recording reliable.

To disable it, set `"auto_storage_preroll": false` in the `settings` section of `settings.json`.

You can still warm up media on demand: type `storage preroll` in the Cinemate CLI.

## When the pre-roll runs

- **On startup**, after the boot splash and camera come up.
- **When storage mounts**, so a freshly attached drive is exercised before you use it.
- **On demand**, when you type `storage preroll` in the CLI.

Only one warm-up runs at a time.

??? note "How it works"

    The warm-up does not arm immediately in `StoragePreroll.__init__()`. Instead, `main.py` calls `mark_startup_ready()` after the welcome-message/Plymouth handoff, GUI startup, and preview rebind are finished. This keeps the warm-up clip from racing the boot splash or the first camera restart. Mount-triggered warm-ups during startup are deferred until ready and scheduled as a `startup-mount` run. After startup, the SSD monitor schedules a warm-up whenever storage mounts. Repeated manual requests do not stack while a pre-roll is already active.

    While active, Cinemate raises the `storage_preroll_active` Redis key so the GUI, CLI, and recording logic treat the temporary take as a warm-up rather than a user clip. Disabling `auto_storage_preroll` still clears this flag during startup, so the rest of the recording path stays normal.

    Each run follows a five-step snapshot/restore sequence:

    1. The helper aborts if no media is mounted or if a real recording is already in progress. It will try again after the next trigger.

    2. Before recording, it snapshots the current user-facing state: the selected FPS, `last_dng_cam0`, `last_dng_cam1`, `recording_time`, `recording_tc_rec`, `recording_time_tod`, and the clip directories already present on the mounted volume.

    3. It switches the camera to the maximum FPS supported by the current mode, raises the preroll-active flag, starts recording, waits until `rec` is live, records for the configured duration (two seconds by default), and then waits for all file buffers to flush.

    4. After the run, it restores the previous FPS, deletes any new pre-roll clip directories, and writes the saved `last_dng_*` and recording-timer values back to Redis. This keeps the deleted warm-up take from becoming the "latest recording" shown in the GUI or CLI.

    5. While pre-roll is active, Cinemate skips final frame-sync analysis and drop-frame/SYNC warnings. The Simple GUI hides clip names and recording time while showing a blue background.
