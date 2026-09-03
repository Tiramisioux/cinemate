# Changelog

Release notes for Cinemate. For downloads, see the [releases page](https://github.com/Tiramisioux/cinemate/releases).

## Version 3.4.0

### Dual sensors

- **Automatic dual-camera** — two connected sensors are each detected and driven by their own `cinepi-raw` process, with frame capture synchronised by libcamera (cam0 server, cam1 client).
- **HDMI preview switching** — new command `set preview` cycles side-by-side → cam0 → cam1 → pip_cam0 → pip_cam1 (picture-in-picture).
- **Per-sensor recording** — record both sensors or just the previewed one (`sensors.record_policy` can be set in settings.jsonc), or target sensors with `rec cam0` / `rec cam1` / `rec both`. Each sensor writes its own `..._cam0` / `..._cam1` clip folder.

### imx585 driver

- **Default branch moves to `cinemate-7modes`**, replacing `innomaker-v1.0`. Seven modes total — three SDR (1920×1080 12-bit binned, 3840×2160 12-bit all-pixel, and a 3840×2160 10-bit RAW10 all-pixel mode, up to 90 fps) and four ClearHDR (1920×1080 12-bit binned ClearHDR+CCMP, 3840×2160 12-bit all-pixel ClearHDR+CCMP, 1920×1100 16-bit binned ClearHDR linear, and 3840×2200 16-bit all-pixel ClearHDR linear) — restoring the two binned-HDR modes `6.12.y` had and `innomaker-v1.0` dropped (both colour-sensor only), on top of `innomaker-v1.0`'s RAW10 mode and its dedicated 16-bit entry. Also makes 12-bit CCMP ClearHDR default-on for colour sensors. Verified on hardware. The old `6.12.y` and `innomaker-v1.0` branches stay selectable via `IMX585_DRIVER_REPO_REF` but are no longer the supported default.

### ClearHDR (imx585)

- **16-bit ClearHDR recording** — the imx585's on-sensor single-frame HDR is now a first-class mode: Cinemate probes the sensor with and without `--hdr sensor` and lists the plain and ClearHDR modes (12-bit and 16-bit) in one mode table. Selecting an HDR mode relaunches cinepi-raw with the flag; `HDR` labels mark the modes in both GUIs. See [ClearHDR](clear-hdr.md).
- **12-bit CCMP ClearHDR, and mono-sensor support** — the imx585's on-sensor HDR is also exposed at 12-bit (CCMP) alongside the 16-bit mode, in the same mode table. Verified working on the mono sensor (`imx585_mono`) as of 2026-08-27: a stock 6.12.y kernel gives every Bayer 16-bit format an RP1 workaround that misses mono's `Y16` entry, recording PiSP-COMP1-structured garbage unless patched (`scripts/patch-rp1-cfe.sh`, applied automatically by the installer for `imx585_mono`); binned (2K) ClearHDR is an invalid sensor combination on mono and is removed from its mode table.
- **Mode-detection guard against a stale `cinepi-raw`** — sensor probing now kills any leftover `cinepi-raw` process (orphaned by a crashed or manually-run previous session) before probing for HDR modes; if it was still holding the sensor's `wide_dynamic_range` control, the ClearHDR modes silently dropped out of the mode table with no error. Cinemate now warns if HDR modes still don't appear after the kill.
- **ClearHDR stabilization** — several rounds of fixes across the mono-sensor stack, gain shocks on a mode switch, self-healing after a bad sensor handshake, shutter follow-ups, and corrected default merge thresholds.
- **Live merge knobs** — `set hdr threshold low/high`, `set hdr blend`, `set hdr gain adder` tune the sensor's HG/LG merge while streaming; startup defaults live in `image_capture.hdr` and the knobs can be mapped to pots and encoders.
- **RP1 overclock, automated** — the installer compiles the `rp1-overclock` overlay, ships it disabled (`#dtoverlay=rp1-overclock` in config.txt), and the settings editor's Boot config pane toggles it for higher ClearHDR frame rates on Pi 5 / CM5. See [Overclocking the Pi](overclocking.md).
- **RP1 pixel-rate ceiling passed to cinepi-raw** — libcamera's PiSP pixel-rate bound used to be a compile-time constant baked at the overclocked value, so a non-overclocked board running a fast imx585 mode could silently corrupt frames (a CSI2-to-ISP-FE FIFO overrun that returns static with nothing logged, not a dropped frame). Cinemate now decides the ceiling from the RP1 overclock toggle's actual state and passes it to cinepi-raw as `--max-pixel-rate`. See [Overclocking the Pi](overclocking.md).
- **Launch refusal on a failed HDR handshake** — cinepi-raw retries the sensor's `wide_dynamic_range=1` write up to 4 times, 50 ms apart, and now throws and refuses to launch — instead of silently proceeding — when the sensor never confirms it. Previously an unconfirmed write still launched and recorded a flat BLC pedestal fill instead of real image data. See [ClearHDR](clear-hdr.md#new-launch-refusal-if-the-sensor-doesnt-confirm-hdr).

### CinePi-RAW recorder

- **`--keep16` removed** — SDR sensor modes always write 12-bit DNGs. The flag only preserved 4 padding bits, so files are ~33% smaller with no loss of information. True 16-bit modes (IMX585 ClearHDR) are unaffected.
- **Reworked capture path under load** — the redis-based per-frame capture pipeline was reworked, with a bgsave debounce, for steadier behaviour when the storage device is under load.
- **Correct DNG timecode frame base** — the SMPTE timecode frame base is now derived from the configured fps instead of `FrameDuration`, fixing incorrect embedded timecode on modes where the two disagreed.
- **MJPEG clean preview fix** — the clean (no-overlay) preview feed now serves correctly on `/` and registers its stream targets before the first frame arrives.

### CineMate Log

- **New, opt-in log-companded DNG recording** on IMX585 and IMX283 — log-compands the linear sensor signal to a smaller code depth and writes a DNG `LinearizationTable` so any DNG app decodes it back to linear automatically. No LUT is needed or should be applied. Shrinks 16-bit ClearHDR frames 17–37% and 12-bit SDR frames ~17%. See [CineMate Log](cinemate-log.md).
- **Per-camera `log_encode` setting** (`false` / `true` / `10` / `12`) and the live `set log` command, both resolved against each camera's own live sensor mode — never a standing choice that can silently drift out of sync with a resolution or ClearHDR switch.
- **`LOG10`/`LOG12` badge** on the Simple GUI, per camera, reflecting what's actually running rather than what was requested.

### Cinemate

- **Settings editor** — a new browser page at `cinepi.local:5000/settings-editor` for configuring and operating the camera without SSH: edit `settings.jsonc` section by section, stage `/boot/firmware/config.txt` changes (sensor overlays, RP1 overclock, link frequency), watch the live camera feed, review a take frame-by-frame, and browse, download, delete or format the RAW drive — all from one page. Saving `config.txt` here writes and reboots within under a second, with **no confirm/revert window and no backup of the previous file** — unlike the recovery console's config.txt editor, which backs up and arms a 5-minute confirm/revert timer. Use the recovery console instead when you want that safety net. See [Settings editor](settings-editor.md).
- **Settings editor config.txt write fix, and `cinepi.local` mDNS install** — the settings editor runs as `pi`, and saving `config.txt` from it previously raised `EACCES` before writing a byte, so the save silently could never succeed; it now falls back to a narrowly-scoped privileged helper (`cinemate-apply-config-txt`) that preserves the file's existing owner/mode. The installer also installs and enables `avahi-daemon`/`libnss-mdns` so `cinepi.local` resolves out of the box, and fixes a stale `/etc/hosts` `127.0.1.1` entry that could break local name resolution independently of mDNS.
- **Playback** — a new tab in the settings editor plays a recorded take back in the browser at its conform frame rate, decoding frames live from the CinemaDNG files on the card — nothing is transcoded, nothing is written back. See [Playback](playback.md).
- **Recovery console** — a new, independent `cinemate-recovery.service` on `:8080` lets you diagnose a Cinemate that will not start, edit `settings.jsonc` and `/boot/firmware/config.txt`, and restart Cinemate — from a phone on the hotspot, with no laptop or SSH. Standard library only, runs as root, and has no dependency on `cinemate-autostart.service` so it survives a crash that takes Cinemate down. The hotspot's Wi-Fi profile now also autoconnects at boot and self-heals a broken `settings.jsonc` by falling back to the last-known-good SSID rather than the compiled-in `CinePi` default. See [Recovery console](recovery-console.md).
- **Storage** — a new `hw_write_failures` counter surfaces as a live "use exFAT or ext4" warning when the storage device can't keep up with the write rate during a take; NTFS is now explicitly flagged supported but not recommended for recording, since its Linux driver can drop frames under sustained 4K writes.
- **No camera at boot** — Cinemate now starts and stays usable with no camera attached instead of failing: the HDMI and web GUIs show a full-width `CAMERA NOT FOUND` message while the hotspot, web UI and settings editor stay reachable. Cinemate re-probes for the sensor on every start, so recovery is just power off, connect the camera, power back on — no command needed.
- **Web GUI rebuilt onto `simple_gui`'s layout** (`feature/web-preview-layout`), driven over the same `/api/v1/cmd` dispatcher as the CLI/serial paths, and gained a live mic-input VU meter (matching `simple_gui`'s green/yellow/red thresholds and L/R channel labels). The page also now reloads automatically once a resolution/mode change completes, gained an EXPERIMENT drawer for live exposure sliders, rebuilt GPIO IN/OUT panes that represent every binding, and phone-usability fixes (viewport meta on the settings editor, larger tap targets and type floors on the live GUI).
- **Per-mode fps ceiling override** — the fps ceiling for each sensor mode can now be corrected and edited directly in `settings.jsonc` (`custom_modes`) instead of being fixed by the driver's mode table.
- **Dynamic resolution** — the tie-break between candidate modes now ranks bit depth over `fps_max`, and an explicit 12-bit request combined with a missing toggle no longer silently downgrades resolution.
- **Controls** — fixed a race between the front-panel potentiometer and an explicit app-side `set` landing on the same control; fixed `get_setting('shutter_a_nom')` resolving to the wrong redis key, which had broken shutter-angle increment/decrement via the Komodo GPIO rotary encoder and the CLI; decoupled shutter-angle sync-mode granularity from the free-increment step setting; fixed mode-switch controls not re-applying correctly after a resolution/mode change.
- **Fixes** — RAW-drive unmount/remount no longer fails to find the volume again on a stale `blkid` probe; `cinemate-autostart` restart no longer hangs behind a polkit auth prompt; the link-frequency dropdown no longer shows disabled/greyed out incorrectly in the web GUI; the config.txt toggle no longer shows a stale state when navigating back to the settings editor; the exposure-time/shutter display no longer goes stale in the GUI.

### Web API

- **New wireless control API** over the Wi-Fi hotspot — ESP32, Pico W, other Pis and phones can now send the same commands as the CLI/serial over HTTP (`POST /api/v1/cmd`), read live status (`/api/v1/get/<key>`, `/api/v1/status`), and receive push updates via a UDP status broadcast (`8888/udp`) or SSE (`/api/v1/events`). One dispatcher (`CommandExecutor.handle_received_data`) now serves the CLI, serial and web paths identically. `allow_destructive` defaults to `false`, so `reboot`/`shutdown`/`erase`/`format` are blocked out of the box on a stock unit. See [Web API](web-api.md) and [Building control units](building-control-units.md).

### Raspberry Pi / Bookworm

- **Installer** — no longer creates a Python virtualenv; packages install straight into system Python (`cinemate-autostart.service` now launches `python3` directly), fixing several install blockers that only appeared in the venv path.

## Version 3.3.2

### libcamera

- Cinemate now uses its own fork of libcamera.

### imx283 driver

- Cinemate now uses its own fork of imx283 driver.
- 2 additional modes: 3840 x 2160 (4K UHD, native crop) and 2736 x 1538 (2.7K 16:9, binned) 

### imx585 driver

- Cinemate now uses its own fork of imx283 driver.

### CinePi-RAW recorder

- **Frame-rate phase lock** — closed-loop control (sigma-delta VBLANK dither) keeps long takes locked to the Pi's wall clock and pre-converges during preview. On by default.
- **More reliable audio sync on 4K / exFAT** — the capture path was reworked (protected helper, dedicated writer thread, wall-clock reconciliation, real-time scheduling) for more reliable WAV sync on demanding modes.
- **Wall clock embedded timecode** — timecode is anchored to the first frame's wall-clock time and follows the Pi's real-time clock.
- **Correct Pi 4 RAW** — CSI2-packed frames decode correctly on Pi 4-family boards; raw packing (P/U) is chosen per Pi model automatically.
- **Camera model** — set the camera model manually for each attached sensor.

### Cinemate

- **Storage / media** — multi-drive RAW hot-swap with a standby drive and automatic promotion. Default format is exFAT.

### Raspberry Pi / Bookworm**
- **Boot / install** — faster boot-to-preview on Pi 4/5 (about 10-15 seconds)

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
- Automatic storage pre-roll can be disabled in `settings.json`.
