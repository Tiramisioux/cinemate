# Changelog

Release notes for Cinemate. For downloads, see the [releases page](https://github.com/Tiramisioux/cinemate/releases).

## Version 3.3.2

### Dual sensors

- **Automatic dual-camera** — two connected sensors are each detected and driven by their own genlocked `cinepi-raw` process (cam0 server, cam1 client).
- **HDMI preview switching** — new command `set preview` cycles side-by-side → cam0 → cam1 → pip_cam0 → pip_cam1 (picture-in-picture).
- **Per-sensor recording** — record both sensors or just the previewed one (`sensors.record_policy` can be set in settings.jsonc), or target sensors with `rec cam0` / `rec cam1` / `rec both`. Each sensor writes its own `..._cam0` / `..._cam1` clip folder.

### libcamera

- Cinemate now uses its own fork of libcamera.

### imx283 driver

- Cinemate now uses its own fork of the imx283 driver.
- 2 additional modes: 3840 x 2160 (4K UHD, native crop) and 2736 x 1538 (2.7K 16:9, binned).

### imx585 driver

- Cinemate now uses its own fork of the imx585 driver.

### ClearHDR (imx585)

- **16-bit ClearHDR recording** — the imx585's on-sensor single-frame HDR is now a first-class mode: Cinemate probes the sensor with and without `--hdr sensor` and lists the plain and ClearHDR modes (12-bit and 16-bit) in one mode table. Selecting an HDR mode relaunches cinepi-raw with the flag; `HDR` labels mark the modes in both GUIs. See [ClearHDR](clear-hdr.md).
- **Live merge knobs** — `set hdr threshold low/high`, `set hdr blend`, `set hdr gain adder` tune the sensor's HG/LG merge while streaming; startup defaults live in `image_capture.hdr` and the knobs can be mapped to pots and encoders.
- **RP1 overclock, automated** — the installer compiles the `rp1-overclock` overlay, ships it disabled (`#dtoverlay=rp1-overclock` in config.txt), and the settings editor's Boot config pane toggles it for higher ClearHDR frame rates on Pi 5 / CM5. See [Overclocking the Pi](overclocking.md).

### CinePi-RAW recorder

- **Frame-rate phase lock** — DNG timecode and frame capture is locked to the Pi's wall clock, making audio sync more accurate.
- **More reliable audio sync on 4K / exFAT** — the capture path was reworked (protected helper, dedicated writer thread, wall-clock reconciliation, real-time scheduling) for more reliable WAV sync on demanding modes.
- **Correct Pi 4 RAW** — CSI2-packed frames decode correctly on Pi 4-family boards; raw packing (P/U) is chosen per Pi model automatically.
- **Camera model** — set the camera model manually for each attached sensor.
- **`--keep16` removed** — SDR sensor modes always write 12-bit DNGs. The flag only preserved 4 padding bits, so files are ~33% smaller with no loss of information. True 16-bit modes (IMX585 ClearHDR) are unaffected.

### CineMate Log

- **New, opt-in log-companded DNG recording** on IMX585 and IMX283 — log-compands the linear sensor signal to a smaller code depth and writes a DNG `LinearizationTable` so any DNG app decodes it back to linear automatically. No LUT is needed or should be applied. Shrinks 16-bit ClearHDR frames 17–37% and 12-bit SDR frames ~17%. See [CineMate Log](cinemate-log.md).
- **Per-camera `log_encode` setting** (`false` / `true` / `10` / `12`) and the live `set log` command, both resolved against each camera's own live sensor mode — never a standing choice that can silently drift out of sync with a resolution or ClearHDR switch.
- **`LOG10`/`LOG12` badge** on the Simple GUI, per camera, reflecting what's actually running rather than what was requested.

### Cinemate

- **Storage / media** — multi-drive RAW hot-swap with a standby drive and automatic promotion. Default format is exFAT.
- **Settings editor** — a browser settings page at `cinepi.local:5000/settings-editor`: edit `settings.jsonc` panel by panel, stage `/boot/firmware/config.txt` changes (RP1 overclock toggle, link frequency), and browse, download or format the RAW drive from the RAW files pane.
- **Recovery console** — a new, independent `cinemate-recovery.service` on `:8080` lets you diagnose a Cinemate that will not start, edit `settings.jsonc` and `/boot/firmware/config.txt`, and restart Cinemate — from a phone on the hotspot, with no laptop or SSH. Standard library only, runs as root, and has no dependency on `cinemate-autostart.service` so it survives a crash that takes Cinemate down. The hotspot's Wi-Fi profile now also autoconnects at boot and self-heals a broken `settings.jsonc` by falling back to the last-known-good SSID rather than the compiled-in `CinePi` default. See [Recovery console](recovery-console.md).

### Web API

- **New wireless control API** over the Wi-Fi hotspot — ESP32, Pico W, other Pis and phones can now send the same commands as the CLI/serial over HTTP (`POST /api/v1/cmd`), read live status (`/api/v1/get/<key>`, `/api/v1/status`), and receive push updates via a UDP status broadcast (`8888/udp`) or SSE (`/api/v1/events`). One dispatcher (`CommandExecutor.handle_received_data`) now serves the CLI, serial and web paths identically. `allow_destructive` defaults to `false`, so `reboot`/`shutdown`/`erase`/`format` are blocked out of the box on a stock unit. See [Web API](web-api.md) and [Building control units](building-control-units.md).

### Raspberry Pi / Bookworm

- **Boot / install** — faster boot-to-preview on Pi 4/5 (about 10-15 seconds).

## Version 3.3.1

### CinePi-RAW recorder

- New Cinemate fork, reducing CPU load and temperature dramatically and reducing dropped frames.
- Resolution can now be changed without restarting the recorder process, enabling faster mode changes and dynamic resolution switching.
- Better USB microphone sync.

### Cinemate workflow

- exFAT support and filesystem-aware storage profiles for efficient media writes, including IMX585 25 fps at 4K to SSD without frame drops.
- Dynamic resolution switching to match the observed sustainable frame rate for the attached sensor and storage media — for example, IMX585 automatically switches to HD above 25 fps when an SSD is used.
- Hot-swapping between 16-bit and 24-bit USB microphones.
- 4K-class recording modes are visible by default.
- Automatic storage pre-roll can be disabled in `settings.jsonc`.
