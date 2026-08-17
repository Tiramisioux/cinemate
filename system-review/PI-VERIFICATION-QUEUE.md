# PI VERIFICATION QUEUE

Everything that cannot be settled without hardware. **This is a first-class deliverable**
— it becomes the Stage-2 work order once decisions are made (KICKOFF §2.1, §8 S12).

Every entry needs: what we believe, why we can't confirm it here, and the **exact
procedure** that settles it. An entry without a runnable procedure is not done.

| id | opened | source finding | status |
|---|---|---|---|
| PI-001 | S01 | F-001 | open |
| PI-002 | S01 | F-006 | open |
| PI-003 | S01 | census §11 | open |
| PI-004 | S01 | F-003 | open |
| PI-005 | S01 | census §11 | open |

---

## PI-001 — Does the installer deploy the four dead HTML templates?

**Belief (confirmed statically):** `src/module/templates/*.html` and
`src/module/app/template.html` (928 LOC total) are referenced by no code, and the only
Flask app resolves templates to `src/module/app/templates/`.

**Why the Pi is needed:** the installer copies or clones `src/` wholesale; whether the
dead files land on the device is a property of the deployed filesystem, not of the
source. Harmless either way, but it settles whether deletion has any deployment effect.

**Procedure:**
1. On a freshly installed Pi: `ls -la /home/pi/cinemate/src/module/templates/`
2. `ls -la /home/pi/cinemate/src/module/app/template.html`
3. Record present/absent.

**Settles:** whether F-001's fix is "delete 928 dead LOC from the repo" (no deployment
change) or "delete 928 dead LOC that are also shipping to every camera".

**Expected effort:** 2 minutes on an existing install.

---

## PI-002 — Do the 27 `_test/` pytest files actually pass on hardware?

**Belief (unverified):** 27 pytest files exist and none run in CI (F-006). Whether they
currently *pass* is unknown — they have never been observed running.

**Why the Pi is needed:** several tests import modules that import `gpiozero`, `sugarpie`,
`grove.adc`, `systemd` — hardware-only packages. A Mac run will error at import for an
unknown subset. Establishing the true pass/fail baseline needs the real venv.

**Procedure:**
1. On the Pi, in the CineMate venv: `cd /home/pi/cinemate && python -m pytest _test/ -v --tb=short 2>&1 | tee /tmp/pytest-baseline.txt`
2. Record: passed / failed / errored-at-collection counts.
3. Separately, on a Mac: same command; diff the collection errors.

**Settles:** the split between "tests that are portable and belong in CI" (F-006's fix)
and "tests that need hardware and need a marker". Without this the CI proposal in S06 is
guesswork.

**Expected effort:** 10 minutes. **Do this early in Stage 2 — S06's CI proposal depends
on it.**

---

## PI-003 — Are `add-redis-timecode.patch` and `add-tc.patch` applied, pending, or vestigial?

**Belief (unverified):** two patch files sit at the cinepi-raw root. Their names suggest
timecode features that may already be merged.

**Why the Pi is needed:** not strictly hardware — but it needs the real build tree and
history. The shallow read-only clone used in this review has no `dev` branch and no full
history to test-apply against.

**Procedure:**
1. In a full cinepi-raw checkout on `dev`: `git apply --check add-redis-timecode.patch; echo $?`
2. Same for `add-tc.patch`.
3. `git log --oneline --all -S "$(head -20 add-tc.patch | grep '^+' | head -3)"` to find
   whether the hunks already landed.

**Settles:** whether these are dead files to delete (F-012 neighbours) or un-landed work.

**Expected effort:** 10 minutes. **Can be done on any machine with a full clone — not
truly Pi-bound.** Reclassify once a full checkout is available.

---

## PI-004 — Does a clean install succeed, and is `flask` genuinely only transitive?

**Belief (confirmed statically):** the installer never reads `requirements.txt`
(F-003); `flask` appears in no installer pip list, arriving only via `flask_socketio`.

**Why the Pi is needed:** dependency resolution outcome is a property of the real pip run
against real ARM wheels on the real Pi OS image.

**Procedure:**
1. Flash a blank SD with the documented base image.
2. Run `cinemate-install.sh` end to end; capture full log.
3. `source <venv>/bin/activate && pip show flask` → record version and `Required-by`.
4. `pip freeze > /tmp/actual-installed.txt` and diff against both `requirements.txt` and
   the installer's inline list.

**Settles:** F-003's remediation choice, and whether the transitive-`flask` situation is
currently fragile or merely untidy.

**Expected effort:** 1–2 hours (full install). Combine with any other clean-install test.

---

## PI-005 — Is the meson `/path/to/...` fallback branch ever taken?

**Belief (confirmed statically):** `cinepi/meson.build` contains literal
`include_directories('/path/to/hiredis/includes')` and
`include_directories('/path/to/redis++/includes')` in the branches taken when
`pkg-config` cannot find hiredis / redis++.

**Why the Pi is needed:** whether `pkg-config` finds these depends on what the installer
put on the device.

**Procedure:**
1. On the Pi: `pkg-config --exists hiredis; echo $?` and `pkg-config --exists redis++; echo $?`
2. If either returns non-zero, the fallback branch is live and the build is relying on a
   placeholder path — a real bug.
3. Rebuild cinepi-raw from clean and capture meson's configure output.

**Settles:** whether this is dead defensive code (harmless, delete) or a live landmine
that happens to be masked because pkg-config always succeeds today.

**Expected effort:** 5 minutes for steps 1–2; 30+ minutes for a clean rebuild.

---

## Notes on scope

Per KICKOFF §2.1, these categories are **unverifiable in this review by construction**
and will accumulate entries in later sessions:

- timing and refresh cadence (S07/S08 — GUI redraw rate)
- thermals and sustained throughput
- DRM/framebuffer ownership and compositing (S08 — decisive for ADR-001 options D and E)
- sensor behavior and mode switching
- storage throughput and the RAM auto-stop at UHD
- audio/video sync

**S08 in particular must not resolve ADR-001 without queueing the DRM-ownership test** —
options D and E stand or fall on it.
