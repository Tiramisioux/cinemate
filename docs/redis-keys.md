# Redis key reference

This page lists the Redis keys used by Cinemate and CinePi-raw. Values are simple strings, so you can inspect them with `redis-cli`.

Each entry explains which component normally writes the key and whether it makes sense to change it manually.

| Key | Written by | Description | Safe to change manually? |
|-----|------------|-------------|--------------------------|
| anamorphic_factor | Cinemate | Preview squeeze factor for anamorphic lenses | Yes (publish key to apply) |
| iso | Cinemate -> CinePi-raw | Sensor gain in ISO | Yes |
| shutter_a | Cinemate -> CinePi-raw | Active shutter angle in degrees | Yes |
| shutter_angle_nom | Cinemate | Nominal shutter angle before sync/free-stepping adjustments | Yes |
| shutter_a_sync_mode | Cinemate | Keep exposure constant when changing FPS | Yes |
| shutter_angle_actual | Cinemate | Calculated shutter angle actually applied after clamping/sync | No |
| shutter_angle_transient | Cinemate | Temporary value used during ramps | No |
| exposure_time | Cinemate | Current exposure time in seconds | No |
| fps | Cinemate -> CinePi-raw | Target frames per second | Yes |
| fps_user | Cinemate | User-selected FPS value stored by the UI/controller | No |
| fps_actual | Cinemate (RedisListener) | Measured frame rate: the mean of the last 100 inter-frame intervals CinePi-raw reports on `cp_stats`. Reports cam0 on dual-sensor rigs | No |
| user_changing_fps | Cinemate (RedisListener) | `1` while an fps change is debouncing; cleared once `fps` has been stable for a while | No |
| fps_last | Cinemate | FPS at the previous shutdown, restored as the startup FPS | No |
| fps_max | Cinemate startup | Maximum FPS supported by the current sensor mode | No |
| fps_phase_lock | Cinemate startup | Runtime enable for CinePi-raw's closed-loop frame-rate phase lock, from `sensors.<cam>.phase_lock` in settings.jsonc (default on); read once at CinePi-raw startup, not live | No |
| sensor_mode | Cinemate -> CinePi-raw startup | Active sensor resolution/mode index | Yes (causes pipeline restart) |
| bit_depth | Cinemate startup | Sensor bit depth (10, 12 or 16) for the selected mode | No |
| width / height | Cinemate startup | Active sensor resolution | No |
| mode | Cinemate startup | Composite `width:height:bit_depth:packing` string for the active sensor mode | No |
| packing | Cinemate startup | Sensor packing token for the active mode/platform: `P` (packed) or `U` (unpacked) | No |
| lores_width / lores_height | Cinemate startup | Preview stream resolution passed to CinePi-raw | No |

### Resolution switching

Whether triggered manually (`set resolution`) or automatically by dynamic resolution, a
resolution change publishes a target/in-flight state so the GUI can show a "switching"
transition instead of a stale value.

| Key | Written by | Description | Safe to change manually? |
|-----|------------|-------------|--------------------------|
| dynamic_resolution_enabled | Cinemate | Toggle for automatic FPS-driven resolution downgrade/upgrade (`set dynamic resolution`); persisted and read back at startup, defaulting to on when unset | Yes |
| dynamic_resolution_active | Cinemate | `1` while a lower resolution mode is currently substituted in to sustain the requested FPS | No |
| dynamic_resolution_desired_mode | Cinemate | The sensor mode the user actually asked for; dynamic resolution switches away from and back to this mode as FPS allows | No |
| resolution_switching | Cinemate | `1` while a resolution change (manual or dynamic) is in flight; cleared when CinePi-raw's raw-stream-ready log line reports the new stream at the target size, or after a 2.5 s hold timer | No |
| resolution_target_mode | Cinemate | Sensor mode index CinePi-raw is being switched to | No |
| resolution_target_width / resolution_target_height | Cinemate | Target resolution CinePi-raw's raw-stream-ready log line is matched against to clear `resolution_switching` | No |
| resolution_target_bit_depth | Cinemate | Target bit depth for the in-flight resolution switch | No |
| wb | Cinemate -> CinePi-raw | White-balance temperature in Kelvin | Yes |
| wb_user | Cinemate | Kelvin value stored before conversion to `cg_rb` | No |
| cg_rb | Cinemate -> CinePi-raw | White-balance gain pair `1/R,1/B` | Yes (advanced) |
| zoom | Cinemate | Digital zoom factor for preview streams | Yes |
| hdmi_preview_source | Cinemate -> CinePi-raw | Dual-sensor HDMI preview source: `both`, `cam0`, `cam1`, `pip_cam0`, or `pip_cam1`. Read live by the compositor; no restart | Yes |
| ir_filter | Cinemate -> CinePi-raw | Toggle IR-cut filter (IMX585 only) | Yes |
| hdr | Cinemate -> CinePi-raw startup | ClearHDR state (imx585): `1` makes CinePi-raw launch with `--hdr sensor`. Set automatically when a ClearHDR sensor mode is selected; changing it requires a camera restart | No (select an HDR mode via `set resolution`) |
| hdr_threshold_low | Cinemate -> CinePi-raw | ClearHDR data-selection threshold, low side (0–4095). Applied live to the sensor (as a pair with `hdr_threshold_high`), and re-applied at every CinePi-raw start | Yes (publish key to apply) |
| hdr_threshold_high | Cinemate -> CinePi-raw | ClearHDR data-selection threshold, high side (0–4095). Applied live to the sensor (as a pair with `hdr_threshold_low`), and re-applied at every CinePi-raw start | Yes (publish key to apply) |
| hdr_blend | Cinemate -> CinePi-raw | ClearHDR HG/LG blending mode, driver menu 0–8 (0 = HG 1/2 + LG 1/2). Applied live | Yes (publish key to apply) |
| hdr_gain_adder | Cinemate -> CinePi-raw | ClearHDR low-gain path gain adder, driver menu 0–5 (2 = +12 dB). Applied live | Yes (publish key to apply) |
| thumbnail | Cinemate -> CinePi-raw | Embedded DNG thumbnail mode: `0` off, `1` mono, `2` colour. Applied live (no camera restart), written per frame into new takes only | Yes (publish key to apply) |
| thumbnail_size | Cinemate -> CinePi-raw | Right-shift downscale of the thumbnail plane; `0` is the full lores size. Changing it restarts the camera. Seeded at launch only — no CLI verb or settings-editor field yet | No (seeded to avoid a stale pre-Phase-0 resident value collapsing the thumbnail; change by hand only if you understand the restart) |
| log_encode_request | Cinemate | [CineMate Log](cinemate-log.md) request, shared across every launched camera like `hdr`: `0` off, `1` on (use the live mode's default target), `10` / `12` force that target. Set by `set log`; each camera resolves it independently against its own sensor at the next restart | No (use `set log`) |
| log_encode_cam0 / log_encode_cam1 | CinePi-raw (per camera) startup | The target that camera was actually **launched** with: `0` = off/not applied, else `10` or `12`. Drives the Simple GUI `LOG10`/`LOG12` badge — deliberately not the same as `log_encode_request`, so the badge never shows a target that isn't running yet | No |
| is_recording | Cinemate -> CinePi-raw | Requested record state. Edge-triggered: `0 -> 1` starts, `1 -> 0` stops | Yes |
| record_cams | Cinemate -> CinePi-raw | Dual-sensor record gate: which sensor(s) capture this take (`cam0+cam1`, `cam0`, or `cam1`). Published before `is_recording` flips; each `cinepi-raw` records only if its `--cam-port` is selected. Absent/empty = both | No |
| rec | Cinemate (RedisListener) | Derived runtime record flag based on `framecount` rising/going flat | No |
| framecount | CinePi-raw -> Cinemate | Total frames counted for the active take | No |
| buffer | CinePi-raw -> Cinemate | Raw frames currently buffered in RAM | No |
| buffer_size | CinePi-raw -> Cinemate | Total RAM buffer capacity in frames | No |
| is_buffering | CinePi-raw -> Cinemate | `1` while the RAM buffer is pre-filling | No |
| is_writing | CinePi-raw -> Cinemate | `1` while at least one camera is actively writing frames to disk | No |
| is_writing_buf | Cinemate | `1` while buffered frames are still flushing after stop | No |
| storage_preroll_active | Cinemate (StoragePreroll) | `1` during a storage warm-up clip | No |
| drop_frame | Cinemate (RedisListener) | Live pulse while a TC-gap event is active (advisory — frame may still be on disk) | No |
| drop_frame_count | Cinemate (RedisListener) | TC hole count in the current/last take (alias of `tc_hole_count`; kept for backward compatibility) | No |
| drop_frame_relay | Cinemate (RedisListener) | Short pulse used to mute REC tone for one frame on drop-frame events | No |
| drop_frame_during_last_take | Cinemate (RedisListener) | `1` only if the previous non-preroll take had frames genuinely absent from disk (`missing_frame_count > 0`) | No |
| tc_hole_count | Cinemate (RedisListener) | Number of TC gap events this take — frames that arrived late enough to create a timecode hole (inter-frame gap ≥ 1.5× frame period); file may still be present | No |
| missing_frame_count | Cinemate (RedisListener) | Frames confirmed absent from disk: `max(0, expected − recorded)` at end of take; authoritative signal for genuine data loss | No |
| frames_in_sync | Cinemate (RedisListener) | `1` if live/final expected vs recorded frame counts are within configured sync tolerance; defaults are +/- 2 frames live and +/- 1 frame after buffered writes flush | No |
| recording_time | Cinemate (RedisController timer) | Elapsed record time in seconds | No |
| recording_tc_rec | Cinemate (RedisController timer) | Elapsed record timecode | No |
| recording_time_tod | Cinemate (RedisController timer) | Time-of-day timecode updated during recording | No |
| tc_cam0 / tc_cam1 | Cinemate (RedisListener) | SMPTE timecode per camera derived from `timestamp*` stats fields | No |
| last_dng_cam0 / last_dng_cam1 | Cinemate (cinepi_multi log watcher) | Full path to the most recently written DNG for each camera | No |
| is_mounted | Cinemate (SSD monitor) | `1` when storage is mounted | No |
| storage_type | Cinemate (SSD monitor) | Drive type such as NVME, USB, or SD | No |
| storage_filesystem | Cinemate (SSD monitor) | Current filesystem type such as `ext4`, `exfat`, or `ntfs` | No |
| storage_mount_options | Cinemate (SSD monitor) | Actual mount options reported by the kernel for `/media/RAW` | No |
| storage_recorder_profile | Cinemate (SSD monitor) | Recorder worker profile selected from the current filesystem | No |
| space_left | Cinemate (SSD monitor) | Remaining free space in GB | No |
| write_speed_to_drive | Cinemate (SSD monitor) | Current write speed in MB/s | No |
| FSCK_STATUS | Cinemate (SSD monitor) | Result of the periodic filesystem check run after mount, e.g. `OK ...` / `FAIL ...`; cinemate-internal, cinepi-raw never reads it | No |
| file_size | Cinemate | Bytes per frame for the current mode | No |
| memory_alert | Cinemate | RAM percentage at which the watchdog auto-stopped recording (integer, set at the 80 % trip point); `0` when clear | No |
| cam_init | CinePi-raw | Internal startup flag | No |
| cameras | Cinemate startup | JSON list of detected cameras and port assignments | No |
| audio_capture_gain_db | Cinemate startup | Capture gain in dB applied to the active USB mic, from `audio_capture` in settings.jsonc (per-mic-type block, e.g. `16bit.capture_gain_db`); read back by the USB hotswap monitor on mic reconnect | No |
| trigger_mode | -- | Defined in `ParameterKey` but not currently written or read anywhere in Cinemate or CinePi-raw | -- |
| gui_layout | Cinemate | Path to the active GUI layout preset | No |
| pi_model | Cinemate startup | Platform family, not the full board name: `pi5` (Pi 5 / 500 / CM5), `pi4` (Pi 4 / 400 / CM4), `other`, or `unknown` | No |
| sensor | Cinemate startup | Active camera model key | No |
