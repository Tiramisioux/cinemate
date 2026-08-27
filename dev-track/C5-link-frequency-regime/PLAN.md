# C5 · Link frequency and RP1 regime — verify what shipped, then make the mode table honest

!!! note "Status 2026-08-26 — the code half is done and the defect is closed"
    The fix landed the same day this was filed, and took a different shape than
    planned. Instead of Cinemate clamping `fps_max` after the fact, the ceiling is
    now decided from the overlay switch and passed down —
    `rp1_regime.py` → `cinepi-raw --max-pixel-rate` → `LIBCAMERA_RPI_MAX_PIXEL_RATE`
    → `minPixelProcessingTime`. libcamera then produces an honest mode table
    itself.

    **Gate G2 passed on hardware** (imx585 mono, 2026-08-26): at the 380 default
    the 4K mode advertises 43.80 fps where the hardcoded-580 build advertised
    66.85 — the ratio matches `380/580` to five decimal places. That proves
    libcamera both honours the value and applies it to enumeration, so
    **C5.2–C5.4 below are cancelled**: there is nothing left for Cinemate to
    correct. See `cinemate-handbook/lessons/hardware-log.md`, 2026-08-26.

    Still open: G1 (imx283 overlay parameter, unbooted), G3 (imx477 750 MHz), and
    a sustained take at 66.85 fps — only the advertised ceiling has been observed,
    not real capture.

Two ceilings govern frame rate on this stack, and Cinemate now exposes both. What it does
not do is tell the operator when they disagree.

- The **RP1 overclock** raises what the receiver can drain: 380 MPix/s stock, 580 MPix/s
  with the 300 MHz overlay.
- The **CSI-2 link frequency** raises what the sensor sends, per port, as a `dtoverlay`
  parameter.

Both shipped to `dev` on 2026-08-26 (merge `9834b322`, PR #154, plus the overclock work
through `d175b2fe`). The defect below was found the same day and is now fixed; the
remaining gates are G1 and G3. History below is kept as filed — see the status note.

## The defect (fixed 2026-08-26)

`libcamera`'s `minPixelProcessingTime` **was** compiled at `1.0us / 580` unconditionally on
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

## Preconditions (both cleared 2026-08-26)

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
| ~~C5.2~~ | ~~probe the live RP1 rate in `sensor_detect.py`~~ — **cancelled.** Superseded: the rate is decided in `rp1_regime.py` from the overlay switch and passed down, rather than probed. Probing was tried in libcamera first and fails on this hardware — no `rp1` node in `/proc/device-tree`, and the overlay's requested 300 MHz arrives as 333.33 MHz |
| ~~C5.3~~ | ~~fold a regime ceiling into `fps_max`~~ — **cancelled by G2.** libcamera already applies the bound during enumeration, so `--list-cameras` is honest on its own and a second correction in Cinemate would double-count |
| ~~C5.4~~ | ~~surface "capped by RP1 regime" in the GUIs~~ — **cancelled with C5.3.** Nothing to surface: the fps the mode table reports is already the achievable one |
| C5.5 | Docs · `overclocking.md` drops the manual `clk_summary` check as *the* answer and describes the live behaviour instead |

**Branch:** none outstanding. The work landed across all three repos rather than on one
cinemate branch, which the original plan got wrong — it assumed the libcamera fork already
read the live clock, when in fact that code was unpushed and, once tested, unworkable:
cinemate `feature/rp1-pixel-rate`, cinepi-raw `feature/max-pixel-rate`, libcamera
`feature/rp1-clock-autodetect` → its `cinemate` branch.

**Verification.** Desk — done: `_test/test_rp1_regime.py`, 13 cases, all Pi-free. The ones
that matter are the asymmetric fallbacks, since the failure they guard is silent: overlay
enabled but the clock still reading stock resolves *down* to 380, an unreadable clock still
honours the switch, and no RP1 means no ceiling is passed at all. Hardware — G2 passed
(above); G0 passed incidentally, since the settings switch drove the config.txt write that
produced the 333 MHz clock. G1 and G3 remain.

**Hardware needed:** the dev Pi, plus an imx585 (G2) and an imx283 (G1) — both already in
the operator's kit. G1 additionally needs a Pi whose imx283 driver predates `257c9cf`, or
a deliberate downgrade of the installed overlay.
