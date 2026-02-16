# Storage pre-roll warm-up

Cinemate includes an automatic "storage pre-roll" that records and discards a short clip to make sure new media can keep up. The warm-up runs the recorder at full speed so SSDs spin up, controllers cache their write tables and the rest of the pipeline has a chance to stabilise.

## When the pre-roll runs

- **On startup:** after a brief settle delay, the helper checks whether the RAW volume is mounted and triggers a warm-up run if so.

- **Whenever storage mounts:** the SSD monitor emits an event that immediately schedules another pre-roll so freshly attached drives are exercised before you use them.

- **On demand:** you can type `storage preroll` in the Cinemate CLI to queue a run manually. The command is ignored while a pre-roll is already active so repeated presses do not stack up.

The module keeps a lock so only one warm-up runs at a time and exposes the `storage_preroll_active` Redis key to let the UI show progress.

## What happens during a run

1. The helper aborts if no media is mounted or if a real recording is in progress; it will try again after the next trigger.

2. It records the user's current FPS choice, switches the camera to the maximum FPS supported by the sensor/mode and raises a "pre-roll active" flag so other systems (such as the `rec` command) leave it alone.

3. Cinemate starts recording, waits until the REC flag is live, keeps rolling for the configured duration (two seconds by default) and then stops once all file buffers have flushed to disk.

4. After recording the 2 second temporary clip, it restores the previous FPS, clears the activity flag and deletes the temporary clip directory.
