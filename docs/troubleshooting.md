# Troubleshooting

Common issues during a first build.

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| **No preview on the monitor** | No HDMI signal, or the browser UI never started | Plug in an HDMI monitor, **or** join the `CinePi` Wi-Fi and open `cinepi.local:5000`. The browser UI only starts if the Pi has a network address at boot — if you connect later, restart Cinemate. See [Web GUI](web-gui.md). |
| **Camera not detected** | Ribbon connected with power on, or wrong sensor overlay | Power off, reseat the ribbon, power on. Confirm the right sensor line is enabled in [config.txt](config-txt.md). |
| **Recording won't start / no storage** | Drive not labelled or formatted as expected | The drive must be formatted **exFAT, ext4 or NTFS** and labelled **RAW**, and mounted. See [Quick start](getting-started.md). |
| **Purple/magenta screen, frequent DROP** | Storage too slow for the current frame rate | Lower the FPS or use faster media (SSD, NVMe, or CFE Hat). See [Camera sensors and frame rates](sensors.md). |
| **Blue screen at startup or on inserting a drive** | Normal storage pre-roll (warm-up) | This is expected, not an error. To disable it, set `"auto_storage_preroll": false`. See [Storage pre-roll warm-up](storage-preroll.md). |
| **Audio drifts out of sync on long takes** | Microphone clock drift | See [Audio sync & drift](audio-sync.md) for correction. |
| **Can't reach the Pi over SSH** | Hostname or network | Connect to `cinepi.local`. See [Connecting via SSH](ssh.md). |

!!! tip "Power down before changing hardware"

    Always power the Pi off before attaching or removing the camera ribbon or a hat. Hot-swapping can damage hardware.
