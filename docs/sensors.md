## Compatible sensors 

### IMX477 (Raspberry Pi HQ Camera)

| Mode | Resolution       | Aspect Ratio | Bit Depth | Max FPS | Sustainable FPS* | DNG Frame File Size (MB) |
|------|------------------|--------------|-----------|---------|------------------|--------------------------|
| 0    | 2028 x 1080      | 1.87         | 12        | 50      | -                | 4.3                      |
| 1    | 2028 x 1520      | 1.33         | 12        | 40      | -                | 5.3                      |
| 2    | 1332 x 990       | 1.34         | 10        | 120     | -                | 2.7                      |

### IMX296 (Raspberry Pi Global Shutter Camera)

| Mode | Resolution       | Aspect Ratio | Bit Depth | Max FPS | Sustainable FPS* | DNG Frame File Size (MB) |
|------|------------------|--------------|-----------|---------|------------------|--------------------------|
| 0    | 1456 x 1088      | 1.33         | 10        | 60      | -                | 3.1                      |

### IMX585 (Starlight Eye)

| Mode | Resolution       | Aspect Ratio | Bit Depth | Max FPS | Sustainable FPS* | DNG Frame File Size (MB) |
|------|------------------|--------------|-----------|---------|------------------|--------------------------|
| 0    | 1928 x 1090      | 1.77         | 12        | 87      | 50 on CFE/NVMe ext4/exFAT and SSD ext4/exFAT | 4.0 |
| 1    | 3856 x 2180      | 1.77         | 12        | 40      | 40 on CFE/NVMe ext4; 38 on CFE/NVMe exFAT; 25 on SSD ext4/exFAT | 10.0 |

### IMX283 (OneInchEye)

| Mode | Resolution       | Aspect Ratio | Bit Depth | Max FPS | Sustainable FPS* | DNG Frame File Size (MB) |
|------|------------------|--------------|-----------|---------|------------------|--------------------------|
| 0    | 2736 x 1538      | 1.80         | 12        | 40      | -                | 7.1                      |
| 1    | 2736 x 1824      | 1.53         | 12        | 34      | -                | 8.2                      |

*Sustainable FPS means the empirically observed frame rate that records without dropped frames on the listed storage and filesystem.*

Note that maximum fps will vary according to disk write speed. For the specific fps values for your setup, make test recordings and monitor the output. Purple background in the monitor/web browser indicates drop frames.

You can limit which modes appear inside CineMate by editing the `resolutions` section in `settings.json`. `k_steps` are the approximate recording-size choices shown in the UI. The stock Cinemate defaults show only 1.5K and 2K because 2K is the standard working size and the default list is kept to modes suitable for 25 fps recording. Higher modes are supported when the user opts in.

```json
"resolutions": {
  "k_steps": [1.5, 2, 4],
  "bit_depths": [10, 12],
  "custom_modes": {
    "imx283": [
      {"width": 3936, "height": 2176, "bit_depth": 12, "fps_max": 24}
    ]
  }
}
```

!!! note ""

    The bit-depth column above describes the sensor mode reported by the camera stack. The IMX296 sensor mode is 10 bit. Cinemate's CinePi-RAW DNG writer may still save captures through its 12 bit DNG output path, so a correctly saved IMX296 DNG does not mean the sensor itself has a 12 bit mode.

!!! info "Raspberry Pi 4 raw packing"

    Cinemate handles the CinePi-RAW packing choice automatically. On Raspberry Pi 4 / Pi 400 / CM4, IMX296 and IMX477 use packed raw mode (`P`). On Raspberry Pi 5 / CM5 they stay on unpacked mode (`U`). For IMX296 this means `1456:1088:10:P` on Raspberry Pi 4-family boards and `1456:1088:10:U` on Raspberry Pi 5 / CM5.

## Sustainable frame rates

These rows are measured sustainable limits: continuous recording without dropped frames. Performance depends on the sensor, storage device, and filesystem. Cinemate loads the stock dynamic-resolution rows from `resources/dynamic_resolution_profiles.json`, and the sensor compatibility metadata lives in `resources/sensors.json`.

| Sensor | Resolution | Bit Depth | Storage | Filesystem | Sustainable FPS |
|--------|------------|-----------|---------|------------|-----------------|
| IMX477 | 2028 x 1080 | 12 bit | SSD (Samsung T7) | ext4 | 34 |
| IMX477 | 2028 x 1520 | 12 bit | SSD (Samsung T7) | ext4 | 24 |
| IMX477 | 1332 x 990 | 12 bit | SSD (Samsung T7) | ext4 | 71 |
| IMX477 | 2028 x 1080 | 12 bit | CFE Hat / NVMe | ext4 | 50 |
| IMX477 | 2028 x 1520 | 12 bit | CFE Hat / NVMe | ext4 | 40 |
| IMX477 | 1332 x 990 | 12 bit | CFE Hat / NVMe | ext4 | 119 |
| IMX585 | 1928 x 1090 | 12 bit | CFE Hat / NVMe | exFAT | 50 |
| IMX585 | 1928 x 1090 | 12 bit | CFE Hat / NVMe | ext4 | 50 |
| IMX585 | 3856 x 2180 | 12 bit | CFE Hat / NVMe | exFAT | 38 |
| IMX585 | 3856 x 2180 | 12 bit | CFE Hat / NVMe | ext4 | 40 |
| IMX585 | 1928 x 1090 | 12 bit | SSD | exFAT | 50 |
| IMX585 | 1928 x 1090 | 12 bit | SSD | ext4 | 50 |
| IMX585 | 3856 x 2180 | 12 bit | SSD | exFAT | 25 |
| IMX585 | 3856 x 2180 | 12 bit | SSD | ext4 | 25 |

Missing rows are intentionally inert in dynamic resolution mode: if the detected sensor, storage type, filesystem, desired resolution, or requested FPS is not represented by measured data, Cinemate leaves the current resolution unchanged.

### Dynamic resolution

When `dynamic_resolution.enabled` is `true`, Cinemate remembers the resolution the user selected as the desired mode. If the user raises FPS above that desired mode's measured sustainable limit, Cinemate switches to the highest measured mode that can sustain the requested FPS. If the user lowers FPS back to the desired mode's measured limit or below, Cinemate switches back.

Example: with IMX585, CFE Hat, ext4, and desired 3856 x 2180, the table limit is 40 fps. At 40 fps Cinemate keeps 3856 x 2180. Above 40 fps it switches to 1928 x 1090 because that row is measured up to 50 fps.

While dynamic resolution is enabled, Cinemate also uses the measured profile to set the maximum FPS exposed to controls and free-mode stepping. If the desired mode has no matching measured row, Cinemate keeps the normal sensor-readout FPS maximum instead. When dynamic resolution is disabled, the maximum FPS always comes from the sensor readout reported by `cinepi-raw`.

The active resolution numbers turn green in the simple GUI when Cinemate is currently using a lower measured mode than the user's desired mode.

### Measuring your own rows

1. Format the RAW media with the filesystem you want to test, for example `ext4` or `exfat`, and mount it as the normal RAW drive.
2. Select one sensor mode and one FPS value.
3. Record a long enough take to expose sustained write behavior, not just startup behavior.
4. Watch the HDMI/browser GUI and logs. A purple `DROP` alert means the FPS is above the sustainable limit for that setup.
5. Repeat until you find the highest FPS that records continuously with no dropped frames. If the buffer fills temporarily but catches up, note that in the row.
6. Add or update one row in `resources/dynamic_resolution_profiles.json` with the sensor, storage type, filesystem, resolution, bit depth, and sustainable FPS.

Each row should include:

| Field | Meaning |
|-------|---------|
| `sensor` | Sensor id, for example `imx585`. |
| `sensor_aliases` | Optional compatible sensor names, for example `["imx585_mono"]`. |
| `storage_type` | Storage class detected by Cinemate, for example `ssd`, `cfe`, or `nvme`. |
| `filesystem` | Filesystem of the mounted RAW media, for example `ext4` or `exfat`. |
| `media_model` | Human-readable device name used for documentation. |
| `width`, `height`, `bit_depth` | Measured recording mode. Nearby driver modes are matched using `match_tolerance_px`. |
| `sustainable_fps` | Highest FPS that recorded without dropped frames. |
| `max_fps_no_buffer` | Optional stricter value for rows where you have also verified no buffer growth. |
| `test_duration_seconds` | Test duration, if recorded. |
| `buffer_peak_frames`, `drop_frames` | Evidence from the test run. |
| `confidence` | Suggested values are `empirical`, `documented`, or `observed`. |
| `notes` | Short context for future users. |

### Self-correcting observations

Cinemate can also learn local limits from real takes. Set `dynamic_resolution.learning.enabled` to `true` to let Cinemate observe buffer and drop-frame behavior while recording. After a take stops, Cinemate writes stable or failed observations to `src/dynamic_resolution_observed_profiles.json`.

Observed rows do not affect resolution switching until you opt in:

```json
"dynamic_resolution": {
  "enabled": true,
  "use_observed_profile": true,
  "learning": {
    "enabled": true
  }
}
```

This keeps the standard profile as the default and lets the operator decide when the locally learned rows should override it.

!!! note ""

    Occasional write-speed dips are most common on SSDs. Use conservative values in the lookup table; dynamic resolution is meant to prevent buffering, not to chase best-case burst performance.
