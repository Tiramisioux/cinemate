# Redis key reference

This page lists the Redis keys used by CineMate and CinePi-raw. Values are simple strings, so you can inspect them with `redis-cli`.

Each entry explains which component normally writes the key and whether it makes sense to change it manually.

| Key | Written by | Description | Safe to change manually? |
|-----|------------|-------------|--------------------------|
| anamorphic_factor | CineMate | Preview squeeze factor for anamorphic lenses | Yes (publish key to apply) |
| iso | CineMate -> CinePi-raw | Sensor gain in ISO | Yes |
| shutter_a | CineMate -> CinePi-raw | Active shutter angle in degrees | Yes |
| shutter_angle_nom | CineMate | Nominal shutter angle before sync/free-stepping adjustments | Yes |
| shutter_a_sync_mode | CineMate | Keep exposure constant when changing FPS | Yes |
| shutter_angle_actual | CineMate | Calculated shutter angle actually applied after clamping/sync | No |
| shutter_angle_transient | CineMate | Temporary value used during ramps | No |
| exposure_time | CineMate | Current exposure time in seconds | No |
| fps | CineMate -> CinePi-raw | Target frames per second | Yes |
| fps_user | CineMate | User-selected FPS value stored by the UI/controller | No |
| fps_actual | CineMate (RedisListener) | Measured frame rate: the mean of the last 100 inter-frame intervals CinePi-raw reports on `cp_stats`. Reports cam0 on dual-sensor rigs | No |
| user_changing_fps | CineMate (RedisListener) | `1` while an fps change is debouncing; cleared once `fps` has been stable for a while | No |
| fps_last | CineMate | FPS at the previous shutdown, restored as the startup FPS | No |
| fps_max | CineMate startup | Maximum FPS supported by the current sensor mode | No |
| fps_phase_lock | CineMate startup | Runtime enable for CinePi-raw's closed-loop frame-rate phase lock, from `sensors.<cam>.phase_lock` in settings.jsonc (default on); read once at CinePi-raw startup, not live | No |
| sensor_mode | CineMate -> CinePi-raw startup | Active sensor resolution/mode index | Yes (causes pipeline restart) |
| bit_depth | CineMate startup | Sensor bit depth (10, 12 or 16) for the selected mode | No |
| width / height | CineMate startup | Active sensor resolution | No |
| mode | CineMate startup | Composite `width:height:bit_depth:packing` string for the active sensor mode | No |
| packing | CineMate startup | Sensor packing token for the active mode/platform: `P` (packed) or `U` (unpacked) | No |
| lores_width / lores_height | CineMate startup | Preview stream resolution passed to CinePi-raw | No |

### Resolution switching

Whether triggered manually (`set resolution`) or automatically by dynamic resolution, a
resolution change publishes a target/in-flight state so the GUI can show a "switching"
transition instead of a stale value.

| Key | Written by | Description | Safe to change manually? |
|-----|------------|-------------|--------------------------|
| dynamic_resolution_enabled | CineMate | Toggle for automatic FPS-driven resolution downgrade/upgrade (`set dynamic resolution`); persisted and read back at startup, defaulting to on when unset | Yes |
| dynamic_resolution_active | CineMate | `1` while a lower resolution mode is currently substituted in to sustain the requested FPS | No |
| dynamic_resolution_desired_mode | CineMate | The sensor mode the user actually asked for; dynamic resolution switches away from and back to this mode as FPS allows | No |
| resolution_switching | CineMate | `1` while a resolution change (manual or dynamic) is in flight; cleared when CinePi-raw's raw-stream-ready log line reports the new stream at the target size, or after a 2.5 s hold timer | No |
| resolution_target_mode | CineMate | Sensor mode index CinePi-raw is being switched to | No |
| resolution_target_width / resolution_target_height | CineMate | Target resolution CinePi-raw's raw-stream-ready log line is matched against to clear `resolution_switching` | No |
| resolution_target_bit_depth | CineMate | Target bit depth for the in-flight resolution switch | No |
| wb | CineMate -> CinePi-raw | White-balance temperature in Kelvin | Yes |
| wb_user | CineMate | Kelvin value stored before conversion to `cg_rb` | No |
| cg_rb | CineMate -> CinePi-raw | White-balance gain pair `1/R,1/B` | Yes (advanced) |
| zoom | CineMate | Digital zoom factor for preview streams | Yes |
| hdmi_preview_source | CineMate -> CinePi-raw | Dual-sensor HDMI preview source: `both`, `cam0`, `cam1`, `pip_cam0`, or `pip_cam1`. Read live by the compositor; no restart | Yes |
| ir_filter | CineMate -> CinePi-raw | Toggle IR-cut filter (IMX585 only) | Yes |
| hdr | CineMate -> CinePi-raw startup | ClearHDR state (imx585): `1` makes CinePi-raw launch with `--hdr sensor`. Set automatically when a ClearHDR sensor mode is selected; changing it requires a camera restart | No (select an HDR mode via `set resolution`) |
| hdr_threshold_low | CineMate -> CinePi-raw | ClearHDR data-selection threshold, low side (0–4095). Applied live to the sensor (as a pair with `hdr_threshold_high`), and re-applied at every CinePi-raw start | Yes (publish key to apply) |
| hdr_threshold_high | CineMate -> CinePi-raw | ClearHDR data-selection threshold, high side (0–4095). Applied live to the sensor (as a pair with `hdr_threshold_low`), and re-applied at every CinePi-raw start | Yes (publish key to apply) |
| hdr_blend | CineMate -> CinePi-raw | ClearHDR HG/LG blending mode, driver menu 0–8 (0 = HG 1/2 + LG 1/2). Applied live | Yes (publish key to apply) |
| hdr_gain_adder | CineMate -> CinePi-raw | ClearHDR low-gain path gain adder, driver menu 0–5 (2 = +12 dB). Applied live | Yes (publish key to apply) |
| thumbnail | CineMate -> CinePi-raw | Embedded DNG thumbnail mode: `0` off, `1` mono, `2` colour. Applied live (no camera restart), written per frame into new takes only | Yes (publish key to apply) |
| thumbnail_size | CineMate -> CinePi-raw | Right-shift downscale of the thumbnail plane; `0` is the full lores size. Changing it restarts the camera. Seeded at launch only — no CLI verb or settings-editor field yet | No (seeded to avoid a stale pre-Phase-0 resident value collapsing the thumbnail; change by hand only if you understand the restart) |
| log_encode_request | CineMate | [CineMate Log](cinemate-log.md) request, shared across every launched camera like `hdr`: `0` off, `1` on (use the live mode's default target), `10` / `12` force that target. Set by `set log`; each camera resolves it independently against its own sensor at the next restart | No (use `set log`) |
| log_encode_cam0 / log_encode_cam1 | CinePi-raw (per camera) startup | The target that camera was actually **launched** with: `0` = off/not applied, else `10` or `12`. Drives the Simple GUI `LOG10`/`LOG12` badge — deliberately not the same as `log_encode_request`, so the badge never shows a target that isn't running yet | No |
| is_recording | CineMate -> CinePi-raw | Requested record state. Edge-triggered: `0 -> 1` starts, `1 -> 0` stops | Yes |
| record_cams | CineMate -> CinePi-raw | Dual-sensor record gate: which sensor(s) capture this take (`cam0+cam1`, `cam0`, or `cam1`). Published before `is_recording` flips; each `cinepi-raw` records only if its `--cam-port` is selected. Absent/empty = both | No |
| rec | CineMate (RedisListener) | Derived runtime record flag based on `framecount` rising/going flat | No |
| framecount | CinePi-raw -> CineMate | Total frames counted for the active take | No |
| buffer | CinePi-raw -> CineMate | Raw frames currently buffered in RAM | No |
| buffer_size | CinePi-raw -> CineMate | Total RAM buffer capacity in frames | No |
| is_buffering | CinePi-raw -> CineMate | `1` while the RAM buffer is pre-filling | No |
| is_writing | CinePi-raw -> CineMate | `1` while at least one camera is actively writing frames to disk | No |
| is_writing_buf | CineMate | `1` while buffered frames are still flushing after stop | No |
| storage_preroll_active | CineMate (StoragePreroll) | `1` during a storage warm-up clip | No |
| drop_frame | CineMate (RedisListener) | Live pulse while a TC-gap event is active (advisory — frame may still be on disk) | No |
| drop_frame_count | CineMate (RedisListener) | TC hole count in the current/last take (alias of `tc_hole_count`; kept for backward compatibility) | No |
| drop_frame_relay | CineMate (RedisListener) | Short pulse used to mute REC tone for one frame on drop-frame events | No |
| drop_frame_during_last_take | CineMate (RedisListener) | `1` only if the previous non-preroll take had frames genuinely absent from disk (`missing_frame_count > 0`) | No |
| tc_hole_count | CineMate (RedisListener) | Number of TC gap events this take — frames that arrived late enough to create a timecode hole (inter-frame gap ≥ 1.5× frame period); file may still be present | No |
| missing_frame_count | CineMate (RedisListener) | Frames confirmed absent from disk: `max(0, expected − recorded)` at end of take; authoritative signal for genuine data loss | No |
| frames_in_sync | CineMate (RedisListener) | `1` if live/final expected vs recorded frame counts are within configured sync tolerance; defaults are +/- 2 frames live and +/- 1 frame after buffered writes flush | No |
| recording_time | CineMate (RedisController timer) | Elapsed record time in seconds | No |
| recording_tc_rec | CineMate (RedisController timer) | Elapsed record timecode | No |
| recording_time_tod | CineMate (RedisController timer) | Time-of-day timecode updated during recording | No |
| tc_cam0 / tc_cam1 | CineMate (RedisListener) | SMPTE timecode per camera derived from `timestamp*` stats fields | No |
| last_dng_cam0 / last_dng_cam1 | CineMate (cinepi_multi log watcher) | Full path to the most recently written DNG for each camera | No |
| is_mounted | CineMate (SSD monitor) | `1` when storage is mounted | No |
| storage_type | CineMate (SSD monitor) | Drive type such as NVME, USB, or SD | No |
| storage_filesystem | CineMate (SSD monitor) | Current filesystem type such as `ext4`, `exfat`, or `ntfs` | No |
| storage_mount_options | CineMate (SSD monitor) | Actual mount options reported by the kernel for `/media/RAW` | No |
| storage_recorder_profile | CineMate (SSD monitor) | Recorder worker profile selected from the current filesystem | No |
| space_left | CineMate (SSD monitor) | Remaining free space in GB | No |
| write_speed_to_drive | CineMate (SSD monitor) | Current write speed in MB/s | No |
| FSCK_STATUS | CineMate (SSD monitor) | Result of the periodic filesystem check run after mount, e.g. `OK ...` / `FAIL ...`; cinemate-internal, cinepi-raw never reads it | No |
| file_size | CineMate | Bytes per frame for the current mode | No |
| memory_alert | CineMate | RAM percentage at which the watchdog auto-stopped recording (integer, set at the 80 % trip point); `0` when clear | No |
| cam_init | CinePi-raw | Internal startup flag | No |
| cameras | CineMate startup | JSON list of detected cameras and port assignments | No |
| audio_capture_gain_db | CineMate startup | Capture gain in dB applied to the active USB mic, from `audio_capture` in settings.jsonc (per-mic-type block, e.g. `16bit.capture_gain_db`); read back by the USB hotswap monitor on mic reconnect | No |
| trigger_mode | -- | Defined in `ParameterKey` but not currently written or read anywhere in CineMate or CinePi-raw | -- |
| gui_layout | CineMate | Path to the active GUI layout preset | No |
| pi_model | CineMate startup | Platform family, not the full board name: `pi5` (Pi 5 / 500 / CM5), `pi4` (Pi 4 / 400 / CM4), `other`, or `unknown` | No |
| sensor | CineMate startup | Active camera model key | No |
