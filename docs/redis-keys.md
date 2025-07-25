# Redis key reference

This page lists all Redis keys used by Cinemate and CinePi-raw.  Values are simple strings so you can read or write them with `redis-cli`.

Each entry explains which component normally writes the key and what happens when you change it manually.

| Key | Written by | Description | Safe to change manually? |
|-----|------------|-------------|--------------------------|
| anamorphic_factor | Cinemate | Preview squeeze for anamorphic lenses | Yes (publish key to apply) |
| iso | Cinemate → CinePi-raw | Sensor gain in ISO | Yes |
| shutter_a | Cinemate → CinePi-raw | Actual shutter angle in degrees | Yes |
| shutter_angle_nom | Cinemate | Desired shutter angle before sync/free adjustments | Yes |
| shutter_a_sync_mode | Cinemate | Keep exposure constant when changing FPS | Yes |
| fps | Cinemate → CinePi-raw | Target frames per second | Yes |
| sensor_mode | Cinemate → CinePi-raw startup| Active sensor resolution/mode | Yes (causes pipeline restart) |
| wb | Cinemate → CinePi-raw | White‑balance temperature (Kelvin) | Yes |
| zoom | Cinemate | Digital zoom for preview streams | Yes |
| ir_filter | Cinemate → CinePi-raw | Toggle IR‑cut filter (IMX585 only) | Yes |
| rec / is_recording | Cinemate → CinePi-raw | Start/stop recording when toggled | Yes (edge‑triggered) |
| bit_depth | Cinemate → CinePi-raw startup| Sensor bit depth (10 or 12) | No (set at startup) |
| height / width | Cinemate → CinePi-raw startup | Active sensor resolution | No |
| lores_width / lores_height | CinePi-raw startup | Preview stream resolution | No |
| cg_rb | Cinemate → CinePi-raw | White‑balance gain pair "1/R,1/B" | Yes (advanced) |
| fps_user | Cinemate | Temporary storage for the UI slider | No |
| fps_last | Cinemate | Previous stable fps from stats | No |
| fps_actual | CinePi-raw → Cinemate | Measured FPS from pipeline | No |
| framecount | CinePi-raw → Cinemate | Total frames recorded | No |
| buffer | CinePi-raw → Cinemate | Raw frames currently in RAM | No |
| buffer_size | CinePi-raw  →  Cinemate| Size of RAM buffer in frames | No |
| is_buffering | CinePi-raw → Cinemate | 1 while buffer pre‑fills | No |
| is_writing | CinePi-raw → Cinemate | 1 while frames are flushing to disk | No |
| is_writing_buf | Cinemate | Internal countdown after recording stops | No |
| is_mounted | Cinemate (SSD monitor) | 1 when storage is mounted | No |
| storage_type | Cinemate (SSD monitor) | Drive type (NVME/USB/SD) | No |
| space_left | Cinemate (SSD monitor) | Remaining space in GB | No |
| write_speed_to_drive | Cinemate (SSD monitor) | Current write speed MB/s | No |
| file_size | Cinemate | Bytes per frame for current mode | No |
| last_dng_cam0/1 | CinePi-raw → Cinemate | Path to last written DNG frame | No |
| recording_time | Cinemate | HH:MM:SS:FF timer while recording | No |
| memory_alert | Cinemate | 1 if RAM usage high | No |
| cam_init | CinePi-raw | Internal flag during startup | No |
| cameras | CinePi-raw | JSON list of detected cameras | No |
| gui_layout | Cinemate | Path to GUI layout preset | No |
| pi_model | Cinemate | Raspberry Pi model string | No |
| sensor | CinePi-raw | Active camera model | No |
| tc_cam0/tc_cam1 | CinePi-raw → Cinemate | SMPTE time code per camera (derived from `timestamp*` fields) | No |
| shutter_angle_actual | Cinemate | Calculated shutter angle applied after clamping or sync | No |
| shutter_angle_transient | Cinemate | Temporary value during ramping | No |
| exposure_time | Cinemate | Current exposure time in seconds | No |
| wb_user | Cinemate | Kelvin value set before converting to cg_rb | No |
