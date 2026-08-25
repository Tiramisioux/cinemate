# C5 · Hardware gates

Method per `cinemate-handbook/working/hardware-session.md`: state the prediction **before**
running, then record the verdict in `cinemate-handbook/lessons/hardware-log.md` (Tested /
Worked / Did not work / Why / Confirmed by) once the operator confirms the interpretation.
A command exiting cleanly is not a finding.

Run in order. G0 unblocks G2 and G3; G1 is cheap and tests the riskiest claim.

## Baseline, measured 2026-08-26

| | |
|---|---|
| Board | CM5 Lite, `bcm2712` |
| Kernel | `6.12.93+rpt-rpi-2712` |
| `pll_sys` / `clk_sys` | **200 MHz** — overclock installed but off |
| libcamera | `minPixelProcessingTime = 1.0us / 580` (fork tip `614ce18c6`) |
| Overlay | `rp1-overclock.dtbo` present; `#dtoverlay=rp1-overclock` present, commented |
| Attached sensor | imx477 on cam0 |

The clock check used throughout:

```bash
sudo grep -E '^[[:space:]]*(pll_sys|clk_sys) ' /sys/kernel/debug/clk/clk_summary
```

Rate is the fifth column.

---

## G0 — the settings editor can write config.txt, and the toggle reaches 300 MHz

**Belief being tested.** That the shipped RP1 toggle works end to end. Two fixes are
involved and neither has run on hardware: the privileged-write path (`write_config_txt`
staging to a pi-writable file, then a narrowly-scoped sudo helper) and the guard that makes
enabling fail loudly when there is no overlay line to uncomment.

**Why hardware.** The failure is environmental, not logical: `/boot/firmware` is root-owned
vfat with `dmask=0022`, and the settings editor runs as `pi`. `os.access` confirmed both the
directory and the file are unwritable by that user on 2026-08-26. Nothing about the sudoers
grant or the helper's behaviour can be settled off the Pi.

**Repair first** — the sudoers grant for the helper is missing on the dev Pi, and its
checkout predates `write_config_txt`. Validated before installing, so a malformed file
cannot lock out sudo:

```bash
git -C ~/cinemate pull --ff-only origin dev
sudo cp /etc/sudoers.d/pi_cinemate /tmp/pi_cinemate.new
echo 'pi ALL=(ALL) NOPASSWD: /usr/local/bin/cinemate-apply-config-txt' | sudo tee -a /tmp/pi_cinemate.new
sudo visudo -cf /tmp/pi_cinemate.new && sudo install -o root -g root -m 440 /tmp/pi_cinemate.new /etc/sudoers.d/pi_cinemate
sudo systemctl restart cinemate-autostart
```

**Procedure.** In the settings editor's Boot config pane, turn **RP1 overclock** on and
save. Let it reboot. Run the clock check. Turn it off, save, reboot, check again.

**Prediction.** Before the repair, saving returns HTTP 500 with a "Could not write" message
naming `/boot/firmware/config.txt`. After it, the save succeeds, the Pi reboots on its own,
and `pll_sys` and `clk_sys` both read `300000000`. Toggling back returns both to
`200000000`. `config.txt` outside the managed block is byte-identical throughout.

**Also worth capturing while here:** `cinepi-raw --list-cameras` at 200 MHz. The prediction
is that it advertises the *same* mode ceilings as at 300 MHz, because
`minPixelProcessingTime` is compiled in unconditionally — that is the C5 defect, and this is
the cheapest place to record it.

---

## G1 — imx283 link-frequency parameter, patched and unpatched

**Belief being tested.** That `selectable: true` for imx283 in `resources/sensors.json` is
real. The overlay parameter was added to `Tiramisioux/imx283-v4l2-driver` `6.12.y` at
`257c9cf` on 2026-08-26 and verified only by compiling with `dtc` on a laptop and diffing
the resulting `.dtbo` against the unpatched one. It has never been booted.

**Why hardware.** An overlay that compiles can still be rejected at boot, and the predicted
failure mode is severe rather than cosmetic: an unknown `dtoverlay` parameter means the
camera does not enumerate at all.

**Procedure.** With the imx283 attached and the **patched** driver installed, set
`dtoverlay=imx283,cam0,link-frequency=360000000`, reboot, then `cinepi-raw --list-cameras`.
Repeat with an overlay predating `257c9cf` (or downgrade the installed `.dtbo` deliberately).

**Prediction.** Patched: the camera enumerates, and its modes report roughly half their
usual maximum fps, since 360 MHz is half the default link rate. Unpatched: the overlay is
rejected and **no camera enumerates at all**.

**If the unpatched failure is milder than predicted** (parameter ignored rather than overlay
rejected), soften the warning in `docs/sensors.md` and the `sensors.json` note. **If it is
as severe as predicted**, consider gating imx283's menu behind `menu_enabled: false` — the
same one-line mechanism already holding imx477 back — until the patched driver is
guaranteed present.

---

## G2 — imx585 frame rates at each link frequency

**Belief being tested.** The fps figures in `resources/sensors.json` come from
will127534's driver README, not from this stack, and are marked advisory in the block's
`notes`. This gate confirms or corrects them, and supplies the data the C5 regime model is
built against.

**Why hardware.** Pixel throughput depends on the sensor, the RP1 clock and the CFE drain
rate simultaneously; no amount of source reading settles it.

**Procedure.** imx585 attached, RP1 overclock **on**. For each of 297 / 360 / 445.5 / 594 /
720 / 891 / 1039.5 MHz: set it in the Boot config pane, reboot, run the clock check, then
`cinepi-raw --list-cameras`, then record a short take at 4K 12-bit. Then repeat **one**
frequency — 1039.5 MHz — with the overclock **off**.

**Prediction.** `--list-cameras` advertises 20.8 / 25.0 / 30.0 / 41.7 / 50.0 / 60.0 /
75.0 fps for 4K 12-bit 4-lane respectively. Takes at or below the advertised rate record
without dropped frames. With the overclock off, the advertised figure is unchanged (the
defect) but the sustained rate caps near 43.8 fps, because the 380 MPix/s drain bound binds
before the link does.

**If it disagrees:** correct `fps_4k12_4lane` in `resources/sensors.json`, drop "advisory"
from the block's `notes`, and update the table in `docs/overclocking.md`.

---

## G3 — imx477 at 750 MHz

**Belief being tested.** That since kernel 6.12.49 the imx477 driver computes PLL settings
for any ~3 MHz multiple, and that 750 MHz — the Pi 5 RP1 spec limit — is safe on this stack.
The menu ships hidden (`menu_enabled: false`) until this passes.

**Why hardware.** The driver's `imx477_check_link_freq()` is arithmetic with no upper bound;
it vouches for nothing. Only the 450 MHz default is proven here.

**Procedure.** Hand-edit `/boot/firmware/config.txt` to
`dtoverlay=imx477,cam0,link-frequency=750000000`, reboot, `--list-cameras`, record a take,
revert. Do **not** enable the menu as part of this gate.

**Prediction.** Per-mode fps is higher than at 450 MHz — RPi's own report has
1332×990 10-bit going roughly 120 → 200 fps. Frames are clean; their testing saw white and
corrupt frames only from about 939 MHz.

**If it passes:** flipping `menu_enabled` to `true` is an operator decision, not an
automatic consequence.
