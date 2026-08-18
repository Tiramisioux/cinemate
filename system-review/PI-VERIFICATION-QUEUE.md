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
| PI-006 | S02 | F-016 | open |
| PI-007 | S02 | F-025 | open — **step 1 is a desk task, do it before booking Pi time** |
| PI-008 | S03 | F-027 | open |
| PI-009 | S03 | ADR-001 constraint 2 | open — **blocks S08** |

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

## PI-006 — Does the audio VU meter still render end to end?

**Belief (confirmed statically):** `audio_vu` is written by cinepi-raw
(`cinepi_sound.cpp:22`) and read by the HDMI GUI (`simple_gui.py:1166-1172`), with the key
name hand-duplicated on both sides (F-016).

**Why the Pi is needed:** nothing else exercises this contract. There is no test, and the
read path swallows failure (`except: return None`), so a broken contract is invisible
off-hardware.

**Procedure:**
1. Arm audio capture and start a take.
2. Confirm the VU meter renders and moves on the HDMI GUI.
3. `redis-cli GET audio_vu` during the take — confirm non-empty and changing.
4. Deliberately break it: `redis-cli DEL audio_vu` mid-take. Confirm the expected
   degradation (meter disappears) and note whether *anything* is logged.

**Settles:** whether F-016's silent-failure claim is real, and whether the degradation is
acceptable or needs a visible warning (KICKOFF §9 principle 3).

**Expected effort:** 15 minutes.

---

## PI-007 — Is the unserialised control path (F-025) actually racy?

**Belief (probable, not confirmed):** CLI, serial and HTTP commands are serialised under
`CommandExecutor._dispatch_lock`, but GPIO buttons, analog pots, the quad rotary and the
keyboard call `CinePiController` methods directly without it. Whether this is harmful
depends on locking *inside* `CinePiController`, which S02 did not trace (2626 LOC).

**Why the Pi is needed:** this is a concurrency question. It needs real inputs arriving
genuinely simultaneously, which cannot be produced off-hardware.

**Procedure:**
1. First, off-Pi: read `cinepi_controller.py` for internal locking. **If it locks
   internally, F-025 downgrades to a style issue and this entry can be closed without
   hardware.** Do this before booking Pi time.
2. If it does not lock: while turning an ISO pot continuously, issue rapid
   `set iso` commands over the CLI. Watch for the Redis value disagreeing with both
   inputs, or for the GUI and the recorder disagreeing.
3. Repeat with a GPIO resolution switch versus an HTTP `set_resolution` — the
   higher-stakes pairing, since resolution changes restart the camera.

**Settles:** F-025's severity. Step 1 may settle it for free.

**Expected effort:** 30 minutes on the Pi, but do step 1 first — it is a desk task.

---

## PI-008 — Which of the 11 orphaned Redis keys actually move?

**Belief (confirmed statically):** 11 keys cinepi-raw handles have zero references in
cinemate (F-027). Six are control handlers that cannot fire, three are tuning knobs never
set, two are telemetry nobody reads.

**Why the Pi is needed:** static analysis proves cinemate never writes them. It cannot
prove nobody does — these are reachable by hand with `redis-cli`, and groups B/C read like
a deliberate manual tuning surface. Only observation distinguishes "vestigial" from
"undocumented debug feature".

**Procedure:**
1. `redis-cli MONITOR > /tmp/redis-trace.txt` for a full session: boot, a take, a
   resolution change, shutdown.
2. `grep -oE '"(awb|shutter_s|compress|thumbnail|thumbnail_size|raw_crop|rawCrop|pll_kp|pll_ki|pll_deadband_us|pll_phase_err_us|pll_req_dur_us)"' /tmp/redis-trace.txt | sort | uniq -c`
3. Anything with a nonzero count has a writer this review did not find — investigate that
   writer before concluding anything.
4. Ask the operator directly whether the PLL knobs are a tuning workflow they use.

**Settles:** whether F-027's groups are dead code to remove or an undocumented feature to
document. Step 4 may settle most of it faster than step 1.

**Expected effort:** 20 minutes, plus one question to the operator.

---

## PI-009 — How do the DRM preview and the fbdev GUI actually compose?

**Belief (partly confirmed):** cinepi-raw draws preview through DRM/KMS
(`drm_preview.cpp:337,350`) and holds DRM master, which
`dualHdmiPreviewStage.cpp:5-18` states is exclusive per GPU. cinemate's HDMI GUI writes the
legacy fbdev node directly (`framebuffer.py:84,136`). Two different kernel interfaces to
one display.

**Why the Pi is needed:** **this is the single most important unverified fact in the
review.** Source establishes *that* two interfaces are in use. It cannot establish z-order,
whether the GUI occupies a genuine overlay plane or races the same scanout buffer, what
happens on mode change, or whether tearing occurs. None of that is inferable.

**This blocks ADR-001.** KICKOFF §7 constraint 2 asks exactly this, and S08 must not answer
it from reasoning. Options D and E depend on it entirely; even option C's PIL backend
depends on the answer holding.

**Procedure:**
1. With cinepi-raw running and the GUI painting:
   `cat /sys/class/graphics/fb0/{name,virtual_size,bits_per_pixel,stride}`
2. `sudo cat /sys/kernel/debug/dri/0/state` — record planes, CRTCs, z-order, formats.
3. `ls -l /sys/class/drm/*/` and identify which connector/CRTC is driving HDMI.
4. Confirm whether `fb0` is the DRM fbdev emulation (`name` typically reports the DRM
   driver) or an independent device.
5. Stop cinemate's GUI only, leaving cinepi-raw running. Does preview still paint? Then the
   reverse. Record both.
6. Change resolution mid-session (which restarts the camera) and watch whether the GUI
   survives the mode change or has to repaint.

**Settles:** ADR-001 constraint 2, and the feasibility of options D and E. Step 5 is the
decisive one — it establishes whether the two are genuinely independent layers or one is
overwriting the other.

**Expected effort:** 45 minutes. **Do this before S08 if at all possible.**

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
