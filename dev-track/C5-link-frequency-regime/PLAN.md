# C5 · Link frequency and RP1 regime — verify what shipped, then make the mode table honest

Two ceilings govern frame rate on this stack, and Cinemate now exposes both. What it does
not do is tell the operator when they disagree.

- The **RP1 overclock** raises what the receiver can drain: 380 MPix/s stock, 580 MPix/s
  with the 300 MHz overlay.
- The **CSI-2 link frequency** raises what the sensor sends, per port, as a `dtoverlay`
  parameter.

Both shipped to `dev` on 2026-08-26 (merge `9834b322`, PR #154, plus the overclock work
through `d175b2fe`). **None of it is verified on hardware.** This step closes that, and
then fixes the one real defect the work exposed.

## The defect

`libcamera`'s `minPixelProcessingTime` is compiled at `1.0us / 580` unconditionally on
Pi 5 / CM5, and the overlay ships commented out. So `cinepi-raw --list-cameras` advertises
the fast imx585 modes **even at stock clocks**, nothing clamps them, and selecting 75 fps
with the overclock off drops frames silently. The mode table describes a machine the
operator may not be running.

The same gap applies to link frequency: pick 1039.5 MHz with a stock RP1 and the CFE drain
bound (~43.8 fps at 4K) binds first, invisibly.

Today the only honest check is reading the clock itself:

```bash
sudo grep -E '^[[:space:]]*(pll_sys|clk_sys) ' /sys/kernel/debug/clk/clk_summary
```

That is a documented workaround, not a fix — `docs/overclocking.md` says so in as many
words, which is the tell that this belongs on the feature plan.

## What the fix looks like

Make the advertised ceiling reflect the live regime, so the mode table stops lying:

- Probe the active RP1 rate — read the `rp1` node's `assigned-clock-rates` `u32[7]`, which
  is exactly what the libcamera fork already does (`0413c1351`), or parse its `Info` log
  line `RP1_CLK_SYS at …MHz`.
- Compute a per-mode ceiling from that regime in `sensor_detect._mode_from_metadata_or_detected()`
  and fold it into `fps_max`, the same way the `custom_modes` override already narrows it.
- Everything downstream consumes the mode dict's `fps_max` blindly, so the GUIs, dynamic
  resolution and storage pre-roll inherit the correction with no further change.

The settings editor already shows both numbers where they differ (`fps_max_detected` vs
`fps_max_effective`, in the sensor pane's detected-modes readout), so the presentation
pattern for "capped from N" exists and should be reused rather than reinvented.

**Sequencing:** the gates run first. G2 measures the imx585 fps table that the regime model
has to reproduce — building the model before that data exists would be fitting to numbers
copied from a driver README.

## Hardware gates

**Full gate definitions with predictions stated in advance:
[`GATES.md`](GATES.md)** in this directory. Four gates, ordered by what unblocks what and
by risk, not by topic:

| Gate | Tests | Why this order |
|---|---|---|
| G0 | The settings editor can write `config.txt` at all, and the RP1 toggle reaches 300 MHz | Blocks G2/G3; also the first hardware test of the shipped toggle fix |
| G1 | imx283 `link-frequency` overlay parameter, patched and unpatched | Cheapest, and the riskiest claim: an unpatched overlay is predicted to stop the camera enumerating entirely |
| G2 | imx585 fps at each of the seven link frequencies, overclock on and off | Supplies the data the regime model is built against |
| G3 | imx477 at 750 MHz | Gated feature — its menu ships hidden pending this |

Outcomes go to `cinemate-handbook/lessons/hardware-log.md` once the operator confirms the
interpretation, per the handbook's session method. A gate that merely ran is not a finding.

## Preconditions, both outstanding

1. **The settings editor cannot write `config.txt` on the dev Pi.** It runs as `pi`;
   `/boot/firmware` is root-owned vfat (`dmask=0022`). The privileged helper
   (`/usr/local/bin/cinemate-apply-config-txt`) is installed, but the sudoers grant for it
   is missing and the Pi's checkout predates `write_config_txt`. Repair is in `GATES.md`;
   it validates with `visudo -cf` before installing, so a malformed file cannot land.
2. **The dev Pi has an imx477 attached**, not an imx585. G2 needs the StarlightEye; G1
   needs the OneInchEye.

Baseline measured 2026-08-26: kernel `6.12.93+rpt-rpi-2712`, CM5 Lite, `pll_sys`/`clk_sys`
both **200 MHz** (overclock installed, off), libcamera at `1.0us / 580`,
`rp1-overclock.dtbo` present, `#dtoverlay=rp1-overclock` present and commented.

## Risk carried from what already shipped

Selecting a non-default imx283 link frequency needs the overlay parameter added to
`Tiramisioux/imx283-v4l2-driver` `6.12.y` at `257c9cf`. An **older overlay rejects the
unknown parameter and the camera does not enumerate at all.** That minimum revision is
recorded in `resources/sensors.json` notes and in `docs/sensors.md`, and G1 tests it. If G1
shows the failure is as severe as predicted, gating imx283's menu behind `menu_enabled:
false` — the same one-line mechanism holding imx477 back — is the obvious mitigation.

| commit | change |
|---|---|
| C5.1 | Gate outcomes recorded: `GATES.md` verdicts, `sensors.json` fps figures corrected if G2 disagrees, `notes` "advisory" wording dropped |
| C5.2 | `sensor_detect.py` · probe the live RP1 rate; expose it as a regime value |
| C5.3 | `sensor_detect.py` · fold the regime ceiling into `fps_max` in `_mode_from_metadata_or_detected()`, alongside the existing `custom_modes` narrowing |
| C5.4 | GUIs · surface "capped by RP1 regime" using the existing `fps_max_detected` / `fps_max_effective` presentation |
| C5.5 | Docs · `overclocking.md` drops the manual `clk_summary` check as *the* answer and describes the live behaviour instead |

**Branch:** `feature/link-frequency-regime` off `dev` (cinemate only — the libcamera fork
already reads the live clock; no cinepi-raw change). To be cut after G2.

**Verification.** Desk — the regime probe is a pure function of a device-tree read, so it
tests Pi-free with a fake node, same `__new__` + fake pattern as
`test_cinepi_controller_startup_sensor_mode.py`; assert that a stock regime narrows an
imx585 4K mode to ~43.8 fps and an overclocked one does not, and that a board with no `rp1`
node degrades to today's behaviour rather than clamping to zero. Hardware — G0–G3 above,
then a regression pass confirming the corrected ceilings match what G2 measured.

**Hardware needed:** the dev Pi, plus an imx585 (G2) and an imx283 (G1) — both already in
the operator's kit. G1 additionally needs a Pi whose imx283 driver predates `257c9cf`, or
a deliberate downgrade of the installed overlay.
