# Commands reference

Cinemate doesn’t use a real shell parser. Instead, a background thread
reads simple text commands from SSH or the serial port and calls the
corresponding controller methods.

!!! note ""

     Note if you have Cinemate already running, for example by running the preinstalled image file, you first need to stop the autostarted instance in order and manually start Cinemate in order to use the Cinemate CLI:

     cd cinemate    # change directory to cinemate folder
     make stop      # stop the autostarted instance
     cinemate       # start cinemate manually

!!! note ""
     
     Commands without an explicit argument will toggle the current state when possible (e.g. `set fps lock` flips the lock; `set fps lock 1` forces it on).

!!! note ""

     All of the commands below can be easily mapped to GPIO buttons rotary encoders and other input devices. See [this section](settings-json.md) for how to configure the settings file.


| Command                                    | Argument        | Example                                 |  Function                                      |
|--------------------------------------------|-------------------|-----------------------------------------|-------------------------------------------------|
| `rec` / `stop`                             | `[s <seconds>] \| [f <frames>]` | `rec s 10`                           | Toggle recording or schedule an automatic stop after a timed duration or frame count |
| `analyze`                                  | `s\|sec\|seconds <N>` / `f\|frame\|frames <N>` | `analyze s 10` | Start bounded performance analysis, auto-stop at N seconds or frames, and export CSV/summary under `/media/RAW/_analysis` |
| `set iso <value>`                          | int               | `set iso 800`                           | Set ISO to nearest allowed step                 |
| `inc iso` / `dec iso`                      | -              |                                | Step ISO up or down                             |
| `set shutter a <angle>`                    | float             | `set shutter a 180`                     | Set actual shutter angle (snaps unless free/sync)|
| `inc shutter a` / `dec shutter a`          | -              |                          | Cycle through shutter angles                    |
| `set shutter a nom <angle>`                | float             | `set shutter a nom 180`                 | Set nominal shutter angle for motion blur       |
| `inc shutter a nom` / `dec shutter a nom`  | -              |                      | Step the nominal shutter angle                  |
| `set fps <value>`                          | float             | `set fps 24`                            | Change frame rate (snaps unless free)           |
| `inc fps` / `dec fps`                      | -              |                                | Step through FPS list                           |
| `set wb [<Kelvin>]`                        | int or none       | `set wb 5600`                           | Set white balance or cycle presets              |
| `inc wb` / `dec wb`                        | -              |                                 | Cycle white balance steps                       |
| `set resolution [<mode>]`                  | int or none       | `set resolution 2`                      | Apply or cycle sensor mode                      |
| `set anamorphic factor [<float>]`          | float or none     | `set anamorphic factor 1.33`            | Set or toggle anamorphic stretch                |
| `set zoom [<float>]`                       | float or none     | `set zoom 2`                            | Change digital zoom; omit to cycle              |
| `inc zoom` / `dec zoom`                    | -              |                              | Step preview zoom factor                        |
| `mount` / `unmount`                        | -              |                                  | Mount or unmount external storage               |
| `toggle mount`                             | -              |                           | Mount if not mounted, otherwise unmount         |
| `erase`                                    | -              | `erase`                                | Delete every clip on the mounted RAW volume without reformatting |
| `format`                                   | `[ext4\|ntfs]` | `format ntfs`                          | Reformat the RAW drive (defaults to ext4) and remount it |
| `storage preroll`                          | -              | `storage preroll`                       | Run the storage warm-up recording that prepares the media |
| `time`                                     | -              |                                   | Show system and RTC time                        |
| `set rtc time`                             | -              |                           | Copy system time to the RTC                     |
| `space`                                    | -              |                                  | Report remaining SSD space                      |
| `get`                                      | -              |                                    | Print all current settings (Redis keys in cp_controls channel)                      |
| `set shutter a sync [0/1]`                 | 0/1 or none       | `set shutter a sync 1`                  | Enable exposure sync mode                       |
| `set iso lock [0/1]`                       | 0/1 or none       |                           | Lock or unlock ISO setting                      |
| `set shutter a nom lock [0/1]`             | 0/1 or none       | `set shutter a nom lock`                | Lock or unlock nominal shutter                  |
| `set shutter a nom fps lock [0/1]`         | 0/1 or none       | `set shutter a nom fps lock 1`          | Lock nominal shutter and FPS together           |
| `set fps lock [0/1]`                       | 0/1 or none       | `set fps lock 1`                        | Lock or unlock the frame rate                   |
| `set all lock [0/1]`                       | 0/1 or none       | `set all lock 0`                        | Toggle all exposure locks at once               |
| `set fps double [0/1]`                     | 0/1 or none       |                         | Instant or toggled 2× FPS mode                  |
| `reboot` / `shutdown`                      | -              |                                 | Safely reboot or halt the Pi                    |
| `restart camera`                           | -              | `                        | Restart the libcamera pipeline                  |
| `restart cinemate`                         | -              |                       | Restart the Cinemate process                    |
| `set iso free [0/1]`                       | 0/1 or none       | `set iso free 1`                        | Allow any ISO instead of presets                |
| `set shutter a free [0/1]`                 | 0/1 or none       | `set shutter a free 0`                  | Allow any shutter angle                         |
| `set fps free [0/1]`                       | 0/1 or none       | `set fps free 1`                        | Allow any FPS                                   |
| `set wb free [0/1]`                        | 0/1 or none       | `set wb free`                           | Allow any white balance                         |
| `set filter <0/1>`                         | 0/1               | `set filter 1`                          | Toggle IR-cut filter (IMX585)                   |


## Timed recording shortcuts

The `rec` command now accepts timed modes so you can walk away from the camera while it captures a precisely bounded take.

- `rec s <seconds>` stops the recording after the requested duration. Short forms such as `sec`, `secs` and `seconds` are also accepted.
- `rec f <frames>` converts the requested frame count to seconds using the current FPS and schedules the stop for you. You can type `frame` or `frames` instead of `f`.

If recording is not already running, the CLI starts it automatically before arming the timer. An invalid or zero value is ignored so you cannot accidentally stop a clip immediately.【F:src/module/cli_commands.py†L205-L237】【F:src/module/cinepi_controller.py†L533-L591】

## Storage maintenance commands

Two new commands simplify preparing removable media directly from the Cinemate CLI:

- `erase` empties the mounted RAW volume without touching the filesystem structure so you can clear cards quickly between takes.
- `format [ext4|ntfs]` reformats the drive with the chosen filesystem (`ext4` by default), remounts it and refreshes the free-space monitor. The helper tolerates the common `ex4` typo and refuses unsupported targets so you do not accidentally create an unusable volume.

Both actions require the RAW drive to be mounted; otherwise the CLI reports an error and leaves the media untouched.

## Storage pre-roll warm-up

`storage preroll` triggers the automatic warm-up clip that Cinemate normally runs on startup or when you mount new storage. During the pre-roll, Cinemate temporarily drives the sensor at its maximum FPS, records a short burst, waits for buffers to flush and removes the test clip so the media is primed for the next real take.【F:src/module/storage_preroll.py†L40-L175】

See [Storage pre-roll warm-up](storage-preroll.md) for a detailed walkthrough of the workflow and tips on when to run it manually.



## Performance analyzer (phase 1)

Use the new analyzer command to record per-frame and system performance metrics to CSV during a bounded window:

- `analyze s <seconds>` (also accepts `sec`, `seconds`)
- `analyze f <frames>` (also accepts `frame`, `frames`)

Behavior:

- Reuses the same scheduling semantics as `rec s/f` and validates `N > 0`.
- If recording is not already running, Cinemate starts recording automatically before analysis.
- Recording and analysis both stop automatically when the requested window is reached.
- Output files are written to mounted RAW storage at:
  - `/media/RAW/_analysis/<YYYYmmdd_HHMMSS>_analyze.csv`
  - `/media/RAW/_analysis/<YYYYmmdd_HHMMSS>_summary.json`
- If `/media/RAW` is not mounted or not writable, the command fails cleanly and logs an error.

### CSV fields

Minimum schema written by the analyzer:

`monotonic_seq, wall_time_iso, sensor_timestamp_ns, timestamp_key_used, frame_count, fps_expected, fps_actual, dropped_frame_flag, drop_reason, buffer_used, buffer_size, is_buffering, is_writing_buf, write_speed_mb_s, cpu_percent_total, cpu_percent_per_core, ram_percent, cpu_temp_c, loadavg_1m, disk_write_bytes_delta, net_tx_bytes_delta, net_rx_bytes_delta, undervoltage_flag, storage_type, is_mounted, mic_connected, mic_sample_rate, mic_channels, proc_cpu_cinepi_raw, proc_cpu_cinemate, proc_cpu_redis, proc_cpu_arecord`

### Timestamp normalization

For each `cp_stats` sample, analyzer timestamp selection is:

1. `sensorTimestamp` (preferred)
2. fallback to `timestamp`

Both are normalized into `sensor_timestamp_ns`, and `timestamp_key_used` records which key was used (`sensorTimestamp` or `timestamp`).

### Drop-frame candidate detection

Phase-1 drop detection combines:

- timestamp gap check using `expected_period_ns = 1e9 / fps_expected`; a gap above `1.5x` period marks `timestamp_gap`
- framecount discontinuity checks (`framecount_discontinuity`)
- FPS deviation-only marker (`fps_deviation_only`)

### How to run

Examples:

- `analyze s 15`
- `analyze f 240`

Quick validation:

1. Run one command above.
2. Confirm files exist in `/media/RAW/_analysis/`.
3. Open CSV and verify non-empty rows plus expected headers.
4. Open summary JSON and confirm `rows_written` and `drop_candidates`.
