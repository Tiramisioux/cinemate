## Compatible sensors 

### IMX477 (Raspberry Pi HQ Camera)

| Mode | Resolution       | Aspect Ratio | Bit Depth | Max FPS | DNG Frame File Size (MB) |
|------|------------------|--------------|-----------|---------|----------------|
| 0    | 2028 x 1080      | 1.87         | 12        | 50      | 4.3            |
| 1    | 2028 x 1520      | 1.33         | 12        | 40      | 5.3            |
| 2    | 1332 x 990       | 1.34         | 10        | 120     | 2.7            |

### IMX296 (Raspberry Pi Global Shutter Camera)

| Mode | Resolution       | Aspect Ratio | Bit Depth | Max FPS | DNG Frame File Size (MB) |
|------|------------------|--------------|-----------|---------|----------------|
| 0    | 1456 x 1088      | 1.33         | 10        | 60      | 3.1            |

### IMX585 (Starlight Eye)

| Mode | Resolution       | Aspect Ratio | Bit Depth | Max FPS | DNG Frame File Size (MB) |
|------|------------------|--------------|-----------|---------|----------------|
| 0    | 1928 x 1090      | 1.77         | 12        | 87      | 4.0            |
| 1    | 3840 x 2160      | 1.77         | 12        | 34      | 4.0            |

### IMX283 (OneInchEye)

| Mode | Resolution       | Aspect Ratio | Bit Depth | Max FPS | DNG Frame File Size (MB) |
|------|------------------|--------------|-----------|---------|----------------|
| 0    | 2736 x 1538      | 1.80         | 12        | 40      | 7.1            |
| 1    | 2736 x 1824      | 1.53         | 12        | 34      | 8.2            |

Note that maximum fps will vary according to disk write speed. For the specific fps values for your setup, make test recordings and monitor the output. Purple background in the monitor/web browser indicates drop frames.

You can limit which modes appear inside CineMate by editing the `resolutions` section in `settings.json`. `k_steps` are approximate resolution steps. Custom driver modes can also be added here.

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

!!! note ""

    On Raspberry Pi 4 / Pi 400 / CM4, Cinemate launches IMX296 as `1456:1088:10:P` so CinePi-RAW receives the Pi 4 VC4 packed raw stream. On Raspberry Pi 5 / CM5 it uses `1456:1088:10:U`.

## Sustainable frame rates

For continouos recording without the system utilizing the frame buffer and with no drop frames. Performance will depend on sensor and storage media. Here are measured results.

### IMX477

| Resolution         | Bit Depth | Storage          | Sustainable FPS  |
|--------------------|-----------|------------------|------|
| 2028 x 1080        | 12 bit    | SSD (Samsung T7) | 34   |
| 2028 x 1520        | 12 bit    | SSD (Samsung T7) | 24   |
| 1332 x 990         | 12 bit    | SSD (Samsung T7) | 71   |
| 2028 x 1080        | 12 bit    | CFE Hat / NVMe   | 50   |
| 2028 x 1520        | 12 bit    | CFE Hat / NVMe   | 40   |
| 1332 x 990         | 12 bit    | CFE Hat / NVMe   | 119  |

### IMX585

| Resolution         | Bit Depth | Storage          | Sustainable FPS  |
|--------------------|-----------|------------------|------|
| 1928 x 1090        | 12 bit    | SSD (Samsung T7) | 33   |
| 3856 x 2180        | 12 bit    | SSD (Samsung T7) | 10   |
| 1928 x 1090        | 12 bit    | CFE Hat / NVMe   | 87   |
| 3856 x 2180        | 12 bit    | CFE Hat / NVMe   | 43   |

!!! note ""

    Note that the frame buffer is occationally used, especially for SSD drives, due to occational drop in write speed.
