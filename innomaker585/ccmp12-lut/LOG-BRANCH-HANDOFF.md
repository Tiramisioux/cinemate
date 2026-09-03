# Handoff — the CineMate Log × 12-bit ClearHDR guard

Written 2026-08-09, from the CCMP12 branch.

> ## STATUS — STEP 2 IS DONE. The outstanding work is the HARDWARE GATE.
>
> | | |
> |---|---|
> | **Topology** | `feature/ccmp12-decompand` **merged into** `feature/log-encode` (cinepi-raw `4604d0e`). CCMP is now an ancestor, so P3 is reachable in one tree. Merged, not rebased — the log branch is published and installed on the Pi. |
> | **Guard, cinepi-raw** | `978b443` — `log_source_is_companded()` in `log_lut.hpp`, pure and testable; refuses in the scope chain. 166 checks pass. |
> | **Guard, cinemate** | `cede78bf` — `resolve_log_encode_target(hdr=…)` returns None for 12-bit + ClearHDR; the launch log names CCMP. |
> | **STEP 1 — prove on hardware** | **NOT DONE.** `cinepi.local` did not resolve. The failure path is traced statically through the whole scope chain and the "worst_off = 0" arithmetic is derived in the test, but the two-take capture is outstanding. |
> | **STEP 3 — re-record and gate** | **NOT DONE.** Same reason. |
>
> **The falsified premise below was confirmed against the code**, not just the
> docs: `log_lut_scale_black(3200)` = `3200 × 4095/65535` = **exactly 200**, so
> `worst_off` is 0 and the black-level guard passes *correctly*. There is no
> pedestal discrepancy. Do not go looking for one.
>
> The block below is kept as written, for the record and for STEP 1/3.

**Why this exists.** `feature/ccmp12-decompand` (cinepi-raw, off `dev`) now writes a CCMP
decompand `LinearizationTable` into 12-bit ClearHDR DNGs. That changes what the log branch's
guard means: the combination is not permanently forbidden, it is forbidden *until the two
branches meet*. The guard must be written so it is **replaced**, not deleted.

**One correction to carry.** The brief this replaces states *"real companded black is ~542,
not 200, so the footroom toe lands ~342 LSB off."* **That is falsified and the fix should
not be justified by it.** Handoff §2 measures black on a clean lens-cap set, all six modes:

| mode 2 (binned HDR 12b) | mode 3 (4K HDR 12b) | tag |
|---|---|---|
| 201.39 / 201.36 / 201.63 / 201.65 | 198.70 / 198.73 / 198.75 / 198.71 | **200** |

Black **is** 200. 542 is §13.3's *derived* companded black, falsified in §3.4; the earlier
"224–232" reading came from light-leaked takes since deleted (§2, "FALSIFIED: defect A").

This matters for the fix, not just the record: the existing black-level guard reports
`worst_off = 0` **because there is genuinely no black-level problem**. It is working
correctly. Do not try to make it catch this, and do not go looking for a pedestal
discrepancy — there isn't one. The defect is the **transfer curve** and nothing else, so
only an explicit HDR-awareness check can catch it. Which is what the fix below does.

---

```
GOAL: close the CineMate Log x 12-bit ClearHDR double-companding hazard. Two guards, on the
log feature branches. The analysis is done — do not re-derive it, do not re-open the CCMP12
decision (settled, CCMP12-VS-LOG-DECISION.md section 5).

READ FIRST
  1. innomaker585/CCMP12-VS-LOG-DECISION.md section 4 — the failure path and the draft guard.
     Its section 9.7 has the phase table: this is P0, and ** P3 REPLACES THIS GUARD. **
  2. innomaker585/CINEMATE-LOG-RESUME.md — log branch state.
  3. innomaker585/ccmp12-lut/LOG-BRANCH-HANDOFF.md — the black-level correction below.

THE BUG. cinemate resolves --log-encode from sensor + source bit depth only, with no HDR
awareness (src/module/sensor_detect.py resolve_log_encode_target). sensors.json declares
imx585 "12": {"valid":[10],"default":10}. So 12-bit ClearHDR (mode 2/3) + `set log` launches
cinepi-raw --hdr sensor --log-encode 10 against CCMP-companded data. cinepi-raw's scope
checks all pass and mu-law is applied on top of Sony's CCMP curve, with a mu-law
LinearizationTable written over it claiming linear input. Nothing warns.

** WHY THE EXISTING BLACK-LEVEL GUARD DOES NOT CATCH IT — CORRECTED. **
  Not because the real black is 542. It is 200, measured on all six modes on a clean
  lens-cap set (ccmp12-lut handoff section 2; mode 2 reads 201.4-201.7, mode 3 reads 198.7).
  542 is section 13.3's DERIVED companded black and it is FALSIFIED.
  The guard reads worst_off = 0 because there is no black-level problem to find. It is
  correct. ** Do not try to make it catch this and do not hunt for a pedestal discrepancy. **
  CCMP is the identity below its first knee — stored code 700 full res, 325 binned — and
  black at 200 sits well inside that segment, so the pedestal is genuinely untouched by the
  compander. The defect is the transfer curve ABOVE the knee, and only an explicit
  HDR-awareness check can see it.

STEP 1 — PROVE IT BEFORE FIXING. On the Pi (pi@cinepi.local; `uname -r` >= 6.12.93+rpt)
record two short 12-bit ClearHDR takes, log off and `set log`. Confirm from the cinepi-raw
log and the DNGs that the log path engaged: tag 0xC618 present, ~10-bit strips. If it
refuses on its own, STOP and report — then the doc is wrong, not the code.

STEP 2 — FIX, two guards.
  - cinepi-raw/cinepi/dng_encoder.cpp, in the scope-check chain: refuse when src_bits == 12
    AND options_->hdr is "sensor" or "auto". options_->hdr is reachable —
    RawOptions : VideoOptions : Options, Options::hdr at core/options.hpp:291.
  - cinemate/src/module/sensor_detect.py resolve_log_encode_target(): take the mode's hdr
    flag and return None for 12-bit HDR, so cinepi_multi.py logs the reason at launch
    instead of burying it in cinepi-raw's warning.

  ** WRITE BOTH TO BE REPLACED, NOT DELETED. ** Name CCMP in the message and say the
  combination is unsupported UNTIL the decompand table is in the path — not that it is
  invalid. A future reader who deletes this guard without adding the precomposition
  reintroduces the exact bug.

STEP 3 — GATE. Re-record both takes: the log take must now be plain linear 12-bit and the
warning must name CCMP. Then confirm 16-bit ClearHDR + log-12 is untouched — ~12,618,004
bytes, tag 0xC618 present.

WHAT COMES AFTER, AND WHY THE GUARD IS TEMPORARY (section 9.7 P3)
  cinepi-raw `feature/ccmp12-decompand` (off dev, commits 4aef539 + b8a442a) now writes a
  CCMP decompand LinearizationTable into 12-bit ClearHDR DNGs. Once both branches land, the
  combination becomes legal via PRECOMPOSITION: decompand to 16-bit linear first, then
  log-encode.
  ** The source domain after decompand is 16-bit, so P3 uses the `16to10` spec, NEVER
  `12to10`. ** Reaching for 12to10 because the file is 12-bit IS the silent double-compand
  hazard, in a second form. That is the single thing most likely to go wrong at merge.
  Do not attempt P3 on this branch. Guard now; precompose when the branches meet.

BRANCHES. cinepi-raw feature/log-encode (@ 53f1f1a), cinemate feature/log-encode
(@ fdda434c). Put the guards THERE, not on dev, so they merge with the feature.
Do NOT push without asking. ** Do NOT push cinemate dev at all without asking — it deploys
the docs site. **

HARD RULES
  - If a doc contradicts the hardware, believe the hardware and fix the doc. The 542 above is
    a live example: it survived three documents.
  - Never hand-write a golden value.
  - Prove the bug on hardware before fixing it (STEP 1). If it refuses on its own, the doc is
    wrong and the fix is unnecessary.
```

---

## The merge-time checklist, when both branches land

| | |
|---|---|
| **Guard** | replaced by precomposition, not deleted |
| **Spec** | `16to10` — the domain after decompand is 16-bit, never `12to10` |
| **Order** | CCMP decompand first, then mu-law. Both are compressive; the order is not free |
| **Tag** | one `LinearizationTable` slot. Log-on writes the *precomposed* curve, not both |
| **Levels** | under either table the level tags describe the table's OUTPUT domain |
| **Test** | the CCMP table must still be byte-identical to `evidence/tables/*.txt` afterwards |
