# Pi test handoff — CCMP12 decompand + the log guard

Written 2026-08-09. Everything below is **untested on hardware**: the CCMP work has
never been compiled against libcamera, and the log guard's failure path was traced
statically, not observed.

Ordered by risk, cheapest first, so a failure stops you early. **Gate 2 is the one
most likely to fail** — it is the only genuinely new sensor-facing logic.

## What's on the branches

| repo | branch | contains |
|---|---|---|
| cinepi-raw | `feature/ccmp12-decompand` | the curve + encoder wiring, off `dev` |
| cinepi-raw | `feature/log-encode` | all of the above (merged in) **plus** the log branch and the guard |
| cinemate | `feature/log-encode` | the launch-side guard |

**Test `feature/log-encode` in cinepi-raw** — it is a superset. All pushed.

---

```
GOAL: verify the CCMP12 decompand table on hardware, and the CineMate Log double-
compand guard. Both are pushed and both are unverified on a Pi.

PRECONDITION, CHECK IT FIRST AND DO NOT SKIP
  uname -r   must be >= 6.12.93+rpt. Older rp1-cfe SILENTLY CORRUPTS 16-bit
  capture, and half of what you are about to shoot is 16-bit. A bad kernel makes
  every result below meaningless without looking wrong.

  cinepi-raw:  git checkout feature/log-encode && git pull
  cinemate:    git checkout feature/log-encode && git pull

── GATE 0 — DOES IT BUILD ────────────────────────────────────────────────────
  The merged dng_encoder.cpp has NEVER been compiled against libcamera. Three
  conflicts were resolved in it by hand.
    cd ~/cinepi-raw && meson setup build --wipe && ninja -C build
  PASS: builds clean.
  If it fails: send the first 30 lines. The likely spots are the ccmp_lut.hpp
  include in dng_encoder.hpp, CinePIRecorder::SensorBinning (new, uses
  libcamera::properties::PixelArrayActiveAreas), or the one-tag-one-table block
  at the end of setup_encoder.

── GATE 1 — UNIT TESTS ON DEVICE ─────────────────────────────────────────────
    ninja -C build test        (or: meson test -C build)
  PASS: ccmp_lut and log_lut both pass. ccmp_lut proves the curve is still
  byte-identical to the golden tables when compiled by the Pi's compiler — that
  is not automatic, it is float determinism and it is worth one command.

── GATE 2 — THE LAUNCH LINE. ** THE RISKIEST THING HERE. ** ──────────────────
  Boot into 12-bit ClearHDR and watch cinepi-raw's log. Do BOTH resolutions:
     mode 3   3856x2180  12-bit ClearHDR      (full res, expect b=1)
     mode 2   1928x1090  12-bit ClearHDR      (binned,   expect b=4)

  EXPECT one line per launch, e.g. for mode 3:
    CCMP12 decompand  b=1  T1=500.338900  T2=11500  s1=1/64  s2=1/16  P=200
      LinearizationTable 4096 entries, BlackLevel 200 WhiteLevel 63265
  and for mode 2:  b=4  T1=500.943100 ...  WhiteLevel 62704

  ** THE NUMBER THAT MATTERS IS b. ** It is derived at runtime from
  PixelArrayActiveAreas divided by the mode size, and nothing has ever checked
  what this sensor actually reports for that. Verified off-device against the
  real DNG geometry (1928x1090 -> 4, 3856x2180 -> 1) assuming an active area of
  3856x2180 — if libcamera reports something else, this is where it shows.
    b=1 on BOTH modes   -> the active area is being reported as the mode size.
                           SensorBinning needs a different source. STOP, report.
    "12-bit ClearHDR without a CCMP decompand table: no measured CCMP anchor for
     binning N" -> b resolved to something other than 1 or 4. Send N.
    no line at all      -> the scope gate did not fire. Check --hdr sensor is on
                           the command line and the mode really is 12-bit.
  PASS: b=1 full res, b=4 binned, WhiteLevel 63265 / 62704 respectively.

── GATE 3 — THE TABLE IN THE FILE ────────────────────────────────────────────
  Record a couple of seconds in each of the two modes, then, from the ccmp12-lut
  workspace with the takes copied over (or run it on the Pi, numpy only):
    python3 tools/verify_dng_table.py <take-dir-mode3> <take-dir-mode2>
  It regenerates both goldens from ccmp_decode.py and diffs the tag out of IFD0.
  ** It compares against BOTH tables and names a binning mix-up explicitly ** —
  that is the failure Gate 2 is guarding against, and this is where it is proven.
  PASS: "table is BYTE-IDENTICAL to the b=N golden", BlackLevel 200, WhiteLevel
  as above, identity on codes 0..700 (full res) / 0..325 (binned).

── GATE 4 — DOES IT LOOK RIGHT ───────────────────────────────────────────────
  Re-shoot the six-mode set — same chart, same order, all six modes.
    ** tools/modes.py is keyed to the 2026-08-06 take names. Add a mode map
       entry for the new capture first or no tool will find it. ** Nothing
       auto-detects the mode.
    python3 tools/accept.py
  PASS: modes 2 and 3 land inside the same-class control band, i.e. roughly the
  numbers already in the handoff (m2 0.05-0.12%, m3 0.20-0.62%, controls
  0.02-0.07%). Mode 3 is EXPECTED to sit high — its remainder is a per-channel
  gain upstream of the table and no table fixes it. Do not chase it here.

    ** tools/preview.py --decode off ** on the new takes. The table is IN the
    file now, so a converter applies it and the tools must NOT decode a second
    time. Getting this wrong makes a correct file look badly wrong.

── GATE 5 — THE LOG GUARD REFUSES ────────────────────────────────────────────
  In 12-bit ClearHDR, `set log`. Two things must happen:
    cinemate log:   "CineMate Log requested (...) but NOT applied: 12-bit
                     ClearHDR is CCMP-companded on-sensor and log-encoding it
                     would compand twice. Recording linear 12-bit."
    cinepi-raw log: "CineMate Log off for this mode: 12-bit ClearHDR is
                     CCMP-companded ..."
  and the DNG must be plain 12-bit WITH the CCMP table (not a log table):
    python3 tools/verify_dng_table.py <that-take>     -> still byte-identical
  PASS: refused at both layers, naming CCMP, and the file still carries the
  decompand table.
  If it is NOT refused and a log DNG appears: that is the original bug, live.
  Send the launch args and both logs.

── GATE 6 — REGRESSION, THE COMBINATION THAT MUST STILL WORK ─────────────────
  16-bit ClearHDR + `set log` (16to12). This is what the log branch exists for
  and the guard must not touch it.
  PASS: log engages, DNG ~12,618,004 bytes, tag 0xC618 present and it is the
  LOG table (verify_dng_table.py will say it matches NEITHER CCMP golden — that
  is CORRECT here and is the expected output for this gate).
  Also worth one shot: 12-bit SDR + set log (12to10) must still work — the guard
  keys on ClearHDR, not on depth.

── WHAT TO SEND BACK ─────────────────────────────────────────────────────────
  1. the two "CCMP12 decompand" launch lines (Gate 2) — verbatim
  2. verify_dng_table.py output for both modes (Gate 3)
  3. accept.py's verdict table (Gate 4)
  4. the two refusal messages (Gate 5)
  5. anything that failed, with the surrounding 20 log lines
```

---

## If you only have ten minutes

Gates 0, 2 and 3. Build it, read the two launch lines, run `verify_dng_table.py`
on one take from each mode. That covers every piece of new logic that can be
wrong in a way the desk could not already rule out.

## What is already known and does not need re-testing

- **The curve.** Byte-identical to the goldens on two independent compilers, 25
  structural checks, and the analysis behind it is closed across two chart
  sessions. If a render looks off, question the plumbing, not the curve.
- **Mode 3's ~0.5% per-channel residual.** Proven upstream of the table (flat in
  level, per channel, present against every other mode including mode 2). It is a
  separate hardware thread — re-shoot with `EXP_TH_H`/`EXP_TH_L` corrected.
- **The black level.** 200 on all six modes, measured on a clean lens-cap set.
  The "~542 companded black" in older docs is falsified.
