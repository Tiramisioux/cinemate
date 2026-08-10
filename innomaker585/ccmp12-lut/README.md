# CCMP12 decompand LUT — workspace

Everything for getting **12-bit ClearHDR** (modes 2 and 3) looking right. `ccmp_decode` is
the means; the other four modes are already measured correct and are the target.

**Start at [`CCMP12-ANALYSIS-HANDOFF.md`](CCMP12-ANALYSIS-HANDOFF.md).** It is self-contained:
the data, what is established, what has been falsified, the method, the traps, and what is
left.

Background, in reading order: `../CCMP12-VS-LOG-DECISION.md` **§9** (§§2–5 are superseded),
`../CINEMATE-LOG-COLORCHECKER.md` §§1–2 and §13, `../CINEMATE-LOG-VERIFIED.md`.

---

## Layout

```
CCMP12-ANALYSIS-HANDOFF.md   the handoff — read first
NEXT-PASS-PROMPT.md          the brief for the implementation pass (§9.7 P2/P3)
PI-TEST-HANDOFF.md           ** the hardware gates — what to run on the Pi, in risk order **
LOG-BRANCH-HANDOFF.md        the P0 guard brief for the LOG branch, + the merge checklist
tools/                       analysis scripts, numpy only, run anywhere
takes/                       the DNGs — 159 frames, 1.3 GB, gitignored
evidence/                    rendered artefacts, the emitted tables, the block cache
```

**P2 is implemented.** cinepi-raw `feature/ccmp12-decompand`, off `dev`, commits `4aef539`
(the curve + its byte-for-byte test) and `b8a442a` (the encoder wiring). The C++ reproduces
`evidence/tables/*.txt` exactly. **Not yet built or run on a Pi.**

**The workspace is self-contained** — data, tools and brief in one folder.

| `takes/` | Frames | What |
|---|---|---|
| `ccmp-greycard/` | 82 | **the six-mode set, 17:05.** Modes 0/1 clip above grey4; best coverage of knee2 |
| `ccmp-greycard-1837/` | 39 | **the six-mode set, 18:37.** Modes 0/1 stopped down ×6.3 and un-clipped; modes 2–5 unmoved |
| `ccmp-c0-6mode/` | 38 | **lens cap, one take per mode.** The black-level measurement |

The two chart sessions are 1.5 h apart. Fit each independently and require agreement —
**never merge points from both into one curve** (handoff §4).

⚠ **1.3 GB.** `takes/.gitignore` excludes `*.dng` and `*.log`. `innomaker585/` is currently
untracked, so nothing is at risk today — but if it is ever added to git, check that ignore
first.

The old `ccmp-c0/`, `ccmp-c0_UHD/` and the two `..._shutter*` sets have been **deleted**. The
first two were light-leaked, which is what produced the false "black is 229" reading; the last
two were the void exposure bracket (handoff §4).

---

## tools/

Run with the pyenv python (`~/.pyenv/shims/python3`); macOS blocks the system python from
`~/Documents`. numpy only — Pillow is needed for `--overlay` and nothing else.

```
python3 tools/patches.py takes/<set>/*/ --json p.json
python3 tools/gates.py p.json          # §3.0 uniformity, §3.0b scope
python3 tools/neutrality.py p.json     # §3.1 neutrality vs level
```

| Script | What it does |
|---|---|
| `dngread.py` | **The shared reader.** Geometry, bit depth, black, white, CFA, `LinearizationTable` — all from the file's own IFD0, so one tool serves both resolutions. Carries the measured MSB-first 12-bit unpacker. Start any new tool from this. |
| `patches.py` | **The chart sampler.** Boxes in NORMALISED frame coordinates, so one definition samples 1928×1090 and 3856×2180 alike. Raw CFA code means per phase, frame-to-frame spread, saturation flag. `--overlay` draws the boxes, `--profile` finds patch plateaus without guessing. |
| `modes.py` | Mode maps for all three sessions, plus the measured per-mode per-channel black levels. |
| `gates.py` | §3.0 uniformity gate and §3.0b scope test. |
| `neutrality.py` | §3.1 — R/G and B/G across the neutral ramp, the primary instrument. |
| `preview.py` | DNG → RGB PNG, for locating the chart by eye. |
| `diagnose.py` | **Is an A/B pair a function?** A-spread inside narrow B bins with the B-spread fitted out, against the propagated noise floor; plus a left/right and top/bottom split on the residual. Reads geometry from the file, so it serves both resolutions and both bit depths. **Measures the take offset and co-registers automatically** — see the handoff §2. **Run this on every pair before any fit.** Also home to `measure_offset_luma`. |
| `fitcurve.py` | **§3.2 — solves the transfer for one leg**, with the pedestal and `b` both free. Fits the three segments *away* from the knees and lets the knots fall out of the slope intersections; the guard is `k × σ_within` **per block**, so it is set by the physics of the bend, not by a chosen fraction of level. `--dump` prints the binned A-vs-x curve with local secants — **look at that before believing any fitted number.** |
| `fit_all.py` | Runs `fitcurve` over every leg, both sessions, all four CFA phases. `--section 3.2\|3.3\|both`. Answers §3.2's three questions plus §3.3's `g`. Never merges the sessions. |
| `blend.py` | **§3.3 — is the ClearHDR blend a pure gain, or does it have a knee?** Pairs modes 4/5 against 0/1, both linear, so the blend is alone with **no companding in the path**. Single line, residual profile, and a free breakpoint. This is the tool that answers the fourth-segment question; do not try to answer it from §3.3's own legs, where the blend is multiplied into the three CCMP segments. |
| `robust.py` | Sweeps the knobs that could manufacture the §3.2 answer: knee guard, seed, block size, which black level, plus a spatial-tile bootstrap. Imports `fit_all.LEGS`, which is deliberately still **§3.2's two legs** — it is what produced the §3.2e evidence. |
| `c0_analyze.py` | Per-CFA-channel means and σ from a lens-cap take. Superseded for black by `modes.MEASURED_BLACK`, still useful for noise. Hardcodes geometry. |
| `transfer.py` | Region-pair transfer measurement between two takes. Written for a shutter ratio; §3.2's legs need the same structure. Hardcodes geometry. |
| `magenta.py` | Colour vs level, computed with two black levels. **Its premise is now moot** — the black levels agree to 1.3 codes, so it no longer separates anything. `neutrality.py` replaces it. |
| `ccmp_probe.py` | Code-occupancy and density either side of a predicted knee. Hardcodes geometry. |
| `ccmp_decode.py` | **The deliverable's generator — one generator, two tables.** Parameterised on `b`; the only literals are the register readbacks, the `BlackLevel` tag, the measured `b` and the measured middle-segment anchor `T1_EFF` (handoff §3.6c). `--check` runs the round trip and 21 acceptance tests before any DNG is touched. `--report` derives the knee codes, all four candidate output domains and both tags. `--vs-133` compares against §13.3 by **instantiating** it as the same generator with `P=0, b=1`. `--emit DIR` writes both tables plus a manifest, **gated on the self-tests**. `for_mode(b, anchored=False)` still returns the register-only curve — the difference between the two IS the §3.5 residual. |
| `legcache.py` | Caches `fitcurve.leg_points` to `evidence/cache/`, keyed on every argument that changes the blocks. Nothing here changes a number; it makes diagnosis interactive instead of 20 s per question. |
| `closure_L.py` | **§3.2d's closure re-expressed in L**, per SEGMENT, per PHASE, both sessions, with the **signed mean** beside the rms. This is the check that would have caught §3.5 two passes earlier. **§3.6a is `--regs`; §3.6c is `--regs --anchored`.** ⚠ `--anchored` alone is neither — the fit re-absorbs the anchor through its own solved `P` and `b` and mode 2 reads −14.8 L instead of −0.7…+1.5. The tool warns; handoff §4. |
| `anchor.py` | **§3.6c — measures the middle segment's anchor**, which is what the residual is. Fits the residual as a line in `x` and reads it AT THE KNOT, so the level-dependent term cannot contaminate it. Reports `kappa` beside it, which is the part that is *not* the curve. |
| `resid_profile.py` | The closure residual as a dense function of level, in L, knee neighbourhoods printed rather than excluded. A shape names a cause; an rms does not. |
| `resid_why.py` | Four discriminating tests: `phase` (a curve cannot be channel-dependent), `round` (a rounding rule is a sawtooth in `frac(code)`), `space`, `patch`. |
| `resid_neutral.py` | The `phase` test with the **patch class fixed** — at one L the four phases look at four *different* patches, and that confound has to go before a phase disagreement is evidence. |
| `blockratio.py` | The acceptance metric on blocks instead of nine patches, joined on the block grid so all four phases describe the same piece of chart. `--linear` runs the ctrl legs, where both takes are linear. **Blocks localise; patches size** (handoff §4). |
| `sweep_table.py` | Sweeps `T1` and `s1` and shows what the best reachable result is. Used to prove a negative: nothing in the table can remove mode 3's remainder. |
| `accept.py` | **THE ACCEPTANCE GATE.** Decoded 2 and 3 against their own linear references, patch by patch, **with the same-class controls printed beside them**, both sessions, plus the 15-pair matrix that names the outlier mode. |
| `verify_dng_table.py` | **THE P2 GATE.** Is the `LinearizationTable` in a DNG off the Pi the golden one? Regenerates both goldens from `ccmp_decode` and diffs the tag out of IFD0. **Compares against BOTH tables**, so a binning mix-up is named as one rather than reported as 7684 mismatched codes. Also checks both level tags and the identity segment. See `PI-TEST-HANDOFF.md` gate 3. |

`patches.py`, `gates.py`, `neutrality.py`, `diagnose.py` and `dngread.py` read geometry from
the file. `c0_analyze.py`, `transfer.py` and `ccmp_probe.py` do not — **lift `dngread.load`
into them before pointing them at any set that spans two resolutions.**

⚠ **The takes are not co-registered.** The 16-bit takes carry the sensor's **20 optical-black
rows** at the top of the frame and the 12-bit takes do not, so every 12-bit take sits 20
sensor rows above its 16-bit counterpart, on both sessions, `dx = 0`. It is invisible on a
patch plateau and worth 300–660 codes at a patch border. `diagnose.py` corrects it; anything
else that pairs a 12-bit take with a 16-bit one region-by-region must too. Handoff §2.

⚠ **Measure that offset once per LEG, off the luma — never per CFA phase.** The crop origin
is a property of the readout, so one offset serves all four phases.
`diagnose.measure_offset` searched per phase and **fails silently** on the full-res leg's R
and B: it walks to the corner of its ±16 search box and returns `dy=+16 dx=−16` at
**r = −0.29**, for a take that is `dy=−10 dx=0`. One phase plane of the 12-bit take carries a
quarter of the photons and has its gradients divided by 64 through the middle segment, so the
peak drops into the noise. Use **`measure_offset_luma`** — correlates the 4-phase mean, single
clean peak, parabolic sub-step **−9.99**, against §2's model-free white-band anchor of −19.83
raw rows. `leg()` now uses it; the per-phase function is kept and marked deprecated because it
is what produced the offsets recorded in handoff §3.2a. Those were re-run and still pass.

`transfer.py` and `diagnose.py` were originally run against the void shutter pair. Their
numbers in older docs are evidence that the *method* failed, not measurements of the sensor.
The code is sound; the data was not.

⚠ **A block mean cannot report clipping.** `block_stats` returns a per-block
**saturated-pixel-fraction** plane and both `diagnose` and `fitcurve` reject on it
(`--satmax`, default 0 = reject a block holding a single pinned pixel). `mean >= white*0.999`
does not do this: modes 0 and 1 in the 17:05 set are 8.8–11.3% pinned at exactly 4095, and a
block 30% pinned has a mean far below white and passes. With the guard off, the 17:05 binned
§3.3 leg does not fit at all. Handoff §3.3b.

⚠ **`fitcurve` no longer assumes `g == 1`.** The model is `A = P + ccmp(b·g·x)/b`. `b` and `g`
enter the knots only as the product `b·g`, so **the knots alone can never separate them** —
the three slopes do, and `b = T1/(t1·g)` follows. On §3.2's legs `g` comes out 1, which is now
a measurement rather than a construction. Five acceptance tests were added with it (handoff
§4, "Added by §3.3"); the `--kguard`, `--knot-tol` and `--satmax` sweeps are all flat.

---

## evidence/

`res2_clearhdr12.png` — take 2 (1928×1090 12-bit ClearHDR), gamma 2.2, each channel
normalised to its own 99.5th percentile. That normalisation is a crude white balance on the
white chip, and **the chart still renders purple**. Whites neutral, everything below magenta.

That is the defect with no instrumentation: normalising on the highlight cannot neutralise
the mid-tones, because what is wrong is the transfer curve, not the white balance.

**Keep this image.** It is the *before*.

`decode_anchored_asn.png` — the after. Modes 2 and 3 decoded through the shipping tables,
beside their linear references 4 and 5, under the honest `AsShotNeutral` white balance rather
than the flattering per-channel percentile. **The purple is gone and the greys match.**

`tables/` — the emitted tables. `cache/` — `legcache`'s block cache; delete it freely.

⚠ **The four PNGs in `evidence/` are deliberately NOT committed.** The repo's
`.gitattributes` puts `*.png` under git-lfs with `filter.lfs.required=true`, and git-lfs
is not installed on this machine — `git add` hard-fails on them. They stay untracked
rather than being force-added as plain blobs, which would be inconsistent with the
attribute on any machine that *does* have lfs. Install git-lfs to track them.

---

## The two things not to get wrong

**1. 12-bit DNG unpacking is TIFF/DNG MSB-first, not MIPI.**

```python
p0 = (b0 << 4) | (b1 >> 4)
p1 = ((b1 & 0x0F) << 8) | b2      # 2 px per 3 bytes
```

Measured, not assumed. The MIPI ordering returns plausible-looking numbers on R and G2 while
silently garbling G1 and B. It does not crash and it does not look obviously wrong. Carried
in `dngread.py`.

**2. `ccmp_decode` is one generator, two tables.**

```
decode:  L = ccmp⁻¹(b·(code − 200))/b        b = 4 binned, 1 full res
```

The binned and full-res modes put the CCMP knees 4× apart in the delivered-linear domain,
because the companding input is the binned signal. At code 400 the decode gives 200 for mode 3
and **3387.5** for mode 2. A DNG `LinearizationTable` takes no mode parameter, so **modes 2
and 3 need different tables.**

⚠ That figure read **4925** until 2026-08-07 and was wrong — it mixed the binned L-domain knot
2875 with the un-binned code-domain knot 671.875 and dropped the final `/b`. Derive it from
the forward model, never by hand (handoff §2, point 4). Both figures are now
`ccmp_decode.py --report` output rather than prose.

**3. The middle segment's anchor is measured, and it is degenerate.**

`a1 = P + T1(1−s1)/b` is the one number the middle and high segments hang off, and `P`, `T1`
and `b` enter them *only* through it. It measures **+0.334 codes** (b=1) and **+0.232** (b=4)
above the register+tag value, reproducibly on both chart sessions. Written on `T1` — but the
same `a1` is a pedestal of 200.33/200.23 or a `b` of 0.9993/3.992, and the table is
bit-identical either way. **Quote the anchor, then say which of the three you wrote it on.**
Handoff §3.6c.

It does **not** scale as 1/`b` between the modes (0.33 against 0.23, a ratio of 1.4), so it
is not one shared physical parameter. Two measured anchors, one per table.

---

**The tags, settled in handoff §3.4c and re-derived after §3.6c.** Output domain is `L + 200`
— the only one of four candidates that fits uint16 at *both* ends for *both* modes.

| | mode 3 (b=1) | mode 2 (b=4) |
|---|---|---|
| `BlackLevel` | 200 — **unchanged** | 200 — **unchanged** |
| `WhiteLevel` | **63265** | **62704** |
| effective `T1` | **500.3389** | **500.9431** |

The two `WhiteLevel`s differ because the knee2 codes do (872.21 against 368.20), with 16 L
per code above them. **Do not force them equal.**

```
python3 tools/ccmp_decode.py --emit evidence/tables    # two tables + manifest, self-test gated
python3 tools/accept.py                                # the acceptance gate, controls included
```
