# Storage pre-roll warm-up

Cinemate includes an automatic "storage pre-roll" that records and discards a short clip to make sure new media can keep up before you roll on something important.【F:src/module/storage_preroll.py†L1-L57】 The warm-up runs the recorder at full speed so SSDs spin up, controllers cache their write tables and the rest of the pipeline has a chance to stabilise.

## When the pre-roll runs

- **On startup:** after a brief settle delay, the helper checks whether the RAW volume is mounted and triggers a warm-up run if so.【F:src/module/storage_preroll.py†L58-L96】
- **Whenever storage mounts:** the SSD monitor emits an event that immediately schedules another pre-roll so freshly attached drives are exercised before you use them.【F:src/module/storage_preroll.py†L40-L92】
- **On demand:** you can type `storage preroll` in the Cinemate CLI to queue a run manually. The command is ignored while a pre-roll is already active so repeated presses do not stack up.【F:src/module/cli_commands.py†L64-L72】【F:src/module/storage_preroll.py†L40-L92】

The module keeps a lock so only one warm-up runs at a time and exposes the `storage_preroll_active` Redis key to let the UI show progress.【F:src/module/storage_preroll.py†L26-L74】

## What happens during a run

1. The helper aborts if no media is mounted or if a real recording is in progress; it will try again after the next trigger.【F:src/module/storage_preroll.py†L108-L133】
2. It records the user's current FPS choice, switches the camera to the maximum FPS supported by the sensor/mode and raises a "pre-roll active" flag so other systems (such as the `rec` command) leave it alone.【F:src/module/storage_preroll.py†L134-L170】【F:src/module/cinepi_controller.py†L523-L542】
3. Cinemate starts recording, waits until the REC flag is live, keeps rolling for the configured duration (two seconds by default) and then stops once all file buffers have flushed to disk.【F:src/module/storage_preroll.py†L134-L170】
4. Finally, it restores the previous FPS, clears the activity flag and deletes any temporary clip directories created during the warm-up so the test footage never clutters your drive.【F:src/module/storage_preroll.py†L170-L208】

## Why it matters

Running a quick high-FPS burst before your first take helps avoid storage hiccups (for example, when an SSD controller is still negotiating link speed or establishing its allocation tables). Because Cinemate blocks normal `rec` requests while a pre-roll is active, you will always start your real recording on a fresh, warmed-up drive.【F:src/module/storage_preroll.py†L134-L208】【F:src/module/cinepi_controller.py†L523-L542】 Trigger it manually after swapping drives or when you have not recorded for a while to ensure peak performance.
