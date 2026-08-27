# C4 · Sensor autodetect — find the attached sensor, apply the overlay, heal config.txt

CineMate finds out which sensor is physically attached and configures it without user
input: on a boot where the configured overlay produces no camera, a probe step tries each
candidate overlay at runtime, lets the drivers' chip-ID validation identify the sensor and
its port, persists the result into config.txt's camera section, and continues into normal
operation. Autodetect is an **on/off toggle**; with it off, the operator selects the
sensor per port explicitly, exactly as today. imx585 color vs mono is electrically
indistinguishable (same die, same chip ID), so mono is always an explicit **checkbox**,
in both modes.

**Full implementation spec: [`SENSOR-AUTODETECT-PLAN.md`](SENSOR-AUTODETECT-PLAN.md) in
this directory**, written against `dev` 2026-08-26 (cinemate repo only; cinepi-raw and
libcamera untouched). Feasibility was hardware-proven on the dev CM5 2026-06-16
(`~/Documents/codex/sensor_probe.sh`, kernel 6.12.25) and desk-re-verified 2026-08-26.

The finding that shapes the step: **the drivers are the detector.** All candidate sensors
share I2C address 0x1a and are unpowered until an overlay enables their regulator and
clock, so passive bus scanning can never identify them — but applying an overlay powers
the sensor, and every candidate driver (imx477/296/283/585) then reads the chip ID and
refuses to bind on a mismatch. Trying overlays in sequence *is* the detection. Firmware
`camera_auto_detect` does the same thing for official cameras only; it will never know
imx283/imx585.

Decisions taken in the investigating Fable thread (2026-08-26), recorded once here:

- **Toggle + explicit mode + mono checkbox** (operator requirements): a
  `# cinemate-sensor-autodetect: on` marker line in the managed camera section (absent =
  off = today's behavior, fully backward compatible). Off → the existing per-port model
  dropdowns. The `imx585_mono` dropdown entry is replaced by imx585 + a per-port **Mono**
  checkbox that owns the `,mono` token — same config.txt shape as today.
- **Self-healing persist, not probe-every-boot**: config.txt keeps concrete
  `dtoverlay=<model>,camN[,mono]` lines. The probe runs only when `camera-ready.sh` found
  no camera *and* the marker is on. On a hit it persists the line and continues the same
  boot on the runtime-bound overlay; steady-state boots cost zero. On no hit it leaves
  config.txt untouched and falls through to C3's NO CAM state — a loose cable never wipes
  the operator's config.
- **Never remove a bound overlay** (the historical Pi-4-era unload crash): `dtoverlay -r`
  only after a candidate *failed* to bind; the winning overlay stays loaded. imx290/327/462
  family excluded (ghost-binds on an empty connector); imx519 excluded (no modes in
  sensors.json).
- **Mono survives healing**: when the probe persists an imx585 line it preserves the
  port's existing `,mono` token. Swapping a mono unit for a color unit (or vice versa) is
  undetectable by design — the checkbox is the recovery, and the docs say so.
- **Both fork drivers installed** when autodetect is enabled (the existing
  `INSTALL_IMX283_DRIVER`/`INSTALL_IMX585_DRIVER` force flags); fresh-install default
  stays explicit selection until the hardware gates pass, matching the ship-off-by-default
  convention.
- **Pi 5 / CM5 only in v1**: the probe script skips (exit 0) on non-BCM2712 platforms —
  runtime overlay behavior on Pi 4/Unicam is unverified and explicit mode still works
  there.

Held open for the plan review, without blocking implementation: whether the healing boot
should reboot once instead of continuing on the runtime overlay (only if gate **G0** —
full record under a runtime-applied overlay, incl. ClearHDR 16-bit — fails; G0 runs
*before* implementation and needs no new code), and whether the installer should offer an
install-time immediate probe so the first boot is already healed.

| commit | change |
|---|---|
| C4.1 | `boot_config.py` · autodetect marker + per-port mono state (parse `imx585_mono` legacy lines, render `,mono` token) + tests |
| C4.2 | Settings editor Boot Config pane · autodetect toggle, detected-state display, mono checkbox — Python **and** JS copies |
| C4.3 | `sensor-autodetect.sh` probe (productized from the June script) + persist helper + second advisory `ExecStartPre` in `cinemate-autostart.service` |
| C4.4 | Installer · "autodetect" sensor-menu option, marker write, both-fork-drivers policy |
| C4.5 | Docs · sensors page, installation, troubleshooting (incl. the mono-swap caveat) |

**Branch:** `feature/sensor-autodetect` off `dev` (cinemate only). **Depends on C3** —
the probe rides C3's advisory gate and falls back to C3's NO CAM state; C4 implements
after C3 lands on `dev`.

**Verification.** Desk — `boot_config.py` round-trip tests (marker on/off, mono token,
legacy `imx585_mono` parse, never-synthesize preserved), probe script dry-run mode +
shellcheck, full `_test/` suite green. Hardware — gates **G0–G5** in the spec, each with
its prediction written in advance; G0 (record under runtime overlay) is the go/no-go
design gate and runs first, on unpatched `dev`, using the existing June probe script.
Gate outcomes go to `cinemate-handbook/lessons/hardware-log.md`.

**Hardware needed:** the dev CM5 with at least two different sensors to swap (imx585 +
one of imx283/imx477); the dual-sensor rig for G5.
