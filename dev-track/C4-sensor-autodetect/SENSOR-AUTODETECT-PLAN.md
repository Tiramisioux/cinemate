# C4 — Sensor autodetect: implementation spec

Written 2026-08-26 against `dev` (cinemate `13ab0225` era), from a read-only investigation
in the Fable thread plus a hardware feasibility session on the dev CM5 2026-06-16 (kernel
6.12.25). Cinemate repo only — cinepi-raw is unchanged (it remains the `--list-cameras`
probe binary) and the libcamera fork is unchanged. Ledger entry: [`PLAN.md`](PLAN.md)
beside this file.

Line-number policy follows the handbook: files and functions are named, coordinates are
not.

## Verdict

Feasible with unusually strong evidence: the hard half (runtime overlay binding +
identification) was proven on this exact hardware in June 2026, and the post-overlay half
(`SensorDetect`, `discover_cameras()`) already exists in the codebase. What C4 builds is
the selection loop, its persistence, and the operator surface: an on/off toggle, explicit
per-port selection when off, and a mono checkbox for imx585. The genuinely subtle parts
are **never destroying operator config on a probe miss**, **never removing a bound
overlay**, and keeping the mono preference — which no probe can detect — alive across
self-healing rewrites.

## Confirmed facts

### Proven on hardware (dev CM5, 2026-06-16, kernel 6.12.25)

Clean-boot probe with the config.txt camera section commented out
(`~/Documents/codex/sensor_probe.sh`, also on the Pi as `/home/pi/sensor_probe.sh`):

- Runtime `dtoverlay <name>` powers the sensor, binds the driver, and libcamera
  enumerates it — no reboot, no config.txt involvement. imx585 was found automatically.
- Port targeting at runtime: no parameter → **cam1**; `cam0` parameter → **cam0**. The
  `,cam1` token is a firmware/boot-time feature only (confirmed against official docs).
- Chip-ID validation: wrong overlays do not bind — no false positives across
  imx283/477/296/585/519/219/708. The imx290/327/462 family ghost-binds on an empty
  connector and is excluded.
- The apply → settle → enumerate → `dtoverlay -R` cycle ran 16 times in one session
  without kernel trouble.

### Confirmed by source reading (2026-08-26)

- **Why passive scanning is impossible**: imx585 and imx283 sit at I2C `reg = <0x1a>`
  (their fork overlay dts files); imx477/imx296 likewise per upstream overlays
  (probable). The sensor's regulator and clock are enabled *by the overlay*
  (`vana-supply`, `cam1_clk` fragments) — an unconfigured sensor is unpowered and absent
  from the bus. Detection therefore must power-then-ask, which is exactly what a driver
  probe does.
- **The imx585 fork overlay now has a `cam0` override** (plus `mono`, `link-frequency`)
  — `imx585-overlay.dts` in the fork the installer pins since 2026-07-02. The June
  session's "imx585 can only reach cam1 at runtime" limitation is gone. The imx283 fork
  (`6.12.y`) has `cam0` too. Runtime cam0 binding is untested on hardware → gate G1.
- **Tuning files do not care how the overlay was applied**: the libcamera fork's
  `CameraData::loadIPA()` resolves `<model>[_mono].json` from the kernel-reported sensor
  name inside `registerCamera()` at *enumeration* time — the June `--list-cameras` hits
  already exercised it. Full record under a runtime overlay is thereby probable, not
  proven → gate G0, which is the go/no-go for the "continue without reboot" design.
- **Firmware `camera_auto_detect` covers official cameras only** (ov5647, imx219,
  imx477, imx708, imx296 era list; the docs hedge about Compute Modules). It will never
  detect imx283/imx585 — a pure-config.txt solution does not exist for the fork sensors.
- **`camera-ready.sh`** (`services/cinemate-autostart/`, deployed to
  `/usr/local/bin/` by the root `Makefile` `install` target) waits up to 30 s for an
  `imx` line from `cinepi-raw --list-cameras`. C3 makes it advisory (`ExecStartPre=-`).
  Its timeout is precisely the "configured overlay produced no camera" signal C4 hooks.
- **`boot_config.py`** (`src/module/app/`) owns the managed camera section:
  parse/render of `dtoverlay=<model>,camN[,mono]` between the
  `# ---- Camera section ----` markers, rewriting only that sub-region. Its
  `SENSOR_MODELS` list carries `imx585_mono` as a separate model today, and its shape is
  mirrored in `templates/settings_editor.html`'s `cfgOverlayLine()` /
  `CFG_SENSOR_LABELS` — **two copies, both must change** (the pane's established twin-
  catalogue pattern).
- **A renderer quirk to fix in passing**: `_render_camera_section()` writes
  `camera_auto_detect=1` whenever overlay lines are present — the installer writes `1`
  only for imx477/imx296 and `0` for imx283/imx585. C4's renderer aligns with the
  installer's per-model values (and `0` for any probe-persisted line).
- **Fork drivers install conditionally**: `should_install_imx283_driver()` /
  `should_install_imx585_driver()` default to "auto" (= only the selected sensor), with
  `INSTALL_IMX283_DRIVER` / `INSTALL_IMX585_DRIVER` force flags already present.
  Autodetect requires all candidate drivers on disk — a policy change, not new machinery.
  The installer's existing per-platform tuning-file handling (fork `imx283.json` must not
  clobber the stock bcm2835 one Pi 4 needs) stays as is.
- **`SensorDetect` + `discover_cameras()`** already identify model, mono flag, and port
  (media-path → cam0/cam1) once an overlay is bound — the entire post-detection half
  exists and is untouched by C4.

### The mono blind spot

imx585 color and mono are the same die with the same chip ID; the `mono` overlay
parameter tells the *driver* what to report, it does not read anything from the sensor.
No detection method — firmware, probe, or raw register reads — can distinguish them.
Mono is therefore operator state, full stop.

## Unknowns, stated

- Full record (DNG sequence, AWB/AE sanity, ClearHDR 16-bit) under a runtime-applied
  overlay — probable per the tuning analysis; G0 settles it before implementation.
- imx585/imx283 runtime binding on **cam0** via the forks' new `cam0` override — dts
  confirmed, never executed; G1.
- Whether firmware autodetect fires at all on the CM5 carrier (docs hedge on Compute
  Modules). Doesn't matter for correctness — the probe catches whatever the firmware
  misses — but G2 records which path caught an official camera, for the docs.
- Probe timing on real hardware. June's script used 3 s settle per attempt; predicted
  healing-boot cost ≈ 35–60 s total (30 s advisory gate + sweep), steady state zero.
  Measured at G2.

## Design

### 1. The toggle: a marker line in the managed camera section

```
# ---- Camera section ----
# cinemate-sensor-autodetect: on
camera_auto_detect=0
dtoverlay=imx585,cam1,mono
# ---- End camera section ----
```

- Marker **absent or `off`** = today's behavior, byte-for-byte backward compatible with
  every existing install. Marker `on` = the probe step may run and may rewrite this
  sub-region.
- Parsed and written by `boot_config.py`; greppable from shell by the probe script
  without cinemate's Python stack (same robustness philosophy as the recovery console:
  the boot step must not depend on the app it precedes).
- Rejected: a settings.jsonc key (splits camera boot policy across two files, adds a
  four-place settings-key contract for a value only the boot step reads); overloading the
  firmware's `camera_auto_detect` key (it has firmware semantics of its own, used below).
- Initial autodetect state (marker on, no line persisted yet — fresh install choosing
  autodetect): `camera_auto_detect=1` and no dtoverlay lines, so the firmware instantly
  handles official cameras and the probe only pays for fork sensors. Once any line is
  persisted: `camera_auto_detect=0` + explicit line (+ marker stays on). Both states are
  valid under marker-on; the rule is "auto_detect=1 only while no line is persisted".

### 2. Explicit mode and the mono checkbox (`boot_config.py` + settings editor pane)

- State dict: `cam0_sensor`/`cam1_sensor` keep the base models
  (`none|imx477|imx296|imx283|imx585`); new `cam0_mono`/`cam1_mono` booleans own the
  `,mono` token; new `autodetect` boolean owns the marker. `imx585_mono` disappears from
  `SENSOR_MODELS` but **legacy lines still parse** (`imx585` + `mono` token → model
  imx585, mono true) — no migration needed.
- Pane UI (both copies: Python constants and the template's `CFG_SENSOR_LABELS` /
  `cfgOverlayLine()` / `currentConfigText()`):
  - Autodetect toggle at the top of the camera block.
  - Toggle **off**: the existing per-port dropdowns, minus the `imx585 (mono)` entry,
    plus a **Mono** checkbox shown when that port's model is imx585.
  - Toggle **on**: the port rows render read-only from the parsed section
    ("imx585 on cam1 — detected"), the Mono checkbox stays **editable** (it is the one
    thing detection cannot decide).
  - Saving mono or the toggle edits config.txt only; the pane's existing reboot-required
    messaging applies unchanged.

### 3. The probe (`services/cinemate-autostart/sensor-autodetect.sh`)

Productized from the June script, deployed beside `camera-ready.sh` via the same
`Makefile` path. Runs as the **second advisory gate**:

```
ExecStartPre=-/usr/local/bin/camera-ready.sh
ExecStartPre=-/usr/local/bin/sensor-autodetect.sh
```

Behavior, in order:

1. Exit 0 immediately when: marker off/absent, a camera already enumerates
   (camera-ready succeeded), or the platform is not BCM2712 (Pi 4/Unicam runtime
   overlays are unverified — explicit mode only there, v1).
2. Candidate order: the port's previously persisted model first, then imx585, imx283,
   imx477, imx296. Per candidate: default attempt (→ cam1), then `cam0`. Both ports are
   swept; a port stops at its first hit. imx290 family and imx519 are never candidates.
3. Per attempt: `dtoverlay <model> [cam0]` → settle → check for a bind (dmesg/sysfs
   first, `cinepi-raw --list-cameras` as the confirming source, June-style) →
   **on miss `dtoverlay -r` the just-applied overlay; on hit leave it bound**. The
   winning overlay is never removed — the historical Pi-4-era unload crash (regulators
   torn down before the subdev) is avoided by construction, not by hoping the kernel
   fixed it.
4. On any hit: persist via `boot_config.py` (a small stdlib-only CLI entry point so the
   write logic exists once): explicit `dtoverlay=<model>,camN` per detected port,
   `camera_auto_detect=0`, marker kept on, and **the port's previous `,mono` token
   preserved when the detected model is imx585**. Then exit 0 — cinemate starts this
   boot on the runtime-bound overlay (G0-gated; fallback design below).
5. On no hit anywhere: **touch nothing**, log loudly, exit 0 → C3's NO CAM state. The
   probe never clears or rewrites the section on a miss — a loose cable, a dead sensor,
   or a borrowed body with no camera must leave the operator's config intact.
6. A dry-run flag (`--dry-run`) prints the sweep plan and detected result without
   applying anything permanent — for tests and for a future settings-editor "Detect now"
   button (out of v1).

Fallback design if G0 fails (record under runtime overlay broken): step 4 persists, then
reboots exactly once, guarded by a boot-id stamp under `/var/lib/cinemate/` — a second
failure in the same boot chain falls through to NO CAM instead of looping.

### 4. Installer (`cinemate-install.sh`)

- The sensor menu gains **autodetect** alongside the five explicit choices. Choosing it:
  marker on, `camera_auto_detect=1`, no active dtoverlay line, and **both** fork drivers
  installed (set the existing force flags; dkms already handles the kernel baseline).
- Explicit choices behave exactly as today (marker written as `off`).
- Fresh-install default remains explicit imx477 until the gates pass — same
  ship-off-by-default convention as `phase_lock`.
- Held open for plan review: an install-time immediate probe (the installer runs on the
  Pi with the sensor attached, so the first boot could already be healed). Not load-
  bearing; the boot-time probe covers it at the cost of one 30 s gate wait.

### 5. Docs

- `docs/sensors.md`: how autodetect works (the drivers-are-the-detector mechanism, which
  sensors are covered, Pi 5/CM5 only), the mono checkbox, and the mono-swap caveat
  (color↔mono swaps of imx585 units are undetectable — flip the checkbox).
- Installation page: the autodetect install option; existing installs enable it by
  toggling the switch in the Boot Config pane (needs both fork drivers — note the
  one-line install commands).
- Troubleshooting: what a healing boot looks like in the journal, and that a probe miss
  never changes config.txt.

## Commits

| commit | change |
|---|---|
| C4.1 | `boot_config.py`: `autodetect` marker + per-port `mono` booleans + legacy `imx585_mono` parse + renderer `camera_auto_detect` alignment; round-trip tests |
| C4.2 | Settings editor pane: toggle, read-only detected rows, Mono checkbox — Python constants **and** template JS (`CFG_SENSOR_LABELS`, `cfgOverlayLine()`, `currentConfigText()`) |
| C4.3 | `sensor-autodetect.sh` + `boot_config` CLI persist entry + second `ExecStartPre=-` in `cinemate-autostart.service`; deployed via the existing `make install` path |
| C4.4 | Installer: autodetect menu option, marker write, both-drivers policy via the existing force flags |
| C4.5 | Docs: sensors + installation + troubleshooting |

Each commit lands with its tests. C4.1 and C4.3 are load-bearing; C4.2 is UI on both
copies; C4.4 is policy plumbing; C4.5 is prose.

## Verification

### Desk (implementing session, no Pi)

- `boot_config.py` round-trips: marker on/off/absent; mono token add/remove; legacy
  `imx585_mono` line parses to imx585+mono and re-renders identically; a probe-persisted
  section preserves everything outside the camera sub-region byte-identical; the
  never-synthesize rule still raises without a managed block.
- Probe script: shellcheck clean; `--dry-run` unit-exercised with a faked `dtoverlay`
  and faked `--list-cameras` (the script takes both binaries from `PATH` — point them at
  fakes in a temp dir, no Pi needed).
- Pane: the twin catalogues agree (grep-level parity check between `SENSOR_MODELS` and
  `CFG_SENSOR_LABELS`, asserted in a test so the next drift is caught).
- Full existing `_test/` suite green.

### Hardware gates (operator, dev CM5)

Method per `cinemate-handbook/working/hardware-session.md`: prediction written before
each gate, verdict after; outcomes appended to
`cinemate-handbook/lessons/hardware-log.md`. **G0 runs before implementation** — it needs
only the existing June script and decides the continue-vs-reboot design.

| Gate | Setup | Prediction |
|---|---|---|
| G0 | Unpatched `dev`, camera section commented out, runtime-apply imx585 via the June script, then a real record: plain 12-bit and ClearHDR 16-bit takes | Both record normally — tuning resolves at enumeration, which the June hits already exercised. DNGs valid, AWB/AE behave. If this fails, switch step 4 to persist+reboot-once |
| G1 | Same boot: `dtoverlay imx585 cam0` with the sensor moved to cam0 | Binds and enumerates on cam0 — the fork's new `cam0` override works at runtime (dts-confirmed, never executed) |
| G2 | Patched build, autodetect on, config.txt deliberately naming the wrong sensor, systemd boot | camera-ready times out (30 s), probe finds the real sensor, persists, cinemate starts the same boot; healing cost ≈ 35–60 s; next boot is normal speed. Record whether firmware or probe catches an official cam on the CM5 carrier |
| G3 | Explicit mode regression: autodetect off, imx585 + Mono checkbox | Behaves exactly as today's `imx585_mono` selection: `dtoverlay=imx585,camN,mono`, mono modes in the GUI. All other explicit selections unchanged |
| G4 | Autodetect on, no camera attached, systemd boot | Full sweep finds nothing, config.txt byte-identical, C3's NO CAM state, journal says why |
| G5 | Dual-sensor rig (both ports), autodetect on, empty camera section | Both sensors detected on their real ports and persisted; dual preview works as before |

## Out of v1 — recorded so they are not re-litigated

- **Pi 4 / Unicam runtime probing**: unverified platform; the probe skips, explicit mode
  unchanged. Add a G-gate later if Pi 4 autodetect is ever wanted.
- **Hot-plug detection while running**: C3 already deferred it; C4's probe is boot-time
  only. A settings-editor "Detect now" button (probe `--dry-run` + apply + restart) is
  the natural follow-up once the probe exists.
- **Auto-detecting imx585 mono**: physically impossible (same die, same ID). The
  checkbox is the design, not a stopgap.
- **imx519 / imx219 / imx708 as candidates**: bind-distinguishable (June-proven for the
  loop mechanics) but not CineMate-supported sensors; sensors.json has no modes for
  them. Revisit only if support lands.
- **Install-time immediate probe**: held open above; cosmetic (saves one healing boot).

## Confidence

- **Confirmed** (hardware or direct source reading): the runtime bind/identify/port
  mechanism incl. removal of unbound overlays (June session); chip-ID rejection; the
  0x1a/unpowered passive-scan dead end; the fork overlays' `cam0`+`mono` overrides
  (dts); `loadIPA()` tuning resolution at enumeration; `camera-ready.sh` semantics and
  deployment path; `boot_config.py`'s section contract and its twin JS catalogue; the
  installer's conditional driver installs and force flags; firmware autodetect's
  official-cameras-only scope.
- **Probable**: full record under a runtime overlay (G0); runtime cam0 binding (G1);
  the healing-boot timing estimate (G2); firmware autodetect behavior on the CM5
  carrier (G2 records it).
- **Unknown**: none load-bearing — every open question has a gate.
