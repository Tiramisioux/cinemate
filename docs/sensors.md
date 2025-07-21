# Compatible sensors 

| Sensor | Cinemate sensor mode | Resolution   | Aspect Ratio | Bit Depth | Max FPS* | File Size (MB) |
|--------|------|--------------|--------------|-----------|---------|----------------|
| IMX283 | 0    | 2736 x 1538  | 1.80         | 12        | 40      | 7.1            |
|        | 1    | 2736 x 1824  | 1.53         | 12        | 34      | 8.2            |
| IMX296 | 0    | 1456 x 1088  | 1.33         | 12        | 60      | 2              |
| IMX477 | 0    | 2028 x 1080  | 1.87         | 12        | 50      | 4.3            |
|        | 1    | 2028 x 1520  | 1.33         | 12        | 40      | 5.3            |
|        | 2    | 1332 x 990   | 1.34         | 10        | 120     | 2.7             |
| IMX585 | 0    | 1928 x 1090  | 1.77         | 12        | 87      | 4              |
|        | 1    | 3840 x 2160  | 1.77         | 12        | 34      | 4

Note that maximum fps will vary according to disk write speed. For the specific fps values for your setup, make test recordings and monitor the output. Purple background in the monitor/web browser indicates drop frames. From version 3.1 the resolution list is generated dynamically from `cinepi-raw --list-cameras`.

You can limit which modes appear inside CineMate by editing the `resolutions` section in `settings.json`. Only the K categories and bit depths you list will be shown. Custom driver modes can also be added here.