# Troubleshooting

Common issues during a first build.

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| **No preview on the monitor** | No HDMI signal, or the browser UI never started | Plug in an HDMI monitor, **or** join the `CinePi` Wi-Fi and open `cinepi.local:5000`. The browser UI only starts if the Pi has a network address at boot — if you connect later, restart Cinemate. See [Web GUI](web-gui.md). |
| **Camera not detected** | Ribbon connected with power on, or wrong sensor overlay | Power off, reseat the ribbon, power on. Confirm the right sensor line is enabled in [config.txt](config-txt.md). |
| **Cinemate boots with a `NO CAM` badge, no preview** | No camera was found at boot (`camera-ready.sh` waits up to 8 s before giving up, so this isn't a slow-sensor false alarm) | Expected, not a crash. Both the HDMI GUI and the web GUI show `NO CAM` and stay usable — hotspot, web UI, and the settings editor at `http://cinepi.local:5000/settings-editor` are all still reachable, so you can fix `config.txt` or reseat the ribbon without SSH. Power off, reconnect the camera, power on, then run `restart cinemate` (CLI, serial, or the web GUI) — see [CLI commands](cli-commands.md). Recording and preview stay unavailable until then; `restart camera` alone does not re-detect a newly attached sensor. Note `restart cinemate` restarts the **`cinemate-autostart` service** — if you started Cinemate by hand (`python3 src/main.py`, or the `cinemate` alias), it will not restart the process you are looking at; stop that one and start it again yourself. |
| **Bare terminal after boot, no Cinemate error** | Cinemate never started. The systemd unit failed *before* `main.py` ran — almost always because `/etc/systemd/system/cinemate-autostart.service` is an old copy with the strict camera-ready gate, and a `git pull` does not update it | The unit and the `/usr/local/bin/` helpers are **copied** by `sudo make install`, not symlinked. Run `cd /home/pi/cinemate && sudo make install && sudo systemctl daemon-reload`, then reboot. Confirm with `grep ExecStartPre /etc/systemd/system/cinemate-autostart.service` — it must read `ExecStartPre=-/usr/local/bin/camera-ready.sh`, with the leading `-`. Distinguish this from a Python startup crash: a crash prints a red `Cinemate crashed during startup` block on `tty1` first; this failure prints nothing at all. See [Installation](installation-steps.md). |
| **Recording won't start / no storage** | Drive not labelled or formatted as expected | The drive must be formatted **exFAT, ext4 or NTFS** and labelled **RAW**, and mounted. See [Quick start](getting-started.md). |
| **Purple/magenta screen, frequent DROP** | Storage too slow for the current frame rate | Lower the FPS or use faster media (SSD, NVMe, or CFE Hat). See [Camera sensors and frame rates](sensors.md). |
| **Blue screen at startup or on inserting a drive** | Normal storage pre-roll (warm-up) | This is expected, not an error. To disable it, set `system.storage.auto_preroll` to `false`. See [Storage pre-roll warm-up](storage-preroll.md). |
| **Audio drifts out of sync on long takes** | Microphone clock drift | See [Audio sync & drift](audio-sync.md) for correction. |
| **Can't reach the Pi over SSH** | Hostname or network | Connect to `cinepi.local`. See [Connecting via SSH](ssh.md). |

!!! tip "Power down before changing hardware"

    Always power the Pi off before attaching or removing the camera ribbon or a hat. Hot-swapping can damage hardware.
