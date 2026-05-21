# Redis key reference

This page lists the Redis keys used by Cinemate and CinePi-raw. Values are simple strings, so you can inspect them with `redis-cli`.

Each entry explains which component normally writes the key and whether it makes sense to change it manually.

| Key | Written by | Description | Safe to change manually? |
|-----|------------|-------------|--------------------------|
| anamorphic_factor | Cinemate | Preview squeeze factor for anamorphic lenses | Yes (publish key to apply) |
| iso | Cinemate -> CinePi-raw | Sensor gain in ISO | Yes |
| shutter_a | Cinemate -> CinePi-raw | Active shutter angle in degrees | Yes |
| shutter_angle_nom | Cinemate | Nominal shutter angle before sync/free-mode adjustments | Yes |
| shutter_a_sync_mode | Cinemate | Keep exposure constant when changing FPS | Yes |
| shutter_angle_actual | Cinemate | Calculated shutter angle actually applied after clamping/sync | No |
| shutter_angle_transient | Cinemate | Temporary value used during ramps | No |
| exposure_time | Cinemate | Current exposure time in seconds | No |
| fps | Cinemate -> CinePi-raw | Target frames per second | Yes |
| fps_user | Cinemate | User-selected FPS value stored by the UI/controller | No |
| fps_actual | CinePi-raw -> Cinemate | Measured FPS from the running pipeline | No |
| fps_last | Cinemate | Previous stable FPS value from stats | No |
| fps_max | Cinemate startup | Maximum FPS supported by the current sensor mode | No |
| fps_correction_suggestion | Cinemate (RedisListener) | Suggested correction factor after comparing expected vs recorded frame counts | No |
| sensor_mode | Cinemate -> CinePi-raw startup | Active sensor resolution/mode index | Yes (causes pipeline restart) |
| bit_depth | Cinemate startup | Sensor bit depth (10 or 12) for the selected mode | No |
| width / height | Cinemate startup | Active sensor resolution | No |
| lores_width / lores_height | Cinemate startup | Preview stream resolution passed to CinePi-raw | No |
| wb | Cinemate -> CinePi-raw | White-balance temperature in Kelvin | Yes |
| wb_user | Cinemate | Kelvin value stored before conversion to `cg_rb` | No |
| cg_rb | Cinemate -> CinePi-raw | White-balance gain pair `1/R,1/B` | Yes (advanced) |
| zoom | Cinemate | Digital zoom factor for preview streams | Yes |
| ir_filter | Cinemate -> CinePi-raw | Toggle IR-cut filter (IMX585 only) | Yes |
| is_recording | Cinemate -> CinePi-raw | Requested record state. Edge-triggered: `0 -> 1` starts, `1 -> 0` stops | Yes |
| rec | Cinemate (RedisListener) | Derived runtime record flag based on `framecount` rising/going flat | No |
| framecount | CinePi-raw -> Cinemate | Total frames counted for the active take | No |
| buffer | CinePi-raw -> Cinemate | Raw frames currently buffered in RAM | No |
| buffer_size | CinePi-raw -> Cinemate | Total RAM buffer capacity in frames | No |
| is_buffering | CinePi-raw -> Cinemate | `1` while the RAM buffer is pre-filling | No |
| is_writing | CinePi-raw -> Cinemate | `1` while at least one camera is actively writing frames to disk | No |
| is_writing_buf | Cinemate | `1` while buffered frames are still flushing after stop | No |
| storage_preroll_active | Cinemate (StoragePreroll) | `1` during the automatic storage warm-up clip | No |
| drop_frame | Cinemate (RedisListener) | Live drop-frame pulse while the alert is active | No |
| drop_frame_count | Cinemate (RedisListener) | Number of drop-frame detections in the current/last take | No |
| drop_frame_relay | Cinemate (RedisListener) | Short pulse used to mute REC tone for one frame on drop-frame events | No |
| drop_frame_during_last_take | Cinemate (RedisListener) | `1` if the previous non-preroll take had drop frames | No |
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
| file_size | Cinemate | Bytes per frame for the current mode | No |
| memory_alert | Cinemate | `1` if RAM usage is high | No |
| cam_init | CinePi-raw | Internal startup flag | No |
| cameras | Cinemate startup | JSON list of detected cameras and port assignments | No |
| gui_layout | Cinemate | Path to the active GUI layout preset | No |
| pi_model | Cinemate | Raspberry Pi model string | No |
| sensor | Cinemate startup | Active camera model key | No |
