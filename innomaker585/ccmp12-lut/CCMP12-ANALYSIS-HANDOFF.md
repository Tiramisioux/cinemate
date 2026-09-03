# CCMP12 — curve measurement handoff (updated 2026-08-06, second session)

**The goal is to get 12-bit ClearHDR looking right.** That is modes 2 and 3 and nothing
else. Modes 0, 1, 4 and 5 are measured correct and agree with each other across the full
neutral ramp — they are the target, not the problem. `ccmp_decode` is the means; judge every
result on whether modes 2 and 3 join the other four.

Colour-wise the six modes differ in exactly two tags. `AsShotNeutral` is **identical**
(`0.625 1 0.5263`) across all six, so white balance cannot explain any difference between
them.

| | modes 0,1 (SDR 12) | modes 2,3 (CCMP 12) | modes 4,5 (linear 16) |
|---|---|---|---|
| `LinearizationTable` | absent — correct, data is linear | absent — **WRONG**, data is companded | absent — correct |
| `BlackLevel` | 200 — **measured correct** | 200 — **measured correct** | 3200 — **measured correct** |

**One defect, not two.** The `BlackLevel` half of this table used to read "wrong, measured
229". That was a light leak. See §2.

Background, in reading order: `../CCMP12-VS-LOG-DECISION.md` **§9**,
`../CINEMATE-LOG-COLORCHECKER.md` §§1–2 and §13, `../CINEMATE-LOG-VERIFIED.md`.

**All paths are relative to the repo root** (`/Users/patrikeriksson/Documents/cinemate`).
Tools and evidence live beside this file in `innomaker585/ccmp12-lut/` — see its `README.md`.

**§13.3's derived curve is falsified in part. Do not start from it as fact.** What survives
is in §2.

---

## 1. The data

Three sets, 159 DNGs, 1.3 GB, all gitignored.

### 1a. `takes/ccmp-greycard/` — the 17:05 session, 82 DNGs

Six takes, one session, same chart, same light, same exposure. Only the sensor mode changes.

| Take | Mode | Res / depth | Role |
|---|---|---|---|
| `CINEPI_26-08-06_170554_F22_C00000_cam0` | 0 | 1928×1090 12-bit **SDR** | linear control, binned |
| `CINEPI_26-08-06_170608_F22_C00001_cam0` | 1 | 3856×2180 12-bit **SDR** | linear control, full |
| `CINEPI_26-08-06_170626_F03_C00000_cam0` | 2 | 1928×1090 12-bit **ClearHDR** | **under test** |
| `CINEPI_26-08-06_170638_F00_C00001_cam0` | 3 | 3856×2180 12-bit **ClearHDR** | **under test** |
| `CINEPI_26-08-06_170653_F04_C00000_cam0` | 4 | 1928×1090 16-bit ClearHDR | linear truth for 2 |
| `CINEPI_26-08-06_170710_F19_C00001_cam0` | 5 | 3856×2180 16-bit ClearHDR | linear truth for 3 |

⚠ **Modes 0 and 1 clip.** 8.8–11.3% of every CFA phase is pinned at 4095: the big white
band, both white illumination chips, grey5, grey6 and part of the cyan patch. Usable only
below grey4 = 44% of white. This is not an exposure error — SDR clips 0.98 stops below the
chart's white chip at this exposure, which is ClearHDR's extra highlight range, measured.
Best set for **knee2 and the 1/16 segment**.

### 1b. `takes/ccmp-greycard-1837/` — the 18:37 session, 39 DNGs

Same six modes, same order, same framing.

| Take | Mode | Res / depth |
|---|---|---|
| `CINEPI_26-08-06_183719_F09_C00001_cam0` | 0 | 1928×1090 12-bit SDR |
| `CINEPI_26-08-06_183742_F24_C00002_cam0` | 1 | 3856×2180 12-bit SDR |
| `CINEPI_26-08-06_183759_F18_C00000_cam0` | 2 | 1928×1090 12-bit ClearHDR |
| `CINEPI_26-08-06_183819_F08_C00001_cam0` | 3 | 3856×2180 12-bit ClearHDR |
| `CINEPI_26-08-06_183837_F04_C00000_cam0` | 4 | 1928×1090 16-bit ClearHDR |
| `CINEPI_26-08-06_183854_F10_C00001_cam0` | 5 | 3856×2180 16-bit ClearHDR |

**Modes 0 and 1 are stopped down ×6.3 (−2.66 stops) and are UNCLIPPED across the whole
ramp.** Modes 2–5 did **not** move — they sit within +0.7 to +1.5% of the 17:05 session,
which is ~1% of lamp drift over 1.5 h.

⚠ **The shutter change reached the SDR modes only.** Whatever was set did not take on the
ClearHDR modes. That is a cinemate/cinepi-raw finding in its own right and is **not** part
of this job. Raise it, do not bundle.

⚠ **The two chart sessions are 1.5 h apart. Fit each independently and require agreement.
Never merge points from both into one curve** (§4).

### 1c. `takes/ccmp-c0-6mode/` — lens cap, one take per mode, 38 DNGs

| Take | Mode | | Take | Mode |
|---|---|---|---|---|
| `..._183919_F23_C00000_cam0` | 0 | | `..._183954_F08_C00001_cam0` | 3 |
| `..._183930_F11_C00001_cam0` | 1 | | `..._184003_F23_C00000_cam0` | 4 |
| `..._183946_F14_C00000_cam0` | 2 | | `..._184027_F14_C00001_cam0` | 5 |

This set replaces the old `ccmp-c0/` and `ccmp-c0_UHD/`, which were contaminated and have
been deleted. See §2.

### Conditions and launch

Studio, 5600 K. ISO 400, 25 fps, aperture ≈ f/3.2. Calibrite **ColorChecker Video**
(33 patches). **The chart fills the frame.** Registration crosses at all four corners;
the illumination-check black+white pairs sit at **diagonal opposite corners** — top-right
and bottom-left.

```
--mode <W>:<H>:<bits>:U   --hdr sensor   (ClearHDR only; absent for SDR modes 0/1)
--shutter 20000           (= 1/50 s, 180° at 25 fps; the 17:05 session)
--awb auto --awbgains 1.6,1.9
--tuning-file /home/pi/libcamera/src/ipa/rpi/pisp/data/imx585.json
                          no --log-encode  -> log path is OFF in every take
```

⚠ `--awb auto` is present but the explicit `--awbgains 1.6,1.9` won: every take carries
`AsShotNeutral 0.625 1 0.5263`. **White balance is constant and cannot explain any colour
difference between modes.** Still analyse **raw CFA codes** — the 16-bit takes' statistics
are invalid (`bitsPerPixel == 16` gate), so do not rely on anything AWB-derived.

⚠ `takes/ccmp-greycard/system.log` **does not cover the take window.** cinemate wipes `*.log`
on startup (`main.py:565-568`). Kept only for the launch parameters above.

**The tuning file matters in exactly one place.** `imx585.json` carries
`rpi.black_level: 3200`, which scales to 200 in the 12-bit domain. Measurement confirms it
(§2). `rpi.alsc` carries tuning constants but no shading tables, so lens shading is
uncorrected — which is fine, because it is common-mode across all six takes. There is **no
`rpi.decompand` block** in our tree.

---

## 2. Established. Do not re-derive, do not re-litigate.

### Verified on hardware

| Fact | Evidence |
|---|---|
| Driver `479117e` is built, loaded and governing | `v4l2-ctl` readback |
| CCMP thresholds **500 / 11500** | `--get-ctrl` with ClearHDR live |
| ACMP1 (middle) **1/64** (menu idx 6), ACMP2 (high) **1/16** (idx 4) | `--list-ctrls-menus` |
| Controls go active only when ClearHDR engages | `flags=inactive` clears |
| `__v4l2_ctrl_handler_setup()` at `imx585.c:1358` applies them after the mode table | source + readback |

Register semantics, confirmed from source: the menu **index is the register value**,
ratio = 1/2^idx. There is no low-segment slope register, so slope 1 below knee1 is the only
consistent reading — and it is now measured directly (below). `.def` for the threshold is 0;
the real values are `memcpy`'d into `p_cur`/`p_new` at `imx585.c:1131`.
**`v4l2-ctl --list-ctrls-menus` prints `default=0` for the threshold — that is correct.**

### 12-bit DNG unpacking is TIFF/DNG MSB-first, not MIPI

Measured, not assumed — the MIPI interpretation garbles G1 and B while leaving R and G2
plausible. It does not crash and it does not look obviously wrong. Carried in
`tools/dngread.py`.

```python
p0 = (b0 << 4) | (b1 >> 4)
p1 = ((b1 & 0x0F) << 8) | b2      # 2 px per 3 bytes
```

### Take registration — every 12-bit take sits 20 sensor rows off the 16-bit ones

Measured 2026-08-06. **The takes are not co-registered.** Modes 0, 1, 2 and 3 all sit
**20 sensor rows** above modes 4 and 5. `dx = 0` exactly.

| class | modes | offset vs the 16-bit take of the same resolution |
|---|---|---|
| binned 1928×1090 | 0, 2 vs 4 | −10 raw rows = **−20 sensor rows** |
| full res 3856×2180 | 1, 3 vs 5 | −20 raw rows = **−20 sensor rows** |

Replicated on **both** chart sessions to 0.1 px, and corroborated model-free by locating
the top edge of the white band: raw row **155.04** in mode 3 against **174.87** in mode 5,
and **76.94** against **86.95** binned.

**Cause, measured: the 16-bit takes carry the sensor's optical-black rows and the 12-bit
takes do not.** The IMX585 datasheet, page 2: *Optical black — Vertical (V) direction:
Front 20 pixels, rear 0 pixels*. Row means above black, chart filling the frame:

| mode | depth | rows 0–19 (0–9 binned) | next 10 rows | OB band |
|---|---|---|---|---|
| 0, 1 | 12-bit SDR | 429 | 621 | no |
| 2, 3 | 12-bit ClearHDR | 138 / 442 | 152 / 459 | no |
| 4, 5 | 16-bit ClearHDR | **1** | 40–47 | **YES** |

(12-bit scale.) It tracks **output bit depth, not ClearHDR** — the SDR modes behave like
the CCMP ones — so it is not `CCMP_EN`, which is the only register the driver changes
between 12- and 16-bit. It is the RAW16 output path.

⚠ **None of the six DNGs carries `ActiveArea`, `DefaultCropOrigin`, `DefaultCropSize` or
`MaskedAreas`** — all four tags absent. So a converter treats the OB rows as image, and
**every 16-bit ClearHDR DNG renders with a black bar across the top**: 20 rows at 4K, 10
binned. The 16-bit and 12-bit modes also differ in field of view by those 20 rows.
**Raise it as its own cinemate/cinepi-raw thread; do not bundle** (§4). The right fix is
to emit `ActiveArea` plus `MaskedAreas` — DNG has those tags for exactly this, and
`MaskedAreas` would additionally let a converter derive per-frame black level from the OB
band.

The offset is **even in raw pixels**, so the CFA phase is preserved and no colour phase is
swapped. `tools/diagnose.py` now measures it and co-registers automatically.

**It does nothing to a patch plateau and everything to a patch border.** Scanned: every
ramp patch is flat to <0.3% from −56 to +8 raw rows, so the existing `patches.py` boxes are
already inside the plateau in every take and **§3.0, §3.0b and §3.1 stand unchanged** —
correcting the offset moves the ramp G means by ≤0.17% and the worst ramp ratio, grey1 R/G
in mode 3, by 0.5%. But the plateau **cliffs at +16** (grey6 falls 0.7% at +16, 8.5% at
+56), so the margin is one-sided. Anything that pairs a 12-bit take with a 16-bit take
region-by-region must co-register first.

### Black level — measured for all six modes, `takes/ccmp-c0-6mode`

| mode | tag | R | G1 | G2 | B | σ/px |
|---|---|---|---|---|---|---|
| 0 | 200 | 201.06 | 201.05 | 201.14 | 201.15 | 1.01 |
| 1 | 200 | 200.99 | 200.98 | 201.08 | 201.08 | 1.92 |
| 2 | 200 | 201.39 | 201.36 | 201.63 | 201.65 | 1.69 |
| 3 | 200 | 198.70 | 198.73 | 198.75 | 198.71 | 2.30 |
| 4 | 3200 | 3201.66 | 3201.63 | 3201.99 | 3201.98 | 2.87 |
| 5 | 3200 | 3199.15 | 3199.17 | 3199.19 | 3199.16 | 1.90 |

**Every mode sits on its tag.** Max deviation −1.3 codes. Per-channel spread inside a mode
≤0.3 codes. Independently corroborated by §3.0b's same-class fits (mode 0↔1 gives 199.8–203.4,
mode 4↔5 gives 3199.0–3199.4).

> ### ⚠ Modes 3 and 5 are CLIPPED AT BLACK. Their lens-cap means are biased low.
>
> Measured 2026-08-07. In **4K ClearHDR only**, not one pixel in a dark frame exceeds
> `BlackLevel`:
>
> | mode | % above BL | max | % exactly on BL |
> |---|---|---|---|
> | 0 binned SDR | 73.8 | +87 | 21.6 |
> | 1 **4K** SDR | 61.5 | +154 | 18.5 |
> | 2 binned HDR | 74.8 | +64 | 14.5 |
> | **3 4K HDR 12b** | **0.000** | **exactly 200** | **55.0** |
> | 4 binned HDR 16b | 66.5 | +246 | 6.4 |
> | **5 4K HDR 16b** | **0.000** | **exactly 3200** | **64.7** |
>
> Uniform across rows and across all four CFA phases. It is the intersection of 4K **and**
> ClearHDR — 4K SDR is clean, binned ClearHDR is clean.
>
> **The −1.3-code "max deviation" above is modes 3 and 5, and it is this clipping, not a
> real black offset.** The mean of a distribution whose upper half is pinned to the pedestal
> sits below the pedestal. So for the full-res modes the lens cap **cannot** serve as ground
> truth for the pedestal — which is exactly what §3.2 has to pin. Modes 0, 1, 2 and 4 are
> unaffected and still corroborate their tags.
>
> **The legs are unaffected.** The clamp is at black; the chart data sits 3–5× above it.
> §3.2a stands.
>
> Likely cause, not yet confirmed on hardware: our fork sets `hdr_thresh_def = {512, 1024}`
> and writes `th[0]→EXP_TH_H`, `th[1]→EXP_TH_L`, giving **EXP_TH_H < EXP_TH_L**, which
> AppNote §4.2 marks Prohibited — upstream's note on that exact condition says the sensor
> "enters an invalid state and **only outputs the BLC pedestal**". Upstream default is
> `{0x0FFF, 0x0000}`. Confirm by re-shooting a cap with the thresholds corrected.

> ### ⚠ FALSIFIED: "defect A — `BlackLevel` is wrong"
>
> A previous pass reported lens-cap black of 224.5–232.5 with a 4.8-code G1/G2 split, and
> concluded `BlackLevel 200` was wrong for modes 2 and 3. **That is not true.** Those figures
> came from `takes/ccmp-c0*`, whose σ/px was 22.7–49.0 against 1.0–2.9 on clean caps — the
> signature of a light leak, not a dark frame. Those takes have been deleted.
>
> Substituting the new measured black changes §3.1 flatness by 0.3 points, i.e. nothing.
> **There is no black-level bug. There is one defect, and it is the transfer curve.**
>
> The old σ = 22.7 was also the sole evidence for "black sits on a 1:1 segment below knee1".
> That conclusion **survives**, on better evidence: the measured curve below has slope 1 from
> L = 0 and passes through code 200 at L = 0, which is exactly where the lens cap reads.

### The curve — measured, both modes

From G-channel secants between adjacent patch pairs plus the register values. **No fitting.**

```
stored_code = ccmp(b·L)/b + 200          b = 4 (binned), 1 (full res)
                                         L = linear signal above black, 16-bit domain

ccmp(x) = x                       x ≤ 500
        = 500 + (x−500)/64        500 < x ≤ 11500
        = 671.875 + (x−11500)/16  x > 11500
```

| | mode 3 (full res) | mode 2 (binned) |
|---|---|---|
| measured knots, L domain | 500 and 11500 | 125 and 2875 — exactly /4 |
| measured slopes | 1, 1/64, 1/16 | 1, 1/64, 1/16 |
| slope-1 segment | visible | below the darkest patch |
| predicts R/G and B/G to | ≤0.9% / ≤1.4% | ≤0.6% |
| predicts G stored code to | ≤1.2 codes of 699–1057 | ≤1.2 codes of 331–1034 |

The knot pedestal comes out at 199.3 and 200.1 — **it is the `BlackLevel`**.

**Defect B is the transfer curve and nothing else.** A description built only from G-channel
secants predicts the R and B ratios across the whole ramp. No colour-dependent term is
needed, and none is permitted.

### What that proves

1. **The curve's shape is measured**, in both the stored-code and linear domains, on both
   modes, replicated across two sessions.
2. **§13.3's "companded black ≈ 542" is FALSIFIED.** Measured 200.
3. **Binning interacts with companding.** The knees sit 4× apart in the delivered-linear
   domain because the CCMP input is the binned (summed) signal. §3.2 predicted this outcome
   as a possibility; it happened.
4. **`ccmp_decode` is ONE GENERATOR, TWO TABLES.** The inverse is
   `L = ccmp⁻¹(b·(code − 200))/b`, which depends on `b`. At code 400 that is 200 for mode 3
   and **3387.5** for mode 2. A DNG `LinearizationTable` takes no mode parameter.

   > ⚠ **This read 4925 until 2026-08-07 and 4925 is wrong.** It mixed the binned
   > L-domain knot 2875 with the *un-binned* code-domain knot 671.875 and dropped the final
   > `/b`: `2875 + (800 − 671.875)·16 = 4925`. Straight from the forward model instead —
   > `C = ccmp(b·L)/b + 200`, so `ccmp(4L) = 4(400−200) = 800`, `4L = 11500 + (800−671.875)·16
   > = 13550`, `L = 3387.5`. A hand-written golden value, which §4 forbids. Derive it.

---

## 3. The method — §3.0, §3.0b and §3.1 are DONE

Run everything through `tools/`. See `README.md` for the tool table.

```
python3 tools/patches.py takes/<set>/*/ --json p.json
python3 tools/gates.py p.json          # §3.0 and §3.0b
python3 tools/neutrality.py p.json     # §3.1
```

### 3.0 Uniformity gate — **PASSED**

| mode | W top-right | W bottom-left | disparity |
|---|---|---|---|
| 4 | 11664.2 | 11760.2 | +0.82% |
| 5 | 12493.6 | 12575.7 | +0.66% |

Illumination is even to **under 1%** across the chart diagonal. Modes 0/1 cannot be gated in
the 17:05 set — both white chips are clipped.

The **black** illumination pair disagrees by −17% of itself, but that is −0.76% *of white*
and **opposite in sign** to the white pair. A lighting gradient moves both the same way, so
this is **local flare**, not lighting: the top-right black chip is hemmed in by the big white
band and the white chip, the bottom-left one sits in the chart's dark corner.

**Carry forward:** a position-dependent flare pedestal of order 1% of white. It makes
`big3_dgrey` and `big4_gloss` unreliable to ~1.4% and it is why the gloss black is a flare
probe and never a calibration anchor.

### 3.0b Scope test — **PASSED, full ramp**

Do modes 0, 1, 4 and 5 already agree? Yes, everywhere.

| patch | R/G spread | B/G spread | |
|---|---|---|---|
| grey1 … grey4 | 0.07–0.49% | 0.07–0.30% | 17:05 set |
| grey5 | 0.41% | 0.32% | 18:37 set, needs un-clipped 0/1 |
| grey6 | 0.34% | 0.35% | 18:37 set |
| big1_white | 0.36% | 0.32% | 18:37 set |
| big3_dgrey, big4_gloss | 1.0–1.5% | 1.3–1.4% | the two flare-exposed patches |

Measurement floor from same-class pairs (mode 0↔1, mode 4↔5): **0.2% max, 0.07% rms.**

**Scope confirmed. Only modes 2 and 3 are broken.**

### 3.1 Neutrality vs level — **DONE, replicated**

> **R/G and B/G must be flat across the neutral ramp if and only if the decode is correct.**

Within-frame ratios, so no reference values, no exposure ratio, no `Y` column, and immune to
scene drift. Ramp = the 6 ladder steps plus 3 of the 4 large chips; **the high-gloss black is
excluded** (§1 property 3).

| mode | | R/G flatness | B/G flatness |
|---|---|---|---|
| 0, 1 | SDR 12 | 4.3% | 5.7–5.9% |
| 4, 5 | linear 16 | 4.4–4.5% | 7.0% |
| **2** | **CCMP 12 binned** | **51%** | **63%** |
| **3** | **CCMP 12 full res** | **31%** | **38%** |

Both sessions agree to ~0.5 points.

⚠ **The instrument floor is not zero.** The linear modes give 4.4/7.0 over the full ramp, all
of it at the two darkest patches and the white chip — flare and chart non-neutrality, not
pipeline. **Over the five mid-range patches (2861–10960) the linear modes are flat to
1.3% R/G and 0.9% B/G. That is the floor, and it is the target for modes 2 and 3.**

Modes 2 and 3 have **different shapes** — mode 2 falls monotonically, mode 3 rises to a peak
at `big3_dgrey` then falls. Same sensor mode, same chart, same light; only binning differs.
That is the visual proof that one table cannot serve both.

### 3.2 The direct transfer measurement — **DONE. `b` and the pedestal both solved.**

Takes 2↔4 (binned) and 3↔5 (full res) are the same chart under the same light at the same
exposure, differing only in sensor bit depth. Every patch yields a `(linear, CCMP code)` pair
directly onto the transfer curve. Assumes nothing.

`tools/fitcurve.py` (one leg), `tools/fit_all.py` (all four, both sessions),
`tools/robust.py` (the knobs). Results in `evidence/fit-3.2.json`. **Answer first:**

| | binned 2↔4 | full res 3↔5 |
|---|---|---|
| **`b`, solved** | **4.0045** / **4.0032** | **0.9979** / **0.9952** |
| `b` without any register value | ratio of the two legs' knots = **4.0097** / **3.9942** | |
| **pedestal, solved** | 200.37 / 200.33 | 200.38 / 201.21 |
| slopes, fitted free | 1/63.94…1/64.03, 1/15.98…1/16.00 | 1/63.81…1/64.17, 1/15.99…1/16.05 |

Two figures per cell = 17:05 / 18:37, **fitted separately and never merged**. Predicted: 4, 1,
4, 200, 1/64, 1/16.

#### 3.2a Is each leg a function? — **PASSED, all four legs, all four CFA phases**

`tools/diagnose.py`, co-registered, 8×8 blocks on the phase plane. Residual is measured
about a local quadratic, so the A-spread that the B-spread inside a bin legitimately
explains is removed first; `noise` propagates both takes' frame-to-frame scatter, B's
through the local slope.

| leg | session | blocks used | resid/noise, median | max | worst A-spread in a bin | half-to-half at matched B |
|---|---|---|---|---|---|---|
| 2↔4 binned | 17:05 | 1884 | **1.0** | 2.1 | 1.27 codes = 0.31% | 0.14% |
| 3↔5 full res | 17:05 | 11497 | **1.0** | 2.0 | 4.62 codes = 1.73% | 0.19% |
| 2↔4 binned | 18:37 | 1867 | **1.1** | 1.4 | 1.83 codes = 0.49% | 0.14% |
| 3↔5 full res | 18:37 | 10941 | **1.1** | 2.1 | 5.74 codes = 2.09% | 0.21% |

**resid/noise ≈ 1 is the measurement floor.** Every leg is a function to within its own
photon noise. The full-res legs' larger absolute spread is entirely the slope-1 segment,
where the 16-bit take's own noise passes through at gain 1 — those bins read
resid/noise 0.8–1.8. Compare §4's void shutter bracket: 10–114 codes against ~1 code of
precision. **All four legs are legitimate to fit.**

Co-registration is what makes this true. Unfiltered, every block including every patch
border:

| leg | not co-registered | co-registered |
|---|---|---|
| 2↔4 17:05 | 656 codes, resid/noise 245 | 54 codes, 24 |
| 3↔5 17:05 | 325 codes, 235 | 85 codes, 5 |
| 2↔4 18:37 | 612 codes, 196 | 63 codes, 15 |
| 3↔5 18:37 | 350 codes, 165 | 83 codes, 6 |

> ⚠ **The table above was produced with a broken offset on two of the four phases, and the
> conclusion survives anyway.** `diagnose.measure_offset` searched **per CFA phase**. On the
> full-res leg's R and B planes it does not find the peak — it walks to the corner of its
> ±16 search box and returns `dy=+16 dx=−16` at **r = −0.29**, instead of `dy=−10 dx=0`. It
> does not raise. The binned leg and G1/G2 were unaffected (r = 0.98 and 0.14).
>
> The crop origin is a property of the **readout**, so one offset serves all four phases.
> `measure_offset_luma` correlates the 4-phase mean instead: single clean peak at
> **dy = −10.00** (parabolic sub-step −9.99 → −19.99 raw rows), against §2's model-free
> white-band anchor of −19.83. `leg()` now uses it; the per-phase function is kept and
> marked deprecated.
>
> Re-run of the full-res leg with the correct offset: **resid/noise median 1.1 on all four
> phases** (max 1.3 R, 2.1 G1, 2.1 G2, 1.6 B). §3.2a stands.

#### 3.2b What the legs already show, before any fit

Slopes read straight off the local fits, no model assumed, register values not used:

| | mode 2 (binned) | mode 3 (full res) |
|---|---|---|
| slope-1 segment | not reached — darkest patch is L ≈ 235, knee1 is L = 125 | **0.98–1.00** measured, L ≈ 165–450 |
| middle segment | **0.0124–0.0167** | **0.0148–0.0168** |
| high segment | **0.0588–0.0637** | **0.0570–0.0575** |
| knee1 | below the data | transition at L ≈ 470–590 |
| knee2 | transition at L ≈ 2735–4000 | transition at L ≈ 10000–12600 |

1/64 = 0.015625 and 1/16 = 0.0625. The knots land on **125 / 2875** binned and
**500 / 11500** full res — §2's `b = 4` and the register values, confirmed independently.

⚠ **Region means are biased near a knee.** Within-block photon noise straddles the knee
even when the block mean does not, and averaging does not commute with a bend, so the
measured knee is rounded over roughly the pixel noise width. Place the knots from the
registers and the segment slopes; do not read them off the rounded transition.

#### 3.2c The fit — **`b` and the pedestal SOLVED, both free, both sessions**

**The method, in one line:** fit the three segments *away* from the knees, let the knots
fall out of the slope intersections, then read `P` and `b` off the knots. Nothing is fixed —
the slopes 1, 1/64 and 1/16 are predictions to be checked, not inputs.

**The knee guard is physical, not a fudge factor.** A block is contaminated exactly when its
pixels straddle the bend, so the guard is `k × σ_within` **per block**, using that block's
own measured within-block spread. It widens by itself on a patch border and at the bright
end, and collapses to nothing on a dark plateau. For Gaussian pixel noise the residual
mean-vs-bend bias is 0.4 codes at k=2 and 0.02 at k=3; k=3 is used.

**The phases are not interchangeable.** `AsShotNeutral` is `0.625 1 0.5263`, so raw R and B
sit at 0.63 and 0.53 of G for the same patch. **R and B reach below knee1 and own `t1` and
the pedestal; only G reaches above knee2 and owns `t2`.** A phase that does not reach a knot
reports `--`, never a number it did not measure.

| | 17:05 | 18:37 | predicted |
|---|---|---|---|
| **binned, `b` = 11500/t2**, 4 phases | **4.0045** (4.0000–4.0106) | **4.0032** (3.9991–4.0088) | 4 |
| **full res, `b` = 500/t1**, 4 phases | **0.9979** (0.9943–1.0033) | **0.9952** (0.9872–1.0052) | 1 |
| **full res, `b` = 11500/t2**, G1+G2 | **0.9977** | **1.0017** | 1 |
| `t1` full res, R / B | 502.04 ±0.11 / 498.37 ±0.12 | 500.29 ±0.16 / 497.39 ±0.17 | 500 |
| `t2` full res, G1 / G2 | 11526.9 ±18.7 / 11525.2 ±17.7 | 11480.4 ±25.0 / 11481.1 ±24.3 | 11500 |
| `t2` binned, 4 phases | 2867.4–2875.0 | 2868.7–2875.6 | 2875 |
| **pedestal**, full res, seg0 slope≡1 | **200.38** (199.54–202.43) | **201.21** (200.58–202.90) | 200 |
| **pedestal**, binned, register-anchored | **200.37** (200.22–200.57) | **200.33** (200.20–200.52) | 200 |

**`b` = 4 with no register value at all.** The register thresholds cancel in the ratio of the
two legs' knots: `t2(full res)/t2(binned)` = **4.0097** (17:05) and **3.9942** (18:37).

**The pedestal is measured free on the full-res leg** — `P` is the mean of `A − x` over the
slope-1 segment, and no register or tag enters it. It lands on 200. On the **binned** leg `P`
and `t1` are degenerate (only `a1 = P + t1(1−m1)` is measured, because mode 2's darkest patch
sits above its own knee1), so there `P` is quoted **given** the register `T1` — a consistency
check, not an independent measurement. Both are reported; neither was put there.

#### 3.2d Zero-free-parameter closure — the test that matters

Predict every used block from `P = 200` (the tag), `b = 4`/`1`, knots `500`/`11500` and
slopes `1/64`, `1/16` — **all register or tag values, nothing fitted.**

| session | binned 2↔4 | full res 3↔5 |
|---|---|---|
| 17:05 | **0.37 codes rms** (0.08–0.15% of A) | **1.43** (0.17–0.28%) |
| 18:37 | **0.37 codes rms** (0.09–0.13% of A) | **1.91** (0.22–0.36%) |

Blocks *at* the knees were never fitted and are reported separately. Their mean residual
carries **the sign of the local curvature**, which is the §4 bias measured rather than
assumed: **−3.7 to −4.7 codes** on full res, where the concave knee1 (slope 1 → 1/64)
dominates, and **+0.9** on binned, where knee1 is below the data and only the convex knee2
(1/64 → 1/16) is in range.

#### 3.2e Robustness — the answer does not come from the knobs

| knob | swept | effect on `b` | effect on `P` |
|---|---|---|---|
| `kguard` | 2 → 6 | binned 3.999–4.012 flat; full-res R 0.995–1.000 | ±0.5 codes |
| seed | 26 deliberately wrong **ordered** knot pairs | 10–22 of 26 reach the mode; **spread among them 0.00–0.07 codes** | — |
| block size | 4, 6, 8, 12 | full-res R 0.9961→0.9963; binned 4.003–4.011 | ±0.2 codes |
| B's black | lens-cap measurement vs tag | <0.002 | **+0.85 codes, exactly the 1:1 sensitivity** |
| tile bootstrap | 150 draws, 0 degenerate | sd 0.0009–0.0025 (binned, full-res R); 0.0073–0.0119 (full-res G) | sd 0.04–0.14 |

Block size 16 is the one outlier (binned G1 → 3.876) and it is small-N: 0.3 k blocks against
2–16 k at every other size. The seeds that do not reach the mode return **NaN**, not a wrong
number — that is the ordering test below.

**Two traps this fit hit, both now guarded in the tool:**

- **A crossing outside the gap the two segments bracket is an extrapolation, not a knot.**
  Without that test the binned leg — which has *no* data below its knee1 at x = 125 — still
  populated segment 0 as the iteration wandered, fitted a line, passed the slope-separation
  test and returned `t1 = 814` with a pedestal of **−478**. The test must be applied to the
  **converged** solution only: as a gate inside the loop it freezes the iteration before it
  can converge, because the early segments legitimately straddle a bend on the way in.
- **Do not ask the plateau filter of the A plane as well as the B plane.** It is
  segment-asymmetric: on the slope-1 segment a 20-code scene step is a 20-code A step and
  fails, on the 1/64 segment the same step is 0.3 codes and passes. That filters the low
  segment far harder than the middle one — and biases exactly the comparison the fit exists
  to make.

**Open, not blocking.** The B phase reads the full-res pedestal ~2.4 codes above R and G,
consistently in both sessions. `P` is 1:1 sensitive to the 16-bit take's black, and the
lens-cap set was shot 1.5 h after the chart, so a ~2-code black drift accounts for it. Not
resolved; it does not move any conclusion.

### 3.3 The controls — **DONE. No fourth segment. `b` confirmed independently.**

Takes 0↔2 and 1↔3 are the same resolution and the same output depth, differing only in
ClearHDR. §3.2's legs held ClearHDR **fixed** on both sides, so its dual-exposure blend was
common mode and cancelled; §3.3's legs are the only pair in the data set that can see it.

The model gains one free parameter over §3.2's:

```
A = P + ccmp(b·g·x)/b      x = mode 0/1 code above its own black (both takes 12-bit)
                           g = the SDR -> ClearHDR sensitivity ratio -- SOLVED, never
                               taken from the nominal exposure ratio
slopes  g, g/64, g/16      knots  t1 = T1/(b·g),  t2 = T2/(b·g)
```

**`b` and `g` enter the knots only as the product `b·g`.** The knots alone can never separate
them. The **slopes** do — three estimates, `m0`, `64·m1` and `16·m2`, all register-anchored —
and `b = T1/(t1·g)` then follows. That is what makes §3.3 an independent determination of `b`
rather than a second opinion on §3.2's arithmetic.

#### 3.3a Registration and the function test — **PASSED, all four pairs, all four phases**

Both takes in a §3.3 pair are 12-bit, so they carry the same 20-row offset and it cancels.
`measure_offset_luma` returns **dy=0 dx=0** on all four, peak r 0.90/0.98 binned and
0.19/0.23 full res, margin positive. `diagnose.py`: resid/noise median **1.0–1.3**, max 2.8.
Every pair is a function.

#### 3.3b The clipping guard — a mean cannot report clipping

Modes 0 and 1 in the 17:05 set have **8.8–11.3% of every CFA phase pinned at exactly 4095**,
with no soft roll-off (`>=4090` and `>=4095` differ by 0.01 points). A block 30% pinned has a
mean far below white and sails through `B_mean < white*0.999` — biased, one-sided, and by far
more than the knee rounding of §4.

`block_stats` now returns a per-block **saturated-pixel-fraction** plane and both tools reject
on it. It is load-bearing, not cosmetic:

| satmax | 17:05 binned | 17:05 full res | 18:37 binned | 18:37 full res |
|---|---|---|---|---|
| 0.00 → 0.25 | 4.0501 | 1.0003–1.0004 | 4.0191 | 1.0338 |
| 0.50 | 4.0492 | 1.0022 | 4.0191 | 1.0338 |
| 1.00 (guard off) | **fails to fit** | 0.9909 | 4.0191 | 1.0338 |

**18:37 is the control** — it has no clipped pixel anywhere — and it does not move a digit at
any threshold. 17:05 is flat over a 12× range of threshold and then breaks. `--satmax` sweeps
it; `knot_tol` 0.02→0.20 and `kguard` 2→6 are flat too.

#### 3.3c Is there a FOURTH SEGMENT? — **NO.** Measured on a leg with no companding in it

Do not ask §3.3's legs, which see the blend multiplied into the three CCMP segments. Ask
modes 4/5 against modes 0/1: **both linear, so the blend is alone and there is no CCMP
anywhere.** `tools/blend.py`. `L = K + g·x`.

| | 17:05 binned | 17:05 full res | 18:37 binned | 18:37 full res |
|---|---|---|---|---|
| `g` | 1.7628 | 1.8853 | 11.2624 | 11.9570 |
| `K`, free, should be 0 | −1.0 … +1.1 | +1.8 … +4.5 | +14.3 … +17.2 | +18.8 … +22.7 |
| L covered | 145–6580 | 145–6797 | 137–**13831** | 145–**14722** |

Four independent tests, and they agree:

1. **18:37's blend leg is a straight line to ±10 codes out of 13831 — 0.07%** — over an L
   range that spans knee2 for *both* values of `b`. Best free split at x = 64–123 with a
   slope change of 0.6%.
2. **The best free breakpoint lands somewhere different on every phase and both sessions**
   (392–695 at 17:05, 64–123 at 18:37; slope ratio 0.994–1.015). A knee does not move.
3. **Lever-arm controlled, the two sessions' residual profiles anti-correlate** (−0.55 binned,
   −0.69 full res). A real knee reproduces *positively and in the same bin*.
4. `K` lands on mode 4/5's own black with no parameter spent on it.

The 17:05 wander (±15 codes) is a per-session systematic, not the sensor: the clean session is
4× flatter over the same L range, and the residual correlates with neither `x` (r ≈ −0.13…0)
nor block position.

**Session ratio: 6.389 binned, 6.342 full res** — the ×6.3 SDR stop-down, measured, and
confirmation that the shutter change reached the SDR modes only.

> ⚠ **`g` is ~1.8 at 17:05, not ~1.** The brief for this pass predicted g ≈ 1 at 17:05 and
> ≈ 6.3 at 18:37. The *ratio* is right (6.34–6.42); the absolute value is not. ClearHDR is
> ~9× less sensitive than SDR at matched settings and that factor lives in `g`. Every knot
> therefore sits lower in `x` than predicted, and **knot ownership per leg is different from
> what the brief said** (§3.3d). Measured, not assumed — which is why the brief says to solve
> for `g` and never take it from the nominal ratio.

#### 3.3d Which leg owns which knot — measured, not predicted

| session | leg | x range | t1 | from | t2 | from |
|---|---|---|---|---|---|---|
| 17:05 | 0↔2 binned | 130–2962 | -- | anchored | **1616.88** | R G1 G2 B |
| 17:05 | 1↔3 full res | 129–2977 | **264.69** | R G1 | -- | -- |
| 18:37 | 0↔2 binned | 20–1229 | -- | anchored | **253.81** | R G1 G2 B |
| 18:37 | 1↔3 full res | 19–1231 | **40.34** | R G1 G2 B | **960.68** | G1 G2 |

**18:37 full res reaches both knots** and is the richest leg in the data set for §3.3.

#### 3.3e The answer

| session | leg | `g`, from the slopes | `g`, from the blend leg | `b` | `P` |
|---|---|---|---|---|---|
| 17:05 | 0↔2 binned | **1.7562** (1.7447–1.7692) | 1.7628 | **4.0501** (4.0222–4.0887) | 201.78 |
| 17:05 | 1↔3 full res | **1.8884** (1.8825–1.8942) | 1.8853 | **1.0004** (0.9970–1.0038) | 203.36 |
| 18:37 | 0↔2 binned | **11.2735** (11.2503–11.3005) | 11.2624 | **4.0191** (4.0097–4.0252) | 201.04 |
| 18:37 | 1↔3 full res | **11.9912** (11.9495–12.0389) | 11.9570 | **1.0012** (t2) / 1.0338 (t1) | 201.26 |

**The two independent routes to `g` agree to 0.1–0.4%**, and the blend leg never touches a
knee — it is a straight-line fit on two linear takes.

**`b` = 4 binned and 1 full res again, now from `t1` and `g` rather than `t1` alone.**
And without any register value at all, from the ratio of §3.3's own two legs' knots corrected
by their `g`: **4.0126** (4.0040, 4.0212) at 18:37.

**The gate's strong test passes.** The two sessions agree on `b` (4.05/4.02 and 1.00/1.00) and
on `P` (201.8/201.0 binned) while differing on `g` by the exposure ratio, 6.4×.

Zero-free-parameter closure, predicting every used block from `P`, `b`, `g` and the register
knots: **0.10 / 0.28 codes rms** binned, 3.39 / 5.56 full res.

> #### The pedestal on §3.3's legs is amplified by `g` — do not read `P` off segment 0 here
>
> `P = mean(y − g·x)`, so an error δ in the **SDR take's** black moves `P` by **g·δ**. §3.2
> had g = 1 and was immune. §3.3's 18:37 full-res leg has g = 12.
>
> Switching mode 1's black from the lens-cap measurement (200.98) to the tag (200) predicts a
> shift of **−12.4 codes** and delivers **−12.4** — and on 17:05, where g = 1.89, predicts
> **−1.9** and delivers **−1.9**. Mechanism confirmed to the decimal.
>
> So `P_seg0` reads 220.32 on that leg and means nothing. **`P_seg1` reads 201.26** and is the
> one to trust, because it is anchored over a long lever arm rather than at x ≈ 20. Same
> reason `b` from `t1` reads 1.0338 there while `b` from `t2` reads 1.0012. **On §3.3's legs,
> anything anchored at small `x` is black-error amplified; anything anchored at large `x` is
> clean.** The free, unamplified measurement of `P` remains §3.2's full-res leg: **200.5**.

### 3.4 Against §13.3's derived curve — **DONE. Both modes are ROW 2.**

`tools/ccmp_decode.py --report --vs-133 --check`. **Every number in this section came out of
that generator.** Nothing is transcribed and nothing is hand-arithmetic — §4 forbids it and
the retracted `4925` is what happens when the rule slips.

**The rows.** They are referred to by earlier drafts but defined in no surviving doc, so they
are stated here:

| | |
|---|---|
| **row 1** | measured ≡ derived — §13.3 is right as written; **use its inverse** |
| **row 2** | measured = derived **up to a stated domain qualifier** — shape and registers right, semantics need a qualifier |
| **row 3** | measured ≠ derived — discard §13.3; the table comes from measurement only |

**The comparison is mechanical, because §13.3 is the same generator.** §13.3 *is*
`Ccmp(b=1, P=0)` — that is precisely what "the compander sees black-inclusive 16-bit data"
means. Measured is `Ccmp(b=1, P=200)` and `Ccmp(b=4, P=200)`. So §13.3 is not reimplemented
anywhere; it is instantiated, and the difference is two parameters.

Regenerating §13.3's own three numbers from it: companded black `forward(3200)` = **542.1875**
("≈ 542" ✓), `inverse(4095)` = **66270.0** (✓), knees at code **500** and **671.875**, its
knee1 sitting below its own black of 3200 — which is where "knee1 is unobservable" came from.

#### 3.4a Mode 3 (full res, b = 1) — **ROW 2**

**What survives — this part is row 1, and it is the whole shape.**

| §13.3 claim | status | evidence |
|---|---|---|
| three piecewise-linear segments | **SURVIVES** | §3.2b — three segments, slopes fitted free |
| knots at **500** and **11500** | **SURVIVES**, ≤0.5% / ≤0.24% | §3.2c — `t1` 497.4–502.0, `t2` 11480–11527, both sessions |
| slopes **1, 1/64, 1/16** | **SURVIVES**, ≤0.3% | §3.2c — 1/63.81…1/64.17, 1/15.99…1/16.05 |
| the slope-1 low segment exists | **SURVIVES, and is now measured** | §3.2b — 0.98–1.00 over L ≈ 165–450. §13.3 could only assume it; there is no low-slope register |
| the threshold domain is 16-bit linear, ~64× the code | **SURVIVES in SCALE** | the knots land on the register values in L, not in code |
| no binning factor (b = 1) | **SURVIVES**, ≤0.5% | §3.2c `b` = 0.9979/0.9952 from `t1`, 0.9977/1.0017 from `t2`; §3.3e 1.0004/1.0012 independently, from `t1` and `g` |

**What is falsified.**

| §13.3 claim | status | evidence |
|---|---|---|
| the compander's input origin is the **raw pedestal** → companded black **≈ 542** | **FALSIFIED** | §2 — measured **200**, on all six modes, max deviation 1.3 codes. Black is subtracted *before* the compander and the 200 pedestal re-added *after*, in the code domain |
| "knee1 (500) sits below black and is unobservable at any exposure" (§8.8 Note) | **FALSIFIED** | §4. knee1 is at stored code **700** with slope 1 measured below it |
| **the inverse as written**, `L = ccmp⁻¹(C)` | **FALSIFIED — unusable** | at knee1 it returns **11950** where measured is **500**: wrong by **23.9×** |
| `BlackLevel` **3200** | **FALSIFIED as an output-domain tag** | inherits the origin error — and in the only domain where 3200 is right, the table overflows uint16 (§3.4c) |
| `WhiteLevel` **66270** | **FALSIFIED as a tag** — though the *number* is measured-top + 3200 | coincidence of the top segment: both curves run at slope 16 above knee2 and the code offset is 200, so 200 × 16 = 3200 **exactly**. They agree at code 4095 and diverge everywhere below knee2. And 66270 **> 65535** — not representable in a TIFF SHORT at all |

**The call.** Shape and registers right; the domain semantics need a qualifier — the
compander's input origin is **black-referred, not pedestal-referred**. That is row 2 by
definition. It is **not** row 1, because row 1's operative instruction is "use its inverse",
and using it is the one thing that must not be done: 23.9× at knee1.

> The shape-level reading inherited by this pass — "row 1 for mode 3" — is **confirmed for
> `ccmp()` itself and overturned as the row call.** The three segments, both knots and all
> three slopes are §13.3's, to ≤0.5%. The map from stored code to L is not.

#### 3.4b Mode 2 (binned, b = 4) — **ROW 2, with the qualifier stacked twice**

Everything in §3.4a, **plus**: the register thresholds do not apply in the delivered-linear
domain. The compander's input is the **binned (summed)** signal, so the knots land at `T/b`.

| | measured | derived |
|---|---|---|
| `b` | **4.0045 / 4.0032** (§3.2c), **4.0097 / 3.9942** with no register value at all, **4.0501 / 4.0191** independently from `t1` and `g` (§3.3e) | §13.3 has no `b` — it is implicitly 1 |
| `t2` | **2867.4–2875.6**, both sessions, ≤0.26% | 11500/4 = **2875** |
| slopes, delivered domain | 1/63.94…1/64.03, 1/15.98…1/16.00 | **1, 1/64, 1/16** — the `/b` on the output cancels the `×b` on the input, so the slopes are the same for both modes and only the knots move |

§13.3 applied to mode 2 is wrong by **2.6×** at knee1, and puts knee2 at code 671.875 where it
measures **367.97**.

⚠ **Mode 2's knee1 is not directly observed.** Its darkest patch is L ≈ 235; knee1 is
L = 125 (§3.2b). It is constrained by the intercept `a1 = P + t1(1−m1)` with `P` = 200, and by
`b` from `t2`. That is a constraint, not a direct measurement — say so.

**Also from the same doc:** §13.6's "one artifact serves both branches" is true across
log-on/log-off and **false across binning**. Two tables. §5 already says so.

**§13.4's go/no-go table:** the "≈ 542" row is falsified. The "≈ 200" row's *diagnosis* —
"the knee domain assumption is wrong" — is **confirmed**; only its prescription ("do not shoot
the bracket yet") was wrong, and the bracket is what solved the curve.

#### 3.4c The output domain — **forced, not chosen**

A `LinearizationTable` is TIFF type SHORT: entries are uint16, **0–65535**. It also moves
`BlackLevel` and `WhiteLevel` into the **table's output domain**, so both tags must be
rewritten to match. All four candidates, straight from `--report`:

| domain | output | mode 3 | mode 2 | verdict |
|---|---|---|---|---|
| **(a) ABOVE_BLACK** | `L` | −200 … 63070 | −200 … 62507.5 | **REJECTED — at the BOTTOM** |
| **(a′) KEEP_PEDESTAL** | `L + 200` | 0 … **63270** | 0 … **62707.5** | **CHOSEN** |
| **(b) RAW16** | `L + 3200` | 3000 … **66270** | 3000 … **65707.5** | **REJECTED — overflows, BOTH modes** |
| **(c) SCALED** | `(L+200)·s` | 0 … 65535 | 0 … 65535 | admissible, **strictly dominated** |

- **(a) fails at the bottom, not the top.** The brief for this pass had it fitting. It does
  not: stored codes 0–199 decode to L < 0, which a uint16 table cannot hold. A mode-2 dark
  frame puts **10.7% of its pixels** below the pedestal (§2's clipping table: 74.8% above,
  14.5% exactly on). (a) would clip all of them to zero. It also makes the table perform
  black subtraction *as well as* decompanding — not "undoes CCMP and nothing else".
- **(b) overflows for BOTH modes**, not only mode 3: 66270 and 65707.5 against 65535. The
  mode's own range does not fit in a black-inclusive 16-bit container. That is a property of
  the hardware, not a choice.
- **(c) buys nothing.** A converter computes `(L − BlackLevel)/(WhiteLevel − BlackLevel)`;
  since the scale divides out of both, (c) is **arithmetically identical to (a′) after
  normalisation**. It costs a 1..2 step ripple with 0.5 rounding error on the identity
  segment — where the true transfer is exactly 1:1 and any ripple is ours, not the sensor's —
  gives the two modes different `BlackLevel`s (**207** and **209**), and adds a per-mode scale
  constant to carry. Rejected on cost against zero benefit.

**(a′) KEEP_PEDESTAL is the only candidate that fits at both ends for both modes.**

| | mode 3 (b=1) | mode 2 (b=4) |
|---|---|---|
| `BlackLevel` | **200 — unchanged** | **200 — unchanged** |
| `WhiteLevel` | **63270** | **62708** (exact 62707.5) |
| knee1 / knee2, stored code | 700 / 871.875 | 325 / 367.96875 |
| knee1 / knee2, L | 500 / 11500 | 125 / 2875 |

Three properties, each load-bearing:

1. **Only one tag is rewritten.** `BlackLevel` 200 is measured correct (§2) and stays.
2. **The table is the identity on [0, knee1]** — codes 0–700 and 0–325 respectively, asserted
   in `--check`. That is exactly what the compander does there, so the table **undoes CCMP and
   nothing else**, which is what §5 requires, met literally rather than approximately.
3. **One output unit = one 16-bit ClearHDR LSB above black**, i.e. mode 4/5's own scale.
   Verified in the tool, not assumed: `fitcurve.leg_points` sets `x = B_mean − black(B)` on
   the 16-bit take and `y` = the raw 12-bit code, and `g` = 1 on §3.2's legs.

⚠ **The two `WhiteLevel`s differ and must not be forced equal.** 63270 against 62708. Both
knee2 codes carry 16 L per code above them, but they sit at 871.875 and 367.97 — the
difference is that, and it is a consequence, not a bug.

**Rounding is `floor(x+0.5)`, not half-to-even.** Every entry on mode 2's top segment is a
half-integer (`16C − 2812.5`); half-to-even would alternate the step 15/17 and put a visible
ripple in the LUT's slope. `WhiteLevel` is read off `table[4095]` **after** rounding, so tag
and table agree by construction rather than by inspection.

#### 3.4d What the evidence covers — and what it does not

| | mode 3 | mode 2 |
|---|---|---|
| chart's brightest L (§3.3c) | 14722 | 13831 |
| stored codes exercised | 200 … 1073 | 200 … 1053 |
| of the 0–4095 code range | **21.3%** | **20.8%** |
| the 1/16 segment, measured fraction | **6.2%** | **18.4%** |
| decoded top vs mode 4/5's own ceiling (62335 above black) | **1.0118×** | **1.0028×** |

**Above stored code ≈ 1075 the table is extrapolation along a measured slope.** That is sound
— the slope is a register value confirmed to 0.3% over the covered part, and §3.3c showed
there is no fourth segment out to L = 14722 — but it *is* extrapolation, and **the acceptance
gate cannot test it**: the chart never gets there. Worse for the top specifically, the decoded
top exceeds what the 16-bit reference itself can hold, so the last ~1% has no reference even
in principle. Neither blocks the table. Both belong in the write-up when it ships.

---

### 3.5 First decode — the gross defect is gone, a structured residual is not

**Not the acceptance gate.** A first pass of the table through `patches.py --decode auto`
(per pixel, before averaging) and `neutrality.py`, both sessions, `--limit 6`.
`evidence/res2_decode_compare.png` and `evidence/decode_compare_asn.png`.

**The purple is gone**, on both modes and under both white balances — including the honest
`AsShotNeutral` render, which does not flatter the curve the way the per-channel percentile
normalisation does. §3.1 full-ramp flatness:

| | before | after | its linear reference |
|---|---|---|---|
| mode 2 | 51% / 63% | **5.7% / 8.7%** | 4.4% / 7.1% (mode 4) |
| mode 3 | 31% / 38% | **4.2% / 7.1%** | 4.3% / 7.0% (mode 5) |

**But flatness is the wrong instrument** — it cannot see an error shared across the ramp. The
sharp test is §3.0b's: pair each decoded CCMP mode against its own linear reference, patch by
patch. rms of the per-patch R/G and B/G difference:

| pair | 17:05 | 18:37 |
|---|---|---|
| 2 vs 4, decoded | 0.86% / 1.09% | 0.88% / 1.17% |
| 3 vs 5, decoded | 1.49% / 1.74% | 1.43% / 1.72% |
| 0 vs 1, same-class control | 0.05% / 0.09% | 0.07% / 0.14% |
| 4 vs 5, same-class control | 0.06% / 0.08% | 0.08% / 0.06% |

The controls reproduce §3.0b's 0.07% rms floor exactly, so the instrument is sound. The
decoded modes sit **10–20× above it**, and it replicates across both sessions.

**The residual is organised by SEGMENT, not by mode** — which makes it a property of the
compander model rather than of `b`:

| where R and B sit | mode 2 | mode 3 | dR/G |
|---|---|---|---|
| **low** (slope 1) | no data — knee1 is below the ramp | grey1, grey2 | **−3.4%, −2.1%** |
| **mid** (1/64) | grey1 … grey3 | big3 … white | **+0.4% … +1.8%**, decaying with level |
| **high** (1/16) | grey4 … white | no data — knee2 is above the ramp | **+0.02% … +0.11%** |

Mode 3's sign flip lands **exactly where R and B cross knee1** (L = 500), on both sessions.
That is the sharpest structure in the data and it points at the knee1 neighbourhood.

**Ruled out: the 20-row offset.** `patches.py` does not co-register, and §2 requires it for any
12-bit/16-bit region pairing — so it was the first suspect. Re-sampling the 12-bit takes with
their boxes shifted by the measured offset (−10 raw rows binned, −20 full res) moves the
result by **≤0.06 points** and not consistently downward: 0.86 → 0.84 and 1.49 → 1.52. The
patch boxes are inside the plateau, exactly as §2 said. **Not the cause.**

> #### ⚠ It is not new. **§3.2d's closure IS this residual**, in a domain that hides it.
>
> §3.2d reports its closure as an rms in the **code** domain — 0.37 codes binned, 1.43–1.91
> full res — and 0.37 codes reads like nothing. The table inverts, so the same error lands in
> L multiplied by the local `dL/dC`, which is **64 on the middle segment**:
>
> | | low (×1) | mid (×64) | high (×16) |
> |---|---|---|---|
> | mode 2, closure → L | 0.4 | **23.7** | 5.9 |
> | mode 3, closure → L | 1.4–1.9 | **91.5–122.2** | 22.9–30.6 |
> | §3.5's implied additive `d` | — | **21–54** / **21–93** | — |
>
> Same numbers. **The residual was always in the data and the code-domain rms concealed it.**
> So it is not introduced by the table, and the table is not the thing to fix: `ccmp_decode`
> faithfully inverts the model, and the model itself carries this much error on the 1/64
> segment. The high segment matches too — 5.9 L predicted against §3.5's ~3 L measured.

**Diagnosed in §3.6.** Two causes, not one: the middle segment's **anchor** (the curve, and
fixable) and a **per-channel gain on mode 3 alone** (not the curve, and not fixable by any
table).

⚠ **Diagnose it on `fitcurve` residuals, not on patch ratios.** Patch ratios were the right
instrument for finding this and are the wrong one for solving it: nine points, two of them
flare-exposed, against thousands of blocks that already localise a residual by level and by
segment. The blocks are the reason the segment structure above is trustworthy at all.

---

### 3.6 The residual, diagnosed — **mode 2 FIXED, mode 3 is not a table problem**

`tools/closure_L.py`, `tools/anchor.py`, `tools/resid_profile.py`, `tools/resid_why.py`,
`tools/resid_neutral.py`, `tools/blockratio.py`, `tools/sweep_table.py`, `tools/accept.py`.
Evidence in `evidence/closure-L-{regs,anchored}.json`, `anchor-3.2.json`,
`accept-anchored.json`, `tables/`.

#### 3.6a The closure in L — the signed mean is structured, not scatter

§3.2d's closure re-expressed per SEGMENT, per PHASE, both sessions, in L, with the **signed
mean** beside the rms. Register/tag values, zero free parameters.

| | low (×1) | **mid (×64)** | high (×16) |
|---|---|---|---|
| mode 2, 8 leg-phases | no data | **+14.1 … +16.4 L** | +3.5 … +15.6 |
| mode 3, 8 leg-phases | −0.5 … **+2.9** | **+15.3 … +46.8 L** | −29.0 … +25.7 |

Standard errors are 0.06–0.26 L. **The signed mean is 100–300 σ.** It is a model error, not
scatter, and the question the brief posed is answered: report in L or the compression ratio
hides it.

#### 3.6b Three of the four candidates are falsified on the data

| candidate | verdict | evidence |
|---|---|---|
| a hardware **rounding** convention | **FALSIFIED** | the residual against `frac(predicted code)` is flat to **0.017 codes** over 10 bins, on a within-block spread of **1.38 codes** — well dithered, so a rounding rule could not survive averaging anyway. `resid_why.py --test round` |
| **`t1` inside its 497.4–502.0 spread**, scaling as 1/`b` | **HALF RIGHT, AND THE 1/`b` PART IS FALSIFIED** | the anchor is off, but by **0.33** (b=1) and **0.23** (b=4) codes — a ratio of **1.4**, where a pure `T1` error gives 4 and a pure pedestal error 1. It is neither, and one number cannot serve both modes |
| a **soft knee** | **NOT NEEDED** | a sharp corner at the measured anchor reproduces mode 2 to **±1.5 L** across its whole middle segment. §3.5's "mode 3 sign flip at knee1" is the step itself, not curvature |
| a **per-channel gain** between the paired takes | **SURVIVES — on mode 3 only** | §3.6d |

**§3.2e's B-phase pedestal is confirmed real and is NOT the cause.** The low segment reads
B **+2.39 / +2.82** codes above R and G, both sessions — §3.2e's ~2.4, now measured to
±0.15. The feared ×64 amplification **does not happen**: B's middle-segment anchor sits
0.03–0.07 codes from G's, not 2.4. The anchor is measured against the model's identity line,
not inherited from a fitted low segment, so a black error passes into it divided by 64. It
stays an open thread (§6) and it moves nothing here.

#### 3.6c The cause, part 1 — the middle segment's ANCHOR

The middle and high segments both hang off one number:

```
a1 = P + T1*(1 - s1)/b        the companded code the middle segment extrapolates to x = 0
```

`P`, `T1` and `b` enter those two segments **only through `a1`**, so on them the three are
**degenerate** — no mid-segment data can separate a pedestal error from a threshold error
from a binning error. What the data does determine is `a1`. Fitted as a line in `x` so the
level-dependent term cannot contaminate it, and read at the knot:

| `delta_c` = a1(measured) − a1(register+tag) | R | G1 | G2 | B | mean | spread |
|---|---|---|---|---|---|---|
| **b = 1**, 17:05 | 0.3404 | 0.3156 | 0.3105 | 0.3400 | **0.3266** | 0.030 |
| **b = 1**, 18:37 | 0.3316 | 0.3185 | 0.3207 | 0.3914 | **0.3406** | 0.073 |
| **b = 4**, 17:05 | 0.2334 | 0.2181 | 0.2182 | 0.2435 | **0.2283** | 0.025 |
| **b = 4**, 18:37 | 0.2409 | 0.2258 | 0.2274 | 0.2494 | **0.2359** | 0.024 |

**The two sessions agree to 0.014 and 0.008 codes.** Written on `T1` with `P` held at the
measured tag 200 and `b` at the design value — **that assignment is a choice, not a
measurement**; the same `a1` is a pedestal of 200.33/200.23 or a `b` of 0.9993/3.992, and the
table is bit-identical either way. It is written on `T1` because it is the only one of the
three the identity segment does not contradict.

```
T1_eff = 500.3389  (b = 1, mode 3)          T1_eff = 500.9431  (b = 4, mode 2)
```

**The closure re-run in L, same zero free parameters plus the anchor:**

| | low | **mid** | high |
|---|---|---|---|
| mode 2 | no data | **+14.1…+16.4 → −0.7 … +1.5 L** | +3.5…+15.6 → −0.2 … +11.9 |
| mode 3 | unchanged, by construction | **+15.3…+46.8 → −6.1 … +25.5 L** | −29…+26 → −34 … +20 |

**Mode 2 collapses onto zero on all four phases and both sessions.** Mode 3 improves by 21 L
and keeps a **20–24 L spread between its channels**, which is §3.6d.

Mode 3's high segment is dominated by `t2`, which reads **11527 (17:05)** and **11480
(18:37)** — it **flips sign between the sessions**, so it is measurement scatter on a
register value, not a model error. `T2` stays at 11500.

**Cross-validated across sessions** — `accept.py --xval`. The anchor is fitted on the same
takes the gate is measured on, and the two instruments are already different (thousands of
blocks over the whole frame against nine hand-placed patch boxes decoded per pixel), but the
takes are shared and only a split tests that.

| anchor fitted on | gate on | m2 dR/G | m2 dB/G | m3 dR/G | m3 dB/G |
|---|---|---|---|---|---|
| 17:05 | 17:05 | 0.056% | 0.118% | 0.221% | 0.621% |
| 17:05 | **18:37** | **0.048%** | **0.066%** | **0.202%** | **0.554%** |
| 18:37 | **17:05** | **0.056%** | **0.118%** | **0.210%** | **0.604%** |
| 18:37 | 18:37 | 0.048% | 0.066% | 0.189% | 0.536% |

**Out of sample is indistinguishable from in sample** — mode 2 agrees to three decimals,
mode 3 to 0.02 points. The two single-session anchors differ by 0.014 (b=1) and 0.031 (b=4)
codes, i.e. 0.9 L and 0.5 L on the middle segment. **The anchor is not fitting session noise.**

#### 3.6d The cause, part 2 — mode 3 carries a per-channel gain, and no table can remove it

**The transfer is per pixel and phase-independent** (§2: "no colour-dependent term is needed,
and none is permitted"). So a residual that differs between channels **at the same L** is not
the curve. Three tests, each tighter than the last:

1. **At matched L on the middle segment**, the four phases' residual spreads from 5 L at
   L = 730 to **46 L at L = 7100**, both sessions, ordered B > R > G1 ≈ G2 with G1 and G2
   agreeing to **<1 L**.
2. That could still be "different patches at the same L", so: **restricted to blocks whose
   reference ratios are neutral**, the three channels agree to **4–5 L** at L ≈ 750 and
   diverge to **23–43 L** by L ≈ 6300–8000. Same patch class, same L, different channel.
3. **The pair matrix over all 15 mode pairs** (dB/G rms, mid-range) names the outlier:

| row mean, dB/G | m0 | m1 | m2 | **m3** | m4 | m5 |
|---|---|---|---|---|---|---|
| 17:05 | 0.32 | 0.34 | 0.29 | **0.65** | 0.25 | 0.26 |
| 18:37 | 0.46 | 0.48 | 0.32 | **0.71** | 0.31 | 0.32 |

**Mode 3 disagrees with every other mode, including mode 2** (0.46 / 0.50) — which is the
*other* CCMP mode, decoded through the *same generator*. Mode 2 agrees with modes 4 and 5 at
0.07–0.17%, i.e. at their own same-class control. So the defect is in mode 3, not in the
generator.

**It is a gain, not an offset, and that is what makes it unfixable.** Mode 3's residual
against mode 5 is **flat across the ramp** at R **+0.2%** and B **+0.6%** of G. Above knee1
the decode is affine and shared by every channel, so `T1` (or `P`, or `b`) buys an **additive**
shift — which in a ratio decays as `1/G` — and `s1` buys a **multiplicative** scale, which a
ratio does not see at all. Neither is flat-and-per-channel.

Confirmed numerically rather than argued: sweeping `T1` over ±3 codes and `s1` over ±2%,
the **best dB/G reachable anywhere** is **0.52% (17:05) / 0.55% (18:37)**, against a
same-class control of **0.06–0.07%**. `tools/sweep_table.py`.

> ⚠ The sweep's optimum sits at `T1` ≈ 500.5, not the anchor's 500.34 — because it optimises
> the **ratio**, and a ratio metric will happily spend the curve's one free parameter
> absorbing an error that is not the curve's. **The shipped value is the anchor**, measured
> on the level residual over thousands of blocks. That is this pass's brief, met literally:
> fix the model on the block data, keep the patch ratios as the independent check.

#### 3.6e The acceptance gate — `tools/accept.py`

Decoded modes 2 and 3 against their own linear reference, **patch by patch**, with the
same-class controls printed beside them, both sessions. Mid-range = §3.1's five flat patches,
selected **by name** so the ×6.3 SDR stop-down cannot empty the control.

| | mode 2 | mode 3 | ctrl 0 vs 1 | ctrl 4 vs 5 | m2 / band | m3 / band |
|---|---|---|---|---|---|---|
| 17:05 dR/G | **0.06%** | 0.22% | 0.03% | 0.03% | **2.1×** | 8.2× |
| 17:05 dB/G | **0.12%** | 0.62% | 0.03% | 0.06% | **2.0×** | 10.7× |
| 18:37 dR/G | **0.05%** | 0.20% | 0.02% | 0.04% | **1.1×** | 4.7× |
| 18:37 dB/G | **0.07%** | 0.55% | 0.04% | 0.07% | **1.0×** | 8.3× |

Full ramp, against §3.5's numbers for the same measurement:

| | before | after |
|---|---|---|
| 2 vs 4 | 0.86% / 1.09% and 0.88% / 1.17% | **0.18% / 0.20%** and **0.09% / 0.16%** |
| 3 vs 5 | 1.49% / 1.74% and 1.43% / 1.72% | **0.27% / 0.62%** and **0.31% / 0.54%** |

> **Mode 2 sits at 1.0–2.1× the same-class control band**, down from 12–18×. On the 18:37
> session it is **equal to the control** (1.0× and 1.1×); on 17:05 it is 2×. The strict
> `≤ 1.0×` test therefore passes on one of four numbers and misses the other three by a
> factor of two — **on a band whose own two controls differ from each other by 3.5×.**
> Call it what it is: mode 2 has joined the other four modes to within the spread of the
> controls themselves, and it is not `ccmp_decode` that would take it the last 2×.
>
> **Mode 3 has not joined them**, at **4.7–10.7×** the band, and §3.6d is why: what remains
> is flat in level, per channel, and a property of the take rather than of the curve. **The
> table is not the thing left to fix on mode 3.**
>
> `accept.py` prints the strict verdict AND the multiple, and rounds neither away.

Supporting checks, both cheap, both run:

- `evidence/decode_anchored_asn.png` — modes 2 and 3 decoded, beside 4 and 5, under the
  honest `AsShotNeutral` white balance. **The purple is gone and the greys match the
  references.**
- `neutrality.py`, both sessions: mode 2 **4.8% / 6.6%** and **4.8% / 6.9%**, mode 3
  **4.3% / 6.3%** and **5.0% / 6.3%**, against references at 4.3–4.5% / 7.0–7.1%. Sessions
  agree to ≤0.7 points. Flatness is **not** the gate (§4) and is reported only because §5
  asks for it.

---

## 4. Traps — every one of these has already cost a pass

- **Never merge points from the 17:05 and 18:37 sessions into one fit.** They are 1.5 h apart
  and the lamp drifted ~1%. Fit each, then require agreement.
- **Do not use an exposure bracket across separate takes of a live scene.** The 1-stop pair in
  the deleted `ccmp-c0_UHD_*_shutter*` takes failed exactly this way: A-code spread within a
  narrow B bin was 10–114 codes against ~1 code of measurement precision. The relation was not
  a function, so no fit on it was legitimate.
- **Never `analyze_dng.py --ref` across two takes.** Different frames, different photons.
  **Region means only.**
- **Do not convert the Video chart's IRE figures to linear reflectance.** It has no published
  colorimetric data; converting requires assuming the curve under test. Circular.
- **Do not use the ColorChecker Classic `Y` column on this chart.** Different product.
- ~~knee1 (500) is below black and unobservable at any exposure.~~ **FALSIFIED.** That
  inherited §13.3's wrong black. Mode 3's knee1 sits at stored code 699 against a black of
  200, and the transfer curve is per-channel, so R and B — at 0.60 and 0.53 of G — already put
  twelve points below knee1 from the neutral patches alone. knee1 **is** observable.
- **Bracket on shutter, never gain.** Gain steps are nominal and the sensor rounds them.
- **Never hand-write a golden value.** Derive it from registers, the fit, or the generator.
- **If a doc contradicts the hardware, believe the hardware and fix the doc.**
- The modes have **different binning**, so absolute levels differ between resolutions.
  Compare within a frame, or within a matched-resolution pair. Never across.
- **Do not port libcamera's `decompand` block.** It would make AE meter linear, it is absent
  from our tree, and it is a separate thread. Raise it, do not bundle.
- **The 18:37 shutter change reached the SDR modes only.** Separate bug. Do not bundle.
- **Co-register before pairing a 12-bit take with a 16-bit one.** They are 20 sensor rows
  apart (§2). Uncorrected it is invisible on a patch plateau and worth 300–660 codes at a
  patch border — enough to make a legitimate pair look like it is not a function.
  `diagnose.py` does it automatically. **The 20-row offset is itself a separate
  cinemate/cinepi-raw thread. Raise it, do not bundle.**
- **Do not read a knee position off region means.** Within-block noise straddles the knee
  when the block mean does not, and averaging does not commute with a bend, so the
  transition is rounded over about the pixel noise width. Knots come from the registers,
  confirmed by the segment slopes either side.
- **Measure the take offset ONCE PER LEG, off the luma — never per CFA phase.** The crop
  origin is a property of the readout. `diagnose.measure_offset` searched per phase and
  **fails silently on the full-res leg's R and B**, walking to the corner of its search box
  at r = −0.29 and returning `dy=+16 dx=−16` for a take that is `dy=−10 dx=0`. Use
  `measure_offset_luma`; a per-phase answer that disagrees across phases is a failed search,
  not four measurements (§3.2a).
- **A line intersection is only a knot if it lands between the two segments' data.** Two
  lines always cross somewhere. Check it on the CONVERGED fit, never as a gate inside the
  iteration — inside, it freezes the fit before it can converge (§3.2e).
- **Never filter on the A plane and the B plane with the same relative tolerance.** The
  transfer curve is what separates them: a 20-code scene step is 20 codes of A on the
  slope-1 segment and 0.3 codes on the 1/64 segment, so one tolerance filters the two
  segments completely differently (§3.2e).

**Added by §3.3. All five are the same disease — believing a segment the fit invented.**

- **A block mean cannot report clipping.** `mean >= white*0.999` does not reject a block that
  is 30% pinned. Reject on the measured saturated-pixel FRACTION. With the guard off, the
  17:05 binned leg does not fit at all (§3.3b).
- **A segment not bracketed by a real knot is not that segment, and must not contribute a
  slope.** §3.2 could ignore this because its slopes were only a check. In §3.3 the slopes
  carry `g`. Phase R of the full-res leg tops out at 8836 with knee2 at 11500, so there is no
  1/16 segment — but the iteration still fills "seg2" with the upper 1/64 data and fits it
  1/64.10. Ungated that is `g2 = 0.2496`, and it drags `g` 0.999 → 0.531, `b` 0.997 → 1.876,
  `P` 200 → 311. `t2_ok` already knew.
- **A knot's own error bar is part of its acceptance.** `_between` is necessary, not
  sufficient: two chunks of the *same* segment also cross inside their own gap, at an
  arbitrary place, with an error the size of the answer. §3.2's knots came out to 0.02–0.16%
  of themselves; §3.3 throws up `t1 = 121.2 ± 51.2`. That 42% is the tool saying the
  segmentation failed.
- **A rejected knot means the two segments either side of it are ONE segment.** Fitting them
  separately throws away exactly the lever arm that measures their common slope. Merge them.
- **Which knot a crossing is comes from the SLOPE RATIO, not from where the seed left it.**
  The two possible adjacent pairs are separated by 1/64 and by 4 — a factor of 256 apart, both
  register values, with `g` cancelling out of both. Without that test, 17:05's full-res leg on
  G1 put the slope-`g` segment in seg1 and the 1/64 segment in seg2 and reported
  `g1 = 64×1.846 = 118`, `g2 = 16×0.0294 = 0.47`, while phase R of the same leg got it right.
  Nothing in a piecewise-linear fit objects to an off-by-one assignment.
- **Do not inverse-variance weight estimates that disagree.** A spurious segment fitted over a
  long lever arm gets the SMALLEST error bar and therefore the LARGEST weight. That is how
  `g0 = 0.177` outvoted `g1 = 11.19` and `g2 = 11.24`. When the three estimates of `g`
  disagree beyond tolerance the answer is "this phase did not measure `g`", not their mean.
  **Weight is not evidence.**

**Added by §3.4.**

- **"Fits uint16" is a test at BOTH ends.** The brief for this pass had output domain (a),
  `L` above black, fitting: it checked 63070 against 65535 and stopped. It fails at the
  *bottom* — stored codes 0–199 decode to L < 0, and a dark frame puts 10.7% of its pixels
  there. `build()` now rejects on `min < 0` as well as `max > 65535` and **never clamps**: a
  clipped highlight or a clipped shadow is exactly the defect this table exists to remove, so
  a domain that does not fit must fail loudly rather than quietly lose data.
- **A number that matches is not a model that matches.** §13.3's `WhiteLevel` 66270 is
  *exactly* measured-top + 3200 — and the agreement is a coincidence of the top segment, where
  both curves run at slope 16 and the code offset is 200, so 200 × 16 = 3200. The same two
  curves differ by **23.9×** at knee1. Checking a curve at one point, especially at an
  endpoint, is not checking a curve. Compare at every knot and either side of each.
- **Instantiate the rival model, do not reimplement it.** §13.3 is this generator with
  `P = 0, b = 1`. Writing its arithmetic out a second time by hand is how a comparison
  acquires a transcription error and starts adjudicating the wrong two curves.

**Added by §3.5. The most expensive one on the list, because it hid for two passes.**

- **A CODE-domain error metric is the wrong metric for a decompanding curve, and it flatters
  it by the compression ratio.** §3.2d's "0.37 codes rms" reads like a closed case. The table
  inverts, so on the 1/64 segment that same 0.37 is **23.7 L**, and on mode 3 it is
  **91–122 L** — which is the whole of the §3.5 residual. The fit was reported in the domain
  where the error is divided by 64. **Report closure in L, or per segment with `dL/dC` shown
  beside it.** Any error metric for this curve that does not name its domain is meaningless.
- **A flatness number cannot see an error shared across the ramp.** §3.1 flatness put decoded
  mode 3 at 4.2%/7.1% against its reference's 4.3%/7.0% — an apparent pass. The per-patch
  pairing against that same reference reads 1.49%/1.74% rms against a 0.07% control floor.
  Flatness measures spread *within* a take; it is blind to a common offset. **Pair against the
  matched linear reference, patch by patch, and always print the same-class control beside
  it.**

**Added by §3.6.**

- **A residual that differs between CFA PHASES at the same L is not the curve, and no
  re-parameterisation can remove it.** The transfer is per pixel and phase-independent (§2);
  a table takes the stored code and knows no channel. Test it before spending a pass fitting:
  `resid_why.py --test phase`. G1 against G2 is the free internal control — they are the same
  colour, and here they agree to **<1 L** while B and G differ by 46.
- **"The four phases at the same L" is FOUR DIFFERENT PATCHES.** R and B sit at 0.625 and
  0.526 of G, so matching on L unmatches the patch. The disagreement is only evidence once
  the patch class is fixed — restrict to blocks whose REFERENCE ratios are neutral
  (`resid_neutral.py`), and select on the reference, never on the thing under test.
- **Do not let a RATIO metric choose a curve parameter.** Above knee1 the decode is affine
  and common to all channels, so `T1`/`P`/`b` move a ratio only as `d·(1/B − 1/G)` and `s1`
  not at all. Optimising a ratio therefore spends the curve's one parameter absorbing errors
  that are not the curve's: the ratio sweep wants `T1` = 500.5 where the level residual
  measures 500.34 — 10 L bought by fitting the answer (§3.6d).
- **`P`, `T1` and `b` are DEGENERATE on the middle and high segments** — they enter only
  through `a1 = P + T1(1−s1)/b`. Quote the anchor, then say which of the three you wrote it
  on and why. "The threshold is 500.34" without that is over-claiming.
- **A level window is not exposure-invariant.** Selecting the mid-range on the reference's
  own G emptied the 0-vs-1 control at 18:37, where the SDR modes are stopped down ×6.3 — and
  a gate that silently drops its control is worse than no gate. Select by patch name.
- **A block-level instrument has its own floor and it is not §3.0b's 0.07%.** Blocks sweep in
  every patch, border and gradient the hand-placed boxes were chosen to avoid: the linear
  control leg reads 1.6–3.2% rms there against 0.07% on patches. Use blocks to LOCALISE a
  residual by level and segment — that is what they are for — and patches to SIZE it.
- **A correction to the REGISTER curve can only be read against the register curve.**
  `closure_L.py --anchored` without `--regs` is **not** §3.6c: the per-phase fit re-absorbs the
  anchor through its own solved `P` and `b`, and mode 2's middle segment then reads
  **−14.8 L** where §3.6c reads −0.7…+1.5 — the anchor apparently made it ten times worse.
  It did not; the two runs measure different quantities. **§3.6c is `--regs --anchored`.** The
  tool now warns. Generally: a parameter measured as a delta against a fixed baseline is
  meaningless in a fit that is free to move that baseline.

---

## 5. Deliverable and gates

**`ccmp_decode` — one generator, two tables.** One for the binned modes, one for full res.

| 12-bit ClearHDR | Written to the DNG |
|---|---|
| log **off** | `ccmp_decode` **is** the LinearizationTable |
| log **on** | forward = `ccmp_decode` ∘ `log16to10_forward`, precomposed at build time; the file carries the existing, byte-gated `cinemate_log_16to10` table, unchanged |

**The log branch's source domain is 16-bit after decompand, not 12.** It uses the `16to10`
spec, never `12to10`. Getting that wrong is the silent double-companding hazard.

⚠ **"One artifact serves both branches" holds for log-on/log-off. It does NOT hold across
binning.** The decode is `L = ccmp⁻¹(b·(code − 200))/b`. Two tables.

**The tags — settled in §3.4c, re-derived after §3.6c's anchor.** Output domain `L + 200`
(KEEP_PEDESTAL), the only one of the four candidates that fits uint16 at both ends for both
modes. The anchor moves `WhiteLevel` by 4–5 counts and changes nothing else: `ABOVE_BLACK`
still fails at the bottom, `RAW16` still overflows both modes, `SCALED` is still dominated.

| | mode 3 (b=1) | mode 2 (b=4) |
|---|---|---|
| `BlackLevel` | **200 — unchanged** | **200 — unchanged** |
| `WhiteLevel` | **63265** (was 63270 pre-anchor) | **62704** (was 62708) |
| effective `T1` (§3.6c) | **500.3389** | **500.9431** |
| knee1 / knee2, stored code | 700.339 / 872.209 | 325.236 / 368.201 |

§13.3's 3200/66270 pair rested on the same falsified assumption as its 542, and 66270 is
additionally **not representable** in a SHORT. Both tags now come out of the generator.

**The tables are written.** `ccmp_decode.py --emit evidence/tables` — 4096 uint16 entries
each as `.bin` (little-endian) and `.txt`, plus a `manifest.json` carrying both tags and
every curve parameter. **The emit is gated on the self-tests**: it runs `check()` first and
writes nothing if any of the 21 fail.

**Analysis gate:** both direct legs (2↔4, 3↔5) agree, on both sessions; `diagnose.py` says
each pair is a function before any fit; and §3.4 lands in one of its first two rows with a
stated reason.

> **Gate status: 3 of 3 met. THE ANALYSIS GATE IS CLOSED.**
> `diagnose.py` passes on all four §3.2 legs and all four §3.3 pairs, every phase. The legs
> agree on both sessions; `b`, `P` and now `g` are solved (§3.2c–e, §3.3e). §3.3 adds an
> **independent** determination of `b` — from `t1` and `g` together rather than `t1` alone —
> and it lands on 4 and 1 again. **No fourth segment exists** (§3.3c), so the
> `LinearizationTable` undoes CCMP and nothing else, which is what §5 assumes. **§3.4 lands
> in row 2 for both modes**, with the qualifier stated per mode and each part of §13.3 marked
> surviving or falsified against a measurement in §2, §3.2 or §3.3.
>
> The remaining gate is **acceptance**, below. It is a measurement, not an analysis.

**Acceptance gate — the actual goal.** Decode all six takes through their own tags and
compare R/G and B/G against the matched linear reference, patch by patch, across the neutral
ramp. `tools/accept.py`.

> **The gate is "inside the same-class control band", measured in the same run.** The
> 1.3% / 0.9% of §3.1 is a FLATNESS figure and the reference modes do not meet it as written
> here either (they read 1.29–1.46 / 0.81–1.08). The pairing test's controls are 0 vs 1 and
> 4 vs 5 and they read **0.02–0.07%**. **Print them beside the result every time.**

| §3.6e, mid-range | mode 2 | mode 3 | ctrl 0v1 | ctrl 4v5 | m2 / band | m3 / band |
|---|---|---|---|---|---|---|
| 17:05 dR/G / dB/G | **0.06% / 0.12%** | 0.22% / 0.62% | 0.03% / 0.03% | 0.03% / 0.06% | 2.1× / 2.0× | 8.2× / 10.7× |
| 18:37 dR/G / dB/G | **0.05% / 0.07%** | 0.20% / 0.55% | 0.02% / 0.04% | 0.04% / 0.07% | 1.1× / 1.0× | 4.7× / 8.3× |

> **Gate status: mode 2 is at 1.0–2.1× the band, down from 12–18×** — equal to the control on
> the 18:37 session, 2× on 17:05, on a band whose own two controls differ by 3.5×. The strict
> `≤ 1.0×` test passes on one of the four numbers. **Mode 3 is at 4.7–10.7×, and the table is
> not what is left to fix on it** — what remains is flat in level, per channel, and reproduced
> against *every* other mode including mode 2 (§3.6d). No `(T1, s1)` anywhere in a ±3-code,
> ±2% sweep brings it below 0.52%.

Two supporting checks, both cheap, **both run and both pass**:

- `evidence/decode_anchored_asn.png` — modes 2 and 3 decoded beside 4 and 5, honest
  `AsShotNeutral` white balance. **The purple is gone; the greys match the references.**
  (`evidence/res2_clearhdr12.png` is kept as the before.)
- `neutrality.py` on both sessions: modes 2 and 3 land on their references, sessions agree to
  ≤0.7 points.

**Do not write C++ until that gate is passed.** Implementation phases, the `curve`
discriminator (`"mulaw" | "pwl"`) in `cinepi-raw/cinepi/log_lut.cpp`, the rebuild-and-verify
invariant and the Prompt A guard replacement are all in decision doc §9.7 and stay as
written. Branch from `dev` in each repo. **Do not push without asking.**

---

## 6. Status

**Done.** P0 on hardware. Three data sets shot, downloaded and identified. Tools built and
landed in `tools/`. §3.0, §3.0b and §3.1 measured and replicated across two sessions. Black
level measured for all six modes. The transfer curve measured on both modes and shown to
predict every neutrality curve. Defect A falsified; the §4 knee1 trap falsified.
`diagnose.py` lifted onto `dngread.load` — it now serves both resolutions and both bit
depths, measures the take offset and co-registers. **§3.2a passed on all four legs and all
four CFA phases**, re-run after the co-registration defect below. The 20-sensor-row offset
measured and recorded (§2).

**§3.2 DONE (§3.2c–e).** `b` = **4.004** binned and **0.995–0.998** full res, solved, on both
sessions and all four CFA phases; **4.005 / 3.994 from the ratio of the two legs' knots with
no register value at all.** Pedestal solved free on the full-res slope-1 segment:
**200.4 / 201.2**, landing on the tag. Zero-free-parameter closure **0.37 codes rms** binned,
1.43–1.91 full res. Survives kguard 2→6, 26 wrong seeds, block size 4→12, tag-vs-measured
black and a tile bootstrap.

**Defect found and fixed in the tooling:** `diagnose.measure_offset` searched the take offset
**per CFA phase** and fails silently on the full-res leg's R and B (returns `dy=+16 dx=−16`
at r = −0.29 for a take that is `dy=−10 dx=0`). Replaced by `measure_offset_luma`, which
correlates the 4-phase mean: one clean peak at **dy = −10.00**, agreeing with §2's model-free
white-band anchor. §3.2a re-run and re-passed on that footing.

**§3.3 DONE (§3.3a–e).** **No fourth segment** — the ClearHDR blend is a pure gain, measured
on modes 4/5 against 0/1 where there is no companding at all: linear to **±10 codes out of
13831 (0.07%)** over an L range spanning knee2 for both values of `b`, with no consistent
breakpoint across phases or sessions (`tools/blend.py`, `evidence/blend-3.3.json`). So the
`LinearizationTable` undoes CCMP and nothing else.

`g` **solved**, two independent ways agreeing to 0.1–0.4%: from the three segment slopes, and
from the blend leg, which never touches a knee. **1.756 / 1.888** at 17:05 and
**11.274 / 11.991** at 18:37 — ratio **6.39 / 6.34**, the SDR stop-down.
`b` = **4.050 / 4.019** binned and **1.000 / 1.001** full res, now from `t1` and `g` together
rather than `t1` alone; **4.0126 with no register value at all**. `P` stays on 200
(201.0–201.8 from segment 1). Closure **0.10 / 0.28 codes rms** binned. Survives the clipping
guard 0→0.25, `knot_tol` 0.02→0.20 and `kguard` 2→6.

**§3.2 re-run and re-passed on the new footing**, with `g` now *measured* as 1 rather than 1
by construction: `b` = 4.0020 / 4.0014 binned, 0.9926 / 1.0008 full res, `P` = 200.3, ratio
3.998 / 4.001. `robust.py` unchanged and reproducing §3.2e.

**Five defects found and fixed in the tooling**, all the same disease — believing a segment
the fit invented. Each is now a §4 trap: the clipping guard; a slope from a segment no knot
brackets; a knot accepted without looking at its own error bar; two halves of one segment left
un-merged; and an off-by-one segment assignment that only the slope ratio can catch. Four of
the five were caught by the §3.2 regression, not by §3.3 itself.

**§3.4 DONE (§3.4a–d). The analysis gate is closed.** Both modes land in **row 2**. Mode 3's
qualifier is a domain **origin** — the compander is black-referred, not pedestal-referred;
mode 2's is that **plus** the `b` = 4 binning scale. §13.3's shape, both knots and all three
slopes survive to ≤0.5%; its companded black (542), its inverse as written (wrong by **23.9×**
at knee1) and both its derived tags are falsified. Output domain settled at `L + 200`:
`BlackLevel` **200 unchanged**, `WhiteLevel` **63270 / 62708** (now 63265 / 62704, §3.6c),
the only one of four candidates that fits uint16 at both ends for both modes.
`tools/ccmp_decode.py` written; its self-tests pass, including the round trip on all 4096
codes both ways.

**§3.5 — first decode run. The gross defect is gone; a structured residual is not.** Per-pixel
decode landed in `patches.py --decode` and `preview.py --decode`. Full-ramp flatness falls from
51%/63% to **5.7%/8.7%** (mode 2) and 31%/38% to **4.2%/7.1%** (mode 3), i.e. onto their linear
references. **The purple is gone** under both white balances. But the per-patch pairing against
the matched linear reference sits at **0.86–1.74% rms against a 0.07% control floor**, on both
sessions, and the residual is organised **by segment**: −3% below knee1, +0.4…+1.8% on the
1/64 segment decaying with level, ~+0.05% on the 1/16 segment. The 20-row offset is **ruled
out** by direct test. **The acceptance gate is NOT passed.**

**§3.6 DONE (§3.6a–e). §3.5's residual is diagnosed, and it is TWO things.**

The closure re-expressed in L per segment and per phase shows a **signed mean of 100–300 σ**
— a model error, not scatter. `closure_L.py`.

1. **The middle segment's ANCHOR.** `a1 = P + T1(1−s1)/b`, measured on 1358–8933 blocks per
   leg-phase, is **+0.3336 codes** high for `b` = 1 and **+0.2321** for `b` = 4 — the two
   sessions agreeing to 0.014 and 0.008 codes. `P`, `T1` and `b` are **degenerate** in it;
   written on `T1` (**500.3389 / 500.9431**) with `P` held at the measured tag. The closure
   in L then collapses: mode 2's middle segment **+14.1…+16.4 → −0.7…+1.5 L** on all four
   phases and both sessions. `anchor.py`.
2. **A per-channel gain on mode 3 alone**, R +0.2% and B +0.6% of G, flat across the ramp,
   both sessions. **Not the curve** — the transfer is phase-independent, and mode 3 disagrees
   with all five other modes including mode 2, which is decoded through the same generator
   and lands on its control. **No table can remove a flat per-channel gain**, proved
   analytically and confirmed by sweep: 0.52% is the best reachable anywhere.

**Rounding conventions falsified** (flat to 0.017 codes against `frac(code)`); the **soft
knee is not needed** (a sharp corner reproduces mode 2 to ±1.5 L); **§3.2e's B-phase
pedestal is confirmed real (+2.4 / +2.8 codes) and shown NOT to be the cause** — the anchor
is measured against the identity line, so a black error enters it divided by 64.

**Acceptance gate: mode 2 is at 1.0–2.1× the same-class control band, down from 12–18×;
mode 3 is at 4.7–10.7×.** Mid-range mode 2 **0.06/0.12%** and **0.05/0.07%** against controls
of 0.02–0.07%; mode 3 0.22/0.62% and 0.20/0.55%. Full ramp 0.86–1.74% → **0.09–0.62%**.
Cross-validated across sessions (`--xval`). `accept.py` prints the controls, the multiple and
the strict verdict every time. **The purple is gone** under `AsShotNeutral`
(`evidence/decode_anchored_asn.png`), and `neutrality.py` agrees across both sessions.

**The tables are emitted.** `ccmp_decode.py --emit evidence/tables` — two 4096-entry uint16
tables, `.bin` + `.txt` + `manifest.json`, gated on the 21 self-tests.

**Next.**

1. **Mode 3's per-channel gain — a different defect and a different doc.** It is not the
   table. It is a property of the 3856×2180 12-bit ClearHDR mode: R +0.2%, B +0.6% of G
   against every other mode, reproduced on both sessions. Note that mode 3 is one of the two
   modes §2 flags as sitting in the AppNote-Prohibited `EXP_TH_H < EXP_TH_L` state — but so
   is mode 5, and mode 5 agrees with mode 4 at 0.06%, so that alone does not explain it.
   Needs hardware, not analysis: re-shoot with the thresholds corrected.
2. **Mode 2's remaining 2× on the 17:05 session.** 1.0× at 18:37 and 2.0–2.1× at 17:05, on
   the same table — so it is session-borne, not curve-borne, and the cheapest read on it is a
   third chart session. Not blocking; it is inside the controls' own 3.5× spread.
3. **C++.** The analysis and acceptance work is done for mode 2 and the table for mode 3 is
   right — its remaining error is upstream of the table. **Ask before starting**: the gate as
   literally written (`≤ 1.0×` on all four numbers) is met on one of four, and whether that
   clears the bar is the user's call, not the tool's.
4. No C++ touched, nothing pushed.

**Open, not blocking.** Separate cinemate/cinepi-raw threads, none part of this job: the
18:37 shutter change reached the SDR modes only; the 12-bit output path's crop origin sits
20 sensor rows off the 16-bit one (§2); the 16-bit ClearHDR DNGs carry no
`ActiveArea`/`MaskedAreas` so they render with a black bar (§2); and the full-res B phase
reads the pedestal ~2.4 codes above R and G in both sessions — **confirmed and quantified in
§3.6b, and shown not to move the curve.** And modes 0/1 in the 18:37 set are 1.7 stops
under-exposed relative to their own ceiling; harmless here, but if that set is ever used for
anything level-critical, note it.

**One inherited prediction overturned, on measurement:** `g` at 17:05 is ~1.8, not ~1. The
session *ratio* was right; the absolute value was not, because ClearHDR is ~9× less sensitive
than SDR at matched settings. Knot ownership per leg follows `g`, so it differs from what was
predicted — 18:37 full res reaches **both** knots and is the richest §3.3 leg (§3.3d).
