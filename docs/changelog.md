# Changelog

Release notes for CineMate. For downloads, see the [releases page](https://github.com/Tiramisioux/cinemate/releases).

## Version 3.4.0

### imx585 driver

- **Default branch moves to `cinemate-7modes`**.

| CineMate mode | Type     | Resolution | Bit depth | Readout   | Max fps (normal) | Max fps (overclocked) | Notes               |
| ------------- | -------- | ---------- | --------- | --------- | ---------------- | --------------------- | ------------------- |
| 0             | SDR      | 3840×2160  | 10-bit    | all-pixel | 44.98            | 68.66                 | RAW10, up to 90 fps |
| 1             | SDR      | 1920×1080  | 12-bit    | binned    | 69.92            | 69.92                 |                     |
| 2             | SDR      | 3840×2160  | 12-bit    | all-pixel | 43.98            | 67.13                 |                     |
| 3             | ClearHDR | 1920×1080  | 12-bit    | binned    | 30.00            | 30.00                 | ClearHDR+CCMP       |
| 4             | ClearHDR | 3840×2160  | 12-bit    | all-pixel | 21.99            | 30.00                 | ClearHDR+CCMP       |
| 5             | ClearHDR | 1920×1100  | 16-bit    | binned    | 30.00            | 30.00                 | ClearHDR linear     |
| 6             | ClearHDR | 3840×2200  | 16-bit    | all-pixel | 21.99            | 30.00                 | ClearHDR linear     |

Max fps figures are measured at the sensor's highest supported link frequency, **1039.5 MHz (2079 Mbps/lane, 39% over the RP1 D-PHY spec ceiling)** — "normal" is the RP1 stock pixel-rate ceiling (`--max-pixel-rate 380`), "overclocked" is with the `rp1-overclock` dtoverlay's pixel-rate ceiling (`--max-pixel-rate 580`). See [Overclocking the Pi](overclocking.md).

- **12/16-bit ClearHDR recording** — See [ClearHDR](clear-hdr.md).

### RP1 overclock

- **Pixel-rate ceiling is now computed, not hardcoded** — CineMate derives it from the RP1 overclock toggle's state and passes it to cinepi-raw as `--max-pixel-rate`. See [Overclocking the Pi](overclocking.md).
- **Automated overlay** — the installer compiles the `rp1-overclock` overlay, ships it disabled by default; the settings editor's Boot config pane toggles it for higher ClearHDR frame rates on Pi 5 / CM5.
- **libcamera tuning fix** — `minPixelProcessingTime` adjusted so the overclock toggle actually raises the achievable frame rate.

### CineMate Log

- **New, opt-in log-companded DNG recording** on IMX585 and IMX283 — log-compands the linear sensor signal to a smaller code depth and writes a DNG `LinearizationTable` so any DNG app decodes it back to linear automatically. No LUT is needed or should be applied. Shrinks 16-bit ClearHDR frames 17–37% and 12-bit SDR frames ~17%. See [CineMate Log](cinemate-log.md).
- **Per-camera `log_encode` setting** (`false` / `true` / `10` / `12`) and the live `set log` command, both resolved against each camera's own live sensor mode — never a standing choice that can silently drift out of sync with a resolution or ClearHDR switch.
- **`LOG10`/`LOG12` badge** on the Simple GUI, per camera, reflecting what's actually running rather than what was requested.

### CineMate

#### Dual sensors

- **Automatic dual-camera** — two connected sensors are each detected and driven by their own `cinepi-raw` process, with frame capture synchronised by libcamera (cam0 server, cam1 client).
- **HDMI preview switching** — new command `set preview` cycles side-by-side → cam0 → cam1 → pip_cam0 → pip_cam1 (picture-in-picture).
- **Per-sensor recording** — record both sensors or just the previewed one (`sensors.record_policy` can be set in settings.jsonc), or target sensors with `rec cam0` / `rec cam1` / `rec both`. Each sensor writes its own `..._cam0` / `..._cam1` clip folder.
#### Web GUI

- **Settings editor config.txt write fix, `cinepi.local` mDNS** — saving `config.txt` used to fail silently (`EACCES`, runs as `pi`); now goes through a scoped helper (`cinemate-apply-config-txt`) that preserves owner/mode. Installer also enables mDNS for `cinepi.local` and fixes a stale `/etc/hosts` entry.
- **Settings editor** — browser page at `cinepi.local:5000/settings-editor`: edit `settings.jsonc`, stage `config.txt`, watch the live feed, review a take, manage the RAW drive. `config.txt` saves write and reboot immediately with no confirm/revert net — use the recovery console for that. See [Settings editor](settings-editor.md).
- **Playback** — new tab plays a take back in-browser at its conform rate, using the DNG thumbnails. See [Playback](playback.md).
- **Recovery console** — independent `cinemate-recovery.service` on `:8080`: diagnose, edit `settings.jsonc`/`config.txt`, and restart CineMate from a phone on the hotspot, no `cinemate-autostart.service` dependency. Hotspot Wi-Fi now self-heals a broken `settings.jsonc` via the last-known-good SSID. See [Recovery console](recovery-console.md).
- **Storage** — new `hw_write_failures` counter warns live on slow storage; NTFS flagged supported but not recommended (can drop frames under sustained 4K writes).

#### CineMate start also without attached camera 

- Web UI and settings editor stay reachable so user settings can be changed also with no camera attached. CineMate re-probes for the sensor on every start.
#### Web API

- **New wireless control API** over the Wi-Fi hotspot — ESP32, Pico W, other Pis and phones can now send the same commands as the CLI/serial over HTTP (`POST /api/v1/cmd`), read live status (`/api/v1/get/<key>`, `/api/v1/status`), and receive push updates via a UDP status broadcast (`8888/udp`) or SSE (`/api/v1/events`). One dispatcher (`CommandExecutor.handle_received_data`) now serves the CLI, serial and web paths identically. `allow_destructive` defaults to `false`, so `reboot`/`shutdown`/`erase`/`format` are blocked out of the box on a stock unit. See [Web API](web-api.md) and [Building control units](building-control-units.md).

### Raspberry Pi / Bookworm

- **Installer** — no longer creates a Python virtualenv; packages install straight into system Python (`cinemate-autostart.service` now launches `python3` directly), fixing several install blockers that only appeared in the venv path.

## Version 3.3.2

### libcamera

- CineMate now uses its own fork of libcamera.

### imx283 driver

- CineMate now uses its own fork of imx283 driver.
- 2 additional modes: 3840 x 2160 (4K UHD, native crop) and 2736 x 1538 (2.7K 16:9, binned) 

### imx585 driver

- CineMate now uses its own fork of imx283 driver.

### CinePi-RAW recorder

- **Frame-rate phase lock** — closed-loop control (sigma-delta VBLANK dither) keeps long takes locked to the Pi's wall clock and pre-converges during preview. On by default.
- **More reliable audio sync on 4K / exFAT** — the capture path was reworked (protected helper, dedicated writer thread, wall-clock reconciliation, real-time scheduling) for more reliable WAV sync on demanding modes.
- **Wall clock embedded timecode** — timecode is anchored to the first frame's wall-clock time and follows the Pi's real-time clock.
- **Correct Pi 4 RAW** — CSI2-packed frames decode correctly on Pi 4-family boards; raw packing (P/U) is chosen per Pi model automatically.
- **Camera model** — set the camera model manually for each attached sensor.

### CineMate

- **Storage / media** — multi-drive RAW hot-swap with a standby drive and automatic promotion. Default format is exFAT.

### Raspberry Pi / Bookworm**
- **Boot / install** — faster boot-to-preview on Pi 4/5 (about 10-15 seconds)

## Version 3.3.1

### CinePi-RAW recorder

- New CineMate fork, reducing CPU load and temperature dramatically and reducing dropped frames.
- Resolution can now be changed without restarting the recorder process, enabling faster mode changes and dynamic resolution switching.
- Better USB microphone sync.

### CineMate workflow

- exFAT support and filesystem-aware storage profiles for efficient media writes, including IMX585 25 fps at 4K to SSD without frame drops.
- Dynamic resolution switching to match the observed sustainable frame rate for the attached sensor and storage media — for example, IMX585 automatically switches to HD above 25 fps when an SSD is used.
- Hot-swapping between 16-bit and 24-bit USB microphones.
- 4K-class recording modes are visible by default.
- Automatic storage pre-roll can be disabled in `settings.jsonc`.
