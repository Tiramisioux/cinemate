# Next pass — the brief

Written 2026-08-09, at the close of the analysis phase. Paste the block below.

---

```
GOAL: ship the CCMP12 decompand LinearizationTable so a 12-bit ClearHDR DNG off the Pi
decodes linear with no post step. Modes 2 and 3, nothing else. The analysis is CLOSED and
the two tables are DERIVED, VERIFIED and WRITTEN TO DISK. Judge every result on whether a
DNG straight off the Pi carries a table byte-identical to the golden one.

READ FIRST — current as of 2026-08-09 and reconciled against the hardware. Trust them.
  1. innomaker585/ccmp12-lut/README.md
  2. innomaker585/ccmp12-lut/CCMP12-ANALYSIS-HANDOFF.md
     §2 ESTABLISHED, §3.4c the output domain, §3.6 the anchor and what it did NOT fix,
     §4 traps, §5 deliverable + tags + gates, §6 status.
     §3.0–§3.6 are DONE. Do not re-derive them. Re-run only to confirm a change you made.
  3. ../CCMP12-VS-LOG-DECISION.md §9.7 — the phase table. **P1 is now DONE.** You are on
     P2, then P3. Its §9.4 and Prompt B are spent; ignore them.
  4. ../CINEMATE-LOG-VERIFIED.md and ../CINEMATE-LOG-RESUME.md — the log branch's existing
     machinery, which P3 precomposes with rather than replaces.

WHAT LANDED LAST PASS
  §3.6 — the §3.5 residual is diagnosed and it was TWO things.
  §3.2d's closure re-expressed in L, per segment per phase per level bin, SIGNED: the mean
  is +14…+47 L on the middle segment against standard errors of 0.06–0.26 L. 100–300 sigma.
  A model error, not scatter.
  ** The cause is the MIDDLE SEGMENT'S ANCHOR. ** a1 = P + T1(1-s1)/b is the one number the
  middle and high segments hang off, and P, T1 and b enter them ONLY through it — so on
  those segments the three are DEGENERATE. a1 itself is determined to +/-0.03 codes:
  +0.3336 (b=1) and +0.2321 (b=4), the two sessions agreeing to 0.014 and 0.008. Written on
  T1 with P held at the measured tag 200. Cross-validated: anchor fitted on one session,
  gate measured on the other, out of sample indistinguishable from in sample.
  Falsified on the way: a hardware rounding convention (flat to 0.017 codes against
  frac(code), on 1.38 codes of dither); the 1/b scaling the last brief predicted (0.33
  against 0.23 is a ratio of 1.4, not 4); and §3.2e's B-phase pedestal as the cause — it is
  confirmed real at +2.4/+2.8 codes and it does not propagate, because the anchor is
  measured against the identity line and a black error enters it divided by 64.
  ** What the anchor did NOT fix: mode 3 carries a PER-CHANNEL GAIN. ** R +0.2%, B +0.6% of
  G, flat across the ramp, both sessions. The transfer is per pixel and phase-independent,
  so this is not the curve; a table takes the stored code and knows no channel. Mode 3
  disagrees with all five other modes including mode 2, which is decoded through the same
  generator and lands on its control. Sweeping T1 over +/-3 codes and s1 over +/-2% never
  gets below 0.52% against a 0.06% control. ** It is upstream of the table. **

WHERE THAT LEFT THE ACCEPTANCE GATE
  Mid-range, decoded against the matched linear reference, patch by patch, controls beside:
                    mode 2      mode 3    ctrl 0v1   ctrl 4v5   m2/band   m3/band
    17:05 dR/G       0.06%       0.22%      0.03%      0.03%      2.1x      8.2x
    17:05 dB/G       0.12%       0.62%      0.03%      0.06%      2.0x     10.7x
    18:37 dR/G       0.05%       0.20%      0.02%      0.04%      1.1x      4.7x
    18:37 dB/G       0.07%       0.55%      0.04%      0.07%      1.0x      8.3x
  Full ramp 0.86–1.74% -> 0.09–0.62%. Mode 2 went from 12–18x the band to 1.0–2.1x. The
  strict <=1.0x test passes on ONE of the four numbers, on a band whose own two controls
  differ from each other by 3.5x. `accept.py` prints all three readings and rounds none away.

** THE ONE DECISION THAT IS NOT THE TOOL'S. ASK IT FIRST, BEFORE ANY C++. **
  §5's rule is "do not write C++ until the acceptance gate is passed", and the gate is now a
  judgement, not a number. Put it to the user in one line: mode 2 at 1.0–2.1x the band,
  mode 3 at 4.7–10.7x with its remainder proven to be upstream of the table. Options are
  (a) ship both tables now, (b) ship and open the mode-3 hardware thread in parallel,
  (c) a third chart session first. Recommend (b). Do not assume the answer.

YOUR TASK, ONCE THAT IS SETTLED: §9.7 P2, then P3.
  P2 — write the table as the LinearizationTable when log is OFF.
       cinepi-raw: a `pwl` curve type in cinepi/log_lut.cpp behind the existing `curve`
       discriminator ("mulaw" | "pwl"), plus the tag writes in dng_encoder.cpp.
  P3 — precompose with log16to10_forward for the log-ON branch and replace the P0 guard.

THE GOLDEN REFERENCE ALREADY EXISTS. DO NOT RE-DERIVE IT IN C++.
  innomaker585/ccmp12-lut/evidence/tables/
    ccmp_decode_mode3_fullres.bin   4096 x uint16 little-endian   + .txt + manifest.json
    ccmp_decode_mode2_binned.bin    4096 x uint16 little-endian   + .txt
  Regenerate with `python3 tools/ccmp_decode.py --emit evidence/tables` — the emit is gated
  on 21 self-tests and writes nothing if any fail. ** The C++ must reproduce these byte for
  byte. ** That is the same acceptance the CineMate Log encoder passed and it is the only
  cheap proof that a reimplementation did not acquire a transcription error.

THE ARITHMETIC THE C++ CARRIES. Every literal, in one place.
    stored_code = ccmp(b*L)/b + P            L = linear above black, 16-bit ClearHDR LSB
    ccmp(x) = x                              x <= T1
            = T1 + (x-T1)*s1                 T1 < x <= T2
            = C2 + (x-T2)*s2                 x >  T2,   C2 = T1 + (T2-T1)*s1
    table[C]  = floor( ccmp_inv(b*(C-P))/b + 200 + 0.5 )        C = 0..4095

                          mode 3 (full res 3856x2180)   mode 2 (binned 1928x1090)
    b                                    1                          4
    T1  (register 500 + measured anchor) 500.3389                   500.9431
    T2  (register)                       11500                      11500
    s1  (ACMP1 menu idx 6)               1/64                       1/64
    s2  (ACMP2 menu idx 4)               1/16                       1/16
    P   (BlackLevel tag)                 200                        200
    BlackLevel written                   200  UNCHANGED             200  UNCHANGED
    WhiteLevel written                   63265                      62704
    knee1 / knee2, stored code           700.339 / 872.209          325.236 / 368.201
    identity on                          codes 0..700               codes 0..325

TRAPS THAT WILL BITE IN C++. Each is a §4 trap or a §3.4c finding, restated for the port.
  - TWO TABLES, ONE GENERATOR. Select on the mode's BINNING, not on ClearHDR and not on
    resolution-as-a-string. Getting it backwards is wrong by 2.6x at knee1 and does not
    look obviously wrong.
  - The output domain is KEEP_PEDESTAL, L + 200. ** BlackLevel stays 200 — only WhiteLevel
    is rewritten. ** The two WhiteLevels differ because the knee2 codes do. Do not force
    them equal.
  - Rounding is floor(x + 0.5), NOT round-half-to-even. Every entry on mode 2's top segment
    is a half-integer, and half-to-even alternates the step 15/17 and puts a visible ripple
    in the slope.
  - ** NEVER CLAMP. ** A domain that does not fit uint16 must fail loudly. A clipped
    highlight or a clipped shadow is exactly the defect this table exists to remove.
    "Fits uint16" is a test at BOTH ends: ABOVE_BLACK fails at the bottom, not the top.
  - The log-ON branch's source domain is 16-bit AFTER decompand, not 12. It uses the
    `16to10` spec, never `12to10`. That is the silent double-compand hazard and it is what
    the P0 guard exists to prevent — P3 REPLACES that guard, it does not remove it.
  - Keep the rebuild-and-verify invariant: the rebuilt table must equal the stored one and
    hard-fail on mismatch. The format already carries an explicit 4096-entry table.
  - Assert the identity segment. table[C] == C for C <= 700 (mode 3) and C <= 325 (mode 2)
    is one line and it catches a b mix-up, a pedestal mix-up and a domain mix-up at once.

VERIFYING ON HARDWARE
  1. Extract the LinearizationTable, BlackLevel and WhiteLevel from a DNG off the Pi and
     diff against evidence/tables/*.bin. Byte-identical, both modes, or stop.
  2. Shoot the six-mode set again — same order, same chart — and run tools/accept.py.
     ** tools/modes.py is keyed to the 2026-08-06 take names. A new capture needs a new
     mode map entry there before any tool will find it. ** Nothing auto-detects the mode.
  3. tools/preview.py --decode off on the new take: with the table IN the file, a converter
     applies it, so the tools must NOT decode a second time. Check that before believing a
     render.
  Check `uname -r` >= 6.12.93 on the Pi before shooting anything 16-bit or ClearHDR — older
  rp1-cfe silently corrupts 16-bit capture, and half this data set is 16-bit.

WHAT MUST NOT HAPPEN
  - Do not re-fit the table. The anchor is measured on thousands of blocks, localised by
    level and segment, and cross-validated across sessions. If a render looks off, the
    thing to question is the plumbing, not the curve.
  - Do not let a RATIO metric choose a curve parameter. Above knee1 the decode is affine and
    channel-blind, so T1/P/b move a ratio only as d*(1/B - 1/G) and s1 not at all.
    Optimising a ratio spends the curve's one parameter absorbing errors that are not the
    curve's — the ratio sweep wants T1 = 500.5 where the level residual measures 500.34.
  - Do not try to fix mode 3's remaining 0.5% in the table. It is proven to be a per-channel
    gain and no table can hold one. Raise it, do not bundle.
  - Do not push without asking. Branch from `dev` in each repo.

GATE for this pass
  P2 passes when a 12-bit ClearHDR DNG off the Pi carries a LinearizationTable byte-identical
  to the emitted golden table for its binning, with BlackLevel 200 and the right WhiteLevel,
  and `accept.py` on a fresh six-mode set reproduces the numbers above within the controls'
  own spread. P3 passes when a 10-bit CCMP take round-trips inside the 20-mstop gate and the
  P0 guard is replaced rather than removed.

NOT PART OF THIS JOB. Four separate cinemate/cinepi-raw threads. Raise them, do not bundle.
  1. ** NEW, and the biggest. ** Mode 3 (3856x2180 12-bit ClearHDR) carries a per-channel
     colour error of R +0.2% and B +0.6% of G against every other mode, both sessions,
     upstream of the table. Against mode 1 — SDR full res, no 16-bit path and no compander
     anywhere — modes 2, 4 and 5 cluster at 0.24–0.49% and mode 3 sits at 0.81–0.99%. Note
     that mode 3 is one of the two modes §2 flags as sitting in the AppNote-Prohibited
     EXP_TH_H < EXP_TH_L state — but so is mode 5, and mode 5 agrees with mode 4 at 0.06%,
     so that alone does not explain it. Needs hardware: re-shoot with the thresholds
     corrected and re-run accept.py.
  2. The 18:37 shutter change reached the SDR modes only.
  3. The 12-bit output path's crop origin sits 20 sensor rows off the 16-bit one (§2).
  4. The 16-bit ClearHDR DNGs carry no ActiveArea / MaskedAreas, so they render with a black
     bar across the top (§2).
  And the full-res B phase reads the pedestal ~2.4 codes above R and G in both sessions —
  now confirmed and quantified in §3.6b, and shown not to move the curve.

HARD RULES
  - §4 traps have each cost a pass. Read before measuring. §3.6 added six.
  - Report residuals in L, or with dL/dC beside them. Never a bare code-domain rms.
  - Never merge points from the two chart sessions into one fit.
  - Never hand-write a golden value. Derive it from registers, the fit, or the generator.
  - ccmp_decode is one generator, TWO tables. Do not try to make one serve modes 2 and 3.
  - Decode PER PIXEL, then average. Never apply the LUT to a mean.
  - Always print the same-class control beside any pairing result.
  - If a doc contradicts the hardware, believe the hardware and fix the doc.
```
