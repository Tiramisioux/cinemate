# Install script vs. install docs — drift report

**Session:** S10 · **Pi used:** no · **Branch:** `dev`, both repos
**Scope:** `cinemate-install.sh` (1916 LOC) × `docs/installation-steps.md` (1061 LOC), plus
`services/` · **Decides:** F-003's two remediation options

---

## 1. Verdict

**They agree on everything mechanically checkable. The problems are structural, not
factual.**

| checked | result |
|---|---|
| sensor-driver repo URLs and refs | **match** — `Tiramisioux/imx283-v4l2-driver`, `imx585-v4l2-driver`, both at `6.12.y` |
| libcamera branch | **match** — `cinemate` in both |
| GitHub URLs shared | 7 |
| absolute paths shared | 16 |
| systemd unit set, both directions | **exact match, 17 names** |
| subjects flagged by the step-name matcher as "missing" | **all present in the doc's prose** — `redis-plus-plus`, `libtiff`, the venv, `lgpio`, the loader config, `.asoundrc`, post-processing configs, the overclock |

For a 1916-line installer against a 1061-line document that was written as an independent
manual-install walkthrough, that is a strong result (F-267), and it is consistent with
S09's finding that the docs are the best-maintained boundary in this system.

**Three real problems**, none of them a factual disagreement:

1. **F-264 (high)** — the two repos that move most are the two nothing pins.
2. **F-265 (medium)** — no step-level correspondence between the 27 installer steps and the
   doc's 18 sub-headings.
3. **F-266 (medium)** — the recovery console is absent from all 1061 lines.

---

## 2. F-264 — the unpinned pair

The installer pins its dependencies **except the two that matter**:

| repo | ref | pinned? |
|---|---|---|
| `imx283-v4l2-driver` | `6.12.y` | ✅ |
| `imx585-v4l2-driver` | `6.12.y` | ✅ |
| `libcamera` | `cinemate` | ✅ |
| `cpp-mjpeg-streamer`, `redis-plus-plus`, `lg` | *(empty)* | ⚠ but low-churn |
| **`cinemate`** | *(empty)* | ❌ |
| **`cinepi-raw`** | *(empty)* | ❌ |

The doc's `git clone` commands pin nothing either, so both paths take whatever the default
branch holds that day.

**S07b measured what that costs.** cinepi-raw's `main` and `dev` differ by **45 files and
+7164 lines**, including **four `CONTROL_KEY_` macros of the cross-repo Redis contract**
(F-226) and a `--same-hdmi` clone implementation that exists on one branch and not the other
(F-227). These two programs talk to each other over a key contract that differs between
branches, and **nothing anywhere records a known-good pairing.**

Combined with F-190 — zero version pins across 23 pip packages — **an install performed on
two different days is not the same system**, and there is no way to say which combination
was tested.

**This is the review's duplicated-truth thesis in its reproducibility form:** the pairing is
real, it is load-bearing, and it is written down nowhere.

### Recommendation

Add a pairing manifest — a `versions.env` the installer sources and the docs quote:

```sh
CINEMATE_REPO_REF=v3.3.2
CINEPI_RAW_REPO_REF=<the cinepi-raw commit tested with it>
```

Cheap, and it makes "which cinepi-raw goes with this cinemate?" answerable for the first
time. Note this clone has **no git tags** (F-263), so the review cannot check what release
tags currently exist.

---

## 3. F-265 — no step-level correspondence

`cinemate-install.sh` prints **27 numbered steps**:

```
[01] Validating environment and installer configuration
[02] Installing bootstrap tools
...
[18] Writing runtime loader configuration
...
[27] Finishing up
```

`installation-steps.md` is a manual-install narrative under 18 `###` sub-headings with
different names in a different order. The doc never cites a step number; the installer never
cites a doc section.

**An operator whose install fails at `[18]` has nothing to look up.** That is the concrete
cost, and it lands on exactly the person least able to absorb it.

This is not a content gap — every step's subject is covered in the prose. It is a
**navigability** gap, and the fix is cheap: print the doc anchor alongside the step name, or
add the step number to each heading. Given that the installer already has a `section()`
helper and a `STEP_COUNTER`, one is a one-line change to that function.

### A note on method

The first pass at this used keyword matching between step names and headings and produced
**11 apparent "NO MATCH" steps**. Grepping the doc for each subject showed the doc covers
essentially all of them. **The matcher was measuring heading-name similarity, not coverage.**
Reported here as a method note rather than a finding, and the numbers above are the
corrected ones.

---

## 4. F-266 — the recovery console is missing from the install doc

`cinemate-recovery` appears **zero times in 1061 lines**. Not in the "Cinemate services"
section — which covers `storage-automount`, `wifi-hotspot`, `redis-log-maintenance` and
`cinemate-autostart` under four `####` headings — and not anywhere else.

It has its own published page (`recovery-console.md`, 111 LOC) and appears in
`system-services.md`, so it is not undocumented. But **a reader following the install never
learns it exists.**

That matters more than a typical omission. Per F-221, the recovery console is the
best-engineered component in the system, and its stated purpose is being reachable when
*"the venv is broken"* and *"redis is down"*. A recovery tool the operator only discovers by
reading a page they had no reason to open is a recovery tool that is not there when needed.

**Fix:** one `####` sub-heading in the services section, naming the port and linking to
`recovery-console.md`.

---

## 5. Deciding F-003 — which dependency list is canonical

S01 laid out two options and leaned toward **option 1** (installer canonical, delete
`requirements.txt`) as *"the smaller change and the honest one"*. **S10 recommends option 2
instead**, because three findings that postdate F-003 change the arithmetic.

**1. CI is coming, and it needs an installable list off-Pi.** `STANDARDS-PROPOSAL.md` §6.2
drafts a pytest job for the **381 tests that have never run** (F-222). Under option 1 that
workflow hand-lists its packages — and the draft `checks.yml` already does, with a comment
explaining why. **That is a third copy of the dependency set**, created by the very change
meant to remove the second. Option 1 does not delete the duplication; it relocates it into
CI where nobody looks.

**2. F-264 makes pinning the priority, and option 1 leaves nowhere to pin.** Deleting the
file removes the only artefact shaped like a place to record versions.

**3. The hardware/portable split is not as clean as F-003 assumed.** F-182: `lgpio` is
installed conditionally but imported unconditionally at the top of the boot chain, so
"hardware-only packages" is not a safe category to reason about casually.

### Recommended shape

| file | contents | consumed by |
|---|---|---|
| `requirements.txt` | portable runtime + test deps, **pinned** | the installer, the CI test job |
| `requirements-hardware.txt` | Pi-only: `grove.py`, `sysv_ipc`, `smbus2`, `rpi_hardware_pwm`, `pigpio-encoder`, the adafruit set, **`lgpio`** | the installer only |
| `docs/requirements-docs.txt` | `mkdocs*`, `schemdraw*` | `docs.yml` only |

The installer becomes
`pip install -r requirements.txt -r requirements-hardware.txt`, replacing the 23-package
literal at `cinemate-install.sh:922-927`. Declare `flask` explicitly wherever it lands
(F-003, F-186). Drop `wave` (stdlib, F-184), `pyaudio` and `sounddevice` (imported nowhere,
F-187, F-188), and the duplicate lines (F-185).

**`lgpio` belongs in the hardware file unconditionally**, not behind
`INSTALL_ALT_GPIO_BACKEND` — that is F-182's fix and it falls out of this change for free.

**Where the split line actually goes is `unverified`** and depends on which packages the
portable tests import. That is **PI-002**: run the suite once, read the import errors, and
the line draws itself. Do not guess it.

### Risk

Medium, and unchanged from F-003's assessment: this is a boot-path change to the installer
and needs a clean install to validate — **PI-004**, and now also **PI-012**, since the
`lgpio` move touches the same code path.

---

## 6. Not re-derived

Per `STATE.md`'s "Do not redo" list, S10 did not recount these:

- **`shellcheck` on the installer** — S06. 15 findings across 11 scripts, **one** in the
  1916-line installer. F-174..F-179. It is a strength.
- **Idempotency** — S06, F-192. Idempotent *by construction*, with the reasoning written in
  the code. One gap, F-193: the libcamera patch has no `else` branch, so an upstream change
  makes it a silent no-op.
- **The dependency package lists** — `findings/F-003.md` has both, computed. §5 above
  chooses between the options; it does not recount.

## 7. Carried in from other sessions, still open against the installer

| finding | |
|---|---|
| F-161 | `services/cinemate-services.Makefile` recurses into three deleted directories |
| F-162 | `services/Makefile`'s `uninstall` targets generate no recipe |
| F-163 | `python3-systemd` reachable only through dead code — F-032's unused apt list becomes 8 of 11 |
| F-165 | root `CMakeLists.txt` references a directory that does not exist, so `cmake .` fails immediately |
| F-182 | `INSTALL_ALT_GPIO_BACKEND` advertised as optional but load-bearing for boot → PI-012 |
| F-195 | the two scripts the installer *generates* are never linted by anything |
| F-236 | `camera-ready.sh` can hold `ExecStartPre` ~30 s before `main.py` starts |

---

## 8. Confidence

Every count in §1 is a literal diff over the two files and is reproducible by inspection.
Every claim in §§2–4 cites a line read in this repository.

- **§3's step-correspondence numbers were wrong on the first attempt** and the corrected
  method is described in place. Treat the "no step-level correspondence" claim as being
  about heading structure, which is what was actually measured.
- **§5 is a recommendation, not a finding.** The three-file split's exact contents are
  `unverified` pending PI-002.
- **No install was performed.** Nothing about installer *behaviour* is asserted as observed;
  PI-004 and PI-012 remain the way to settle that.
- `changelog.md`-style release-tag checks are impossible here — this clone has no tags
  (F-263).
