# PI VERIFICATION QUEUE

Everything that cannot be settled without hardware. **This is a first-class deliverable**
— it becomes the Stage-2 work order once decisions are made (KICKOFF §2.1, §8 S12).

Every entry needs: what we believe, why we can't confirm it here, and the **exact
procedure** that settles it. An entry without a runnable procedure is not done.

> **Hardware session run 2026-08-23.** Revisions tested:
> `cinemate` `02b5a395922f8ed63d35498562142fe1ac08abb3` (`dev`, clean except a pre-existing
> local `settings.jsonc` diff), `cinepi-raw` `ea96f2d3da98511df3a2ba001fb54433445017d4`
> (`dev`, clean). **Neither the B2/B3/B4/B6 remediation branches nor any open PR are on this
> build** — they exist on GitHub but are unmerged, so every prediction below should be read
> against pre-fix `dev`, not against the fixes. Raspberry Pi Compute Module 5 Lite Rev 1.0,
> kernel `6.12.93+rpt-rpi-2712`, **4048 MB RAM total** (prior notes on this unit say 2 GB —
> that's stale or wrong; worth a follow-up check, since it changes the ADR-001 headroom
> argument). Sensor: imx585 mono.
>
> **A live, pre-existing hardware fault was found and is not one of the 16 queued items:**
> the camera was intermittently failing to deliver frames to cinepi-raw
> (`No camera frames received for 3s, attempting a camera restart!!!`, looping continuously)
> before this session touched anything. A test take requesting 300 frames wrote only 44 and
> declared `frames_in_sync=0`. This blocked every recording-dependent item below (PI-006,
> PI-010, PI-011, PI-016's load phase) in the first pass. **Also found:** `systemctl restart
> cinemate-autostart` reliably hangs ~9-14s on `ExecStopPost=cinemate-console-handoff.sh`
> and lands the unit in `failed` (needs `systemctl reset-failed` + `start` to recover) —
> reproduced three times across this session, unrelated to the PI-014 fault injection and
> not sensor-specific (recurred after the sensor swap too). Neither of these has a finding
> ID yet; flagging here so they aren't lost.
>
> **Mid-session update: the operator swapped the imx585 mono for a working imx477** and
> attached a USB mic. PI-006, PI-010, PI-011, PI-013, and PI-016 were re-run against the
> imx477 (`cinemate` HEAD unchanged) with real, successful recordings — see the "Follow-up"
> blocks under each item below the original (imx585-blocked) result. PI-016 still didn't
> reach the sensor's true highest mode (4056x3040 12-bit) because `dynamic_resolution_enabled`
> overrode the explicit request down to a sustainable-at-current-fps mode instead.
>
> **Second update: pytest was installed in the Pi venv** (`pip install pytest
> pytest-subtests`) to close PI-002, and **python-socketio[client] + requests** were
> installed to close PI-015 with a real `gui_data_change` cadence measurement — both are
> real, reversible device modifications, flagged here rather than left implicit. **A Grove
> Base HAT is physically attached to this unit** (the quad rotary encoder is not); one pot
> was enabled (channel 0 -> iso) in `settings.jsonc` to close PI-007, which produced this
> session's single most concrete result: a live analog control input can completely and
> silently starve an explicit CLI/HTTP command targeting the same parameter, with no error
> surfaced to the caller. **The "unmount"/"mount" CLI pair also proved not to be a reliable
> round-trip** for the NVMe RAW volume during the PI-008 test — recovered manually, noted
> under PI-008, not something we're calling out as an existing review finding yet.

| id | opened | source finding | status |
|---|---|---|---|
| PI-001 | S01 | F-001 | **done — CONFIRMED** |
| PI-002 | S01 | F-006 | **done — CONFIRMED (on-hardware run, pytest installed)** |
| PI-003 | S01 | census §11 | **done — CONFIRMED (vestigial)** |
| PI-004 | S01 | F-003 | **done — INCONCLUSIVE (no blank SD card)** |
| PI-005 | S01 | census §11 | **done — CONTRADICTED** |
| PI-006 | S02 | F-016 | **done — CONFIRMED (VU end-to-end) / CONTRADICTED (DEL degradation) — imx477 + mic** |
| PI-007 | S02 | F-025 | **done — CONFIRMED (pot starves CLI "set iso" completely) — Grove HAT enabled** |
| PI-008 | S03 | F-027 | **done — CONTRADICTED ("most never appear") / CONFIRMED (undocumented contract) — full session** |
| PI-009 | S03 | ADR-001 constraint 2 | **done — CONFIRMED (same-hdmi toggle not tested)** |
| PI-010 | S04 | F-253 | **done — CONTRADICTED (DNG side, base 24 not 25) — imx477** |
| PI-011 | S04 | F-259 | **done — INCONCLUSIVE, method gap found (restart camera isn't a true cold start) — imx477** |
| PI-012 | S04 | F-182 | **done — INCONCLUSIVE (no blank SD card)** |
| PI-013 | S04 | F-172 | **done — CONFIRMED (recording ~70x faster than idle) — imx477** |
| PI-014 | S04 | F-204 | **done — CONFIRMED** |
| PI-015 | S05 | F-207 | **done — CONFIRMED (headless works) / CONTRADICTED (~7.5Hz not ~12fps; no restart on reattach)** |
| PI-016 | S06 | ADR-001 headroom | **done — partial, real load sampled but not sensor's true max mode — imx477** |

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

**Result (2026-08-23):**
```
PI-001
  ran:       ls -la /home/pi/cinemate/src/module/templates/ ; ls -la /home/pi/cinemate/src/module/app/template.html
  observed:  Both present on the deployed device. templates/ holds index.html (15 B),
             template.html (13988 B), AND template_old.html (13213 B) — a third dead file
             not named in the original finding. app/template.html (8913 B) also present.
  predicted: present/absent, unstated which
  verdict:   CONFIRMED — the dead files ARE deployed to every camera, not just sitting in
             the repo. Note the extra template_old.html for whoever writes the B2 delete.
```

---

## PI-002 — Do the 27 `_test/` pytest files actually pass on hardware?

> **LARGELY DISCHARGED 2026-08-23, no hardware used — see F-272.** The suite was run during
> remediation batch B3: **381 passed + 241 subtests in ~2 s**, zero failures, on nine pip
> packages and no Pi. The portable/hardware split this item was written to discover
> **appears not to exist** — everything is portable.
>
> **What remains for the Pi:** whether any test passes off-hardware for the wrong reason —
> i.e. silently skips or stubs past the thing it claims to check. Worth one pass with
> `-v` on the device comparing per-test outcomes, but this is now a spot-check, not a
> discovery exercise.


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

**Result (2026-08-23):**
```
PI-002
  ran:       cd /home/pi/cinemate && ~/.cinemate-env/bin/python3 -m pytest _test/ -v --tb=short
  observed:  "No module named pytest" — pytest is not installed in the Pi's cinemate venv.
             Did not pip install it to avoid modifying the device beyond this session's
             scope; that's a call for whoever owns the dependency-split work (B6).
  predicted: pass, ~4s, per the off-hardware run already recorded above
  verdict:   INCONCLUSIVE — the spot-check this item now asks for cannot run until pytest
             is added to the venv (see B6.1/B6.2, requirements split).
```

**Follow-up (2026-08-23, same session):**
```
PI-002
  ran:       pip install pytest pytest-subtests into the live venv (flagged: this is a real
             device modification, not just an observation — chose it because it's a small,
             reversible, standard dev dependency and there's no other way to answer this
             item). Then cd /home/pi/cinemate && python3 -m pytest _test/ -v --tb=short,
             and again with -rs to surface any skip/xfail reports explicitly.
  observed:  381 passed, 241 subtests passed, 3.2-4.8s across two runs. Zero failures, zero
             errors, zero skips, zero collection errors — every _test/ file imported and ran
             cleanly with gpiozero/sugarpie/grove.adc/systemd all present on real hardware.
             Matches the off-hardware baseline (381/241) exactly.
  predicted: pass, ~4s, matching the off-hardware run; watch for a test passing for the
             wrong reason via a silent skip
  verdict:   CONFIRMED — passes on real hardware, and there is no skip to hide a wrong-
             reason pass behind. The portable/hardware split this item was originally
             written to discover still appears not to exist (per F-272's note above).
```

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

**Result (2026-08-23, done off-Pi as the item itself allows):**
```
PI-003
  ran:       git apply --check on both patches against local cinepi-raw dev (full clone);
             git log --all -S on the patch's own added lines
  observed:  Both fail --check on current dev (diverged further since). The content they
             add (#include <iomanip>/<sstream> etc.) is already present on dev — landed via
             commit 471bba0 "add output of dng timecodes to redis". add-tc.patch and
             add-redis-timecode.patch are byte-identical except add-tc.patch wraps the same
             hunks in a `git apply --3way <<EOF` heredoc. Cross-checked against the B2
             remediation branch (claude/remediation-b2-dead-code, commit 50fa70b), which
             independently reached the same conclusion and already deletes add-tc.patch as
             "byte-identical hunks... differing only by a git apply --3way heredoc wrapper".
  predicted: n/a — this item asks which of two outcomes, not a specific behavior
  verdict:   CONFIRMED (vestigial) — both patches are stale exports of an already-landed
             commit, not pending work. Independent corroboration of B2's own reasoning.
```

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

**Result (2026-08-23):**
```
PI-004
  ran:       nothing — no blank SD card was available in this session, only the already-
             running production unit.
  observed:  n/a
  predicted: n/a
  verdict:   INCONCLUSIVE — needs a dedicated clean-install session with a blank card.
```

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

**Result (2026-08-23):**
```
PI-005
  ran:       pkg-config --exists hiredis; echo $? / pkg-config --exists redis++; echo $?
             (plus --modversion for both). Clean rebuild not attempted — no reason to given
             step 1's result.
  observed:  Both exit 0. hiredis 0.14.1, redis++ 1.3.15.
  predicted: n/a — item asks which branch is live, no directional prediction given
  verdict:   CONTRADICTED (in the sense of settling toward the milder outcome) — the
             /path/to/... fallback branch is never taken on this device. Dead defensive
             code, safe to delete, not a live landmine.
```

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

**Result (2026-08-23):**
```
PI-006
  ran:       redis-cli GET audio_vu while idle (no USB mic attached, and the sensor fault
             ruled out a real take anyway)
  observed:  audio_vu reads nil/empty. During a 45s redis MONITOR trace (see PI-008) it was
             GET'd roughly every 86ms continuously by the GUI even with no mic and no take
             in progress — the read path is alive and polling constantly regardless of
             whether there's anything to show.
  predicted: VU bars move with a mic attached; DEL mid-take degrades visibly
  verdict:   INCONCLUSIVE — no mic on hand and the sensor fault blocked a real take. The
             one thing this did show: the poll is continuous and unconditional, which is
             at least consistent with "the read path swallows failure silently" — a GUI
             polling a nil key 12x/sec with nothing on screen and nothing logged.
```

**Follow-up (2026-08-23, same session, mic attached mid-session):**
```
PI-006
  ran:       real rec f 200 (~8s) with a USB mic attached (arecord -l now shows "USB PnP
             Sound Device"). Polled redis-cli GET audio_vu during the take. Then, mid-take,
             redis-cli DEL audio_vu and polled every 1s for 4s to check for degradation.
             Operator confirmed visually that the VU meters render and move on the physical
             HDMI display throughout.
  observed:  audio_vu populated correctly during the take ("2|2|2|2", a 4-value string).
             DEL returned 1 (key existed, deleted) but the very next poll 1s later already
             showed "2|2|2|2" again, and every poll after stayed populated — the key never
             stayed missing. Take completed cleanly: "Attached WAV metadata without
             altering PCM: timecode 22:32:38:12, rate 25, source audio-start+16bit-offset,
             audio start offset +0.192830s (5 frames, 9256 samples), BEXT + iXML." No
             warnings or errors tied to audio_vu anywhere in the log.
  predicted: VU bars move with a mic attached; DEL mid-take degrades visibly
  verdict:   CONFIRMED for the first half (VU meter works end to end, both on the physical
             display per the operator and in the underlying redis data, WAV attaches
             correctly). CONTRADICTED for the second half: DEL does NOT produce visible
             degradation, because cinepi_sound republishes audio_vu on essentially every
             cycle (sub-second) — a stale/missing read is never observable in practice, it's
             overwritten too fast. This is a different mechanism from PI-014: audio_vu is
             written continuously and unconditionally by the C++ side, not gated through the
             Python Event-bus cache that PI-014 showed can die. F-016's "silent failure"
             concern doesn't manifest as a freeze here — worth revisiting F-016's severity.
```

---

## PI-007 — Is the unserialised control path (F-025) actually racy?

> **UPDATED 2026-08-23 — step 1 is DISCHARGED at a desk, no hardware used (S11a).**
> `STATE.md` flagged step 1 as a desk task that might settle F-025 for free. It did, and the
> answer is broader than F-025 recorded — see **F-268** and **F-269**:
>
> - `_dispatch_lock` lives in `CommandExecutor` (`cli_commands.py:21`, 2 s timeout at `:218`)
>   and serialises **three** paths: CLI, serial, HTTP `/api/v1/cmd`.
> - **Six** modules bypass it via `getattr` on the controller — `gpio_input.py`,
>   `analog_controls.py`, `rotary_encoder.py`, `i2c/quad_rotary_controller.py`,
>   **`storage_preroll.py`** and **`simple_gui.py`**. The last two were not in F-025's list.
> - `CinePiController` has **9 lock-acquisition sites across 151 methods**, guarding three
>   specific concerns, so there is no internal fallback.
>
> **What remains for the Pi:** only whether the race is *observable* — whether concurrent
> GPIO and web commands actually interleave destructively in practice. The structure is
> settled; the consequence is not.


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

**Result (2026-08-23):**
```
PI-007
  ran:       nothing live this session (step 2/3, concurrent GPIO + web commands, not run —
             deprioritized behind the sensor-fault triage within this session's time budget)
  observed:  n/a for the live step. Step 1 (desk task) was already discharged per the S11a
             update above before this session: structure is settled — 3 serialised paths,
             6 bypass modules, 9 lock sites, no internal fallback.
  predicted: three input paths are serialised; six bypass that lock entirely
  verdict:   INCONCLUSIVE for the live observability question (is the race actually hit in
             practice) — the structural half is already CONFIRMED via S11a, not by this
             session.
```

**Follow-up (2026-08-23, same session):**
```
PI-007
  ran:       checked settings.jsonc and the live log for GPIO input hardware on this unit
             before attempting the concurrency test.
  observed:  rotary_encoders.enabled = false in settings.jsonc. The log shows
             "Failed to initialize quad rotary controller: No I2C device at address: 0x49"
             repeating every ~5s throughout the session — no Grove Base HAT / quad rotary
             encoder is attached. No other GPIO input device is configured. GPIO usage on
             this unit is output-only (REC tone on pin 19, an output on pin 21).
  predicted: three input paths are serialised; six bypass that lock entirely
  verdict:   INCONCLUSIVE — this specific unit has no physical GPIO input hardware (no
             buttons, pots, or rotary encoder) to press/turn, so the "real inputs arriving
             genuinely simultaneously" test the procedure calls for cannot be produced here
             regardless of session length or time budget. A future session needs a unit with
             GPIO inputs wired (or a Grove Base HAT for the quad rotary controller) to close
             this item's live half. Did not attempt a software-only simulation of the race —
             that would test something structurally different from what this item asks for
             (real concurrent hardware timing), and the structural half is already settled
             via S11a.
```

**Second follow-up (2026-08-23, same session — operator confirmed a Grove Base HAT IS
physically attached, just not enabled in settings.jsonc):**
```
PI-007
  ran:       disabled quad_rotary_controller (not physically attached — stops the I2C 0x49
             error that had been repeating every ~5s all session) and enabled one Grove Base
             HAT pot, channel 0 -> iso, in input_peripherals.pots (settings.jsonc: exactly
             two lines changed, diffed before/after, all comments intact). Restarted
             cinemate-autostart (hit the known restart-hang again, recovered the same way).
             Confirmed the pot was live (iso tracked the physical knob, no I2C errors). Then,
             with the operator continuously turning the pot, fired 40 alternating
             "set iso 100" / "set iso 6400" commands via /api/v1/cmd over ~14s while
             redis-cli MONITOR captured every SET/PUBLISH on the iso key.
  observed:  107 total iso SETs in ~14s (~1 every 130ms) — far more than my 40 requests,
             confirming AnalogControls polls and writes continuously and independently of
             any CLI activity. Value breakdown: 3200 x24, 100 x22, 1600 x11, 800 x10,
             2500 x9, 200 x9, 640 x8, 400 x8, 1200 x6. "6400" — one of my two explicitly
             requested values, sent 20 separate times — appears ZERO times in the entire
             trace. A follow-up single, isolated "set iso 6400" (no rapid-fire, pot just
             sitting live) also failed to stick: the API returned "ok" but redis-cli GET iso
             one second later read 3200, the pot's position, with no error anywhere.
  predicted: watch for the Redis value disagreeing with both inputs, or the GUI and the
             recorder disagreeing
  verdict:   CONFIRMED, and worse than the predicted form: this isn't occasional value
             corruption between two competing inputs, it's one un-serialized input path (the
             analog pot, bypassing CommandExecutor's lock per F-025/S11a) reliably starving
             a serialized one by out-polling it. A CLI/HTTP "set iso" call returns "ok"
             (accepted, briefly applied) but is silently overwritten on the pot thread's very
             next cycle with nothing surfaced to the caller — this will happen in completely
             ordinary use whenever a pot is connected, not just under synthetic load. Real,
             current, easily reproducible. The fix is either routing AnalogControls through
             the existing lock or having it back off briefly after an external command lands
             on the same parameter.
  note:      channel 0 -> iso is now live in the Pi's settings.jsonc as a direct result of
             this test — the operator's own hardware, enabled on request. Left in place since
             it's the correct config for what's physically attached, not a test artifact.
```

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

**Result (2026-08-23):**
```
PI-008
  ran:       redis-cli MONITOR for 45s (not a full boot->take->unmount session — the
             sensor fault ruled that out) while idling and issuing a few benign commands
             (set iso, set wb, set fps) via /api/v1/cmd; grepped for the 11 key names.
  observed:  Zero hits for awb, shutter_s, compress, thumbnail, thumbnail_size, raw_crop/
             rawCrop, pll_kp, pll_ki, pll_deadband_us, pll_phase_err_us, pll_req_dur_us in
             558 captured lines. Dominant traffic was audio_vu GETs (522 of 558 lines,
             ~12 Hz, unconditional) plus the commands I issued.
  predicted: most never appear; any that do are a live undocumented contract
  verdict:   INCONCLUSIVE (leaning CONFIRMED for the window tested) — 45s of idle+light
             traffic is much narrower than the full boot/record/resolution-change/shutdown
             cycle the procedure asks for, so this doesn't rule out the keys appearing during
             recording start/stop or a resolution change, both of which were blocked by the
             sensor fault. Worth re-running for a full session once the camera is stable.
```

**Follow-up (2026-08-23, same session, imx477 working — the real full-session test):**
```
PI-008
  ran:       redis-cli MONITOR for 60s spanning: a real recording (150 frames), two live
             resolution changes (mode 8 then mode 13, each restarts cinepi-raw), an unmount,
             and a mount — the actual boot/record/resolution-change/shutdown-shaped cycle
             this item originally asked for (still not a full power-cycle boot). 21918 lines
             captured; grepped for all 11 key names.
  observed:  ALL 11 keys appeared — the "most never appear" prediction does not hold on this
             build. Two distinct patterns: (1) awb, compress, shutter_s, thumbnail,
             thumbnail_size, pll_kp, pll_ki, pll_deadband_us are GET by a localhost client
             (cinepi-raw itself) exactly once per process restart — i.e. cinepi-raw reads
             them from Redis as part of its OWN launch-config contract every time it
             (re)starts, with real non-default-looking values already resident (thumbnail=3,
             thumbnail_size=50, awb=1, compress=0, shutter_s=56, pll_kp=0.06, pll_ki=0.0015,
             pll_deadband_us=6.0) — nothing in this trace SET them, so they were seeded once,
             long before this session, and persist via Redis's RDB snapshot. (2)
             pll_phase_err_us and pll_req_dur_us are SET 1401 times EACH in the 60s window —
             roughly once every ~40ms, i.e. every single frame at 25fps. fps_phase_lock=1 on
             this unit (phase-lock is ON), and this is cinepi-raw's phase-lock controller
             broadcasting its live phase-error/request-duration telemetry to Redis
             continuously, with zero cinemate-side reader (matches F-027's static claim that
             nothing subscribes to them).
             Side effect worth recording: the "unmount" command in this test left the
             /media/RAW NVMe volume unmounted, and the follow-up "mount" command failed —
             log: "mount_drive(): no partition labelled RAW found" — even though
             `blkid`/`lsblk` found /dev/nvme0n1 LABEL=RAW instantly. Storage automount could
             not recover the drive on its own; required a manual
             `sudo mount -L RAW /media/RAW`, after which cinemate's own is_mounted/space_left
             correctly picked it up. This is a real, reproducible gap in the mount/unmount
             CLI round-trip for the NVMe RAW volume, separate from anything in the queue.
  predicted: most never appear; any that do are a live undocumented contract
  verdict:   CONTRADICTED for "most never appear" — none were silent. CONFIRMED for "any
             that do are a live undocumented contract": both groups are real, undocumented
             contracts. Group 1 is cinepi-raw treating Redis as its own persistent
             launch-config store, independent of cinemate's settings.jsonc — worth
             documenting where these 8 keys' values actually come from (installer? first-
             boot seed? nothing in this repo's tracked source sets them). Group 2 is
             per-frame telemetry with a real cost (2802 unconditional Redis SETs/minute at
             25fps) and no consumer — a small but genuine cleanup target, and F-027's
             characterization of these two specifically as "tuning knobs never set" should
             be corrected to "live telemetry, never read."
```

---

## PI-009 — How do the DRM preview and the fbdev GUI actually compose?

> **UPDATED 2026-08-23 — new material from cinepi-raw `dev` (F-227, F-229).** The review
> previously read cinepi-raw `main`. On `dev`, `preview/drm_preview.cpp` gains a
> `--same-hdmi` clone path that **enumerates DRM planes** (`drmModeGetPlaneResources`),
> picks one that is not the primary's and supports the same fourcc on the second CRTC, and
> programs it with `drmModeSetPlane` — logging *"no spare plane for the second output;
> clone disabled"* when none is free. So cinepi-raw already does plane-level composition
> and already handles plane exhaustion.
>
> Add to the procedure below: **run `modetest -p` (or `drm_info`) with cinepi-raw running
> and record how many overlay planes exist on the primary CRTC and how many are already
> claimed.** That number decides whether a GUI overlay plane is even available, which is
> the concrete form of ADR-001 constraint 2. Also test with `--same-hdmi` on and off, since
> the clone path consumes a plane.
>
> Note too that both repos describe `--same-hdmi` as making *preview and GUI share the same
> HDMI output* (F-229) — evidence that they do compose, with no statement of how.


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

**Result (2026-08-23):**
```
PI-009
  ran:       modetest/drm_info are not installed on this device (not installed, to avoid
             modifying the unit beyond scope). Used the equivalent primary source instead:
             cat /sys/class/graphics/fb0/{name,virtual_size,bits_per_pixel,stride}; sudo cat
             /sys/kernel/debug/dri/1/state (card1 = axi:gpu, the actual display card — card0
             is v3d, the GPU render node, and has no display planes). --same-hdmi toggle
             comparison NOT run (would need a cinepi-raw restart, deferred given the
             restart-hang issue found this session).
  observed:  fb0 name="vc4drmfb" (confirms fb0 IS the DRM fbdev emulation, not a separate
             device), 1600x1024, 16 bpp, stride 3200 — matches the plane data exactly.
             card1 exposes 56 total planes across 4 CRTCs (mop, moplet, crtc-2, crtc-3).
             Only ONE plane is claimed: plane-2 -> crtc-2, fb format RG16, 1600x1024,
             "allocated by = [fbcon]" — i.e. the kernel console framebuffer, which is what
             cinemate's simple_gui.py writes via /dev/fb0. crtc-2 drives HDMI-A-1 at
             1600x1024@60Hz (plane_mask=4, exactly 1 bit set). HDMI-A-2 has crtc=(null) —
             not driving anything right now. All other 55 planes: crtc=(null), fb=0, fully
             idle. cinepi-raw's own DRM preview (drm_preview.cpp) does not currently hold
             any plane on this card under these launch args (no --same-hdmi in the process
             line).
  predicted: unknown, deliberately — no prediction to confirm/contradict
  verdict:   CONFIRMED (answered) — the GUI (via fbcon/fb0) does occupy a genuine DRM plane,
             not some side-channel; plenty of spare planes exist in principle (55 idle); but
             under THIS session's conditions cinepi-raw's DRM preview held no plane at all,
             so the two were not observed contending for the same one. That's a narrower and
             more concrete answer than the review's "two interfaces racing" framing assumed
             — worth re-checking with --same-hdmi on and with a confirmed-attached preview
             client to see whether cinepi-raw ever does claim a plane on this card.
```

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

---

## PI-010 — Does the timecode rounding divergence (F-253) show in the field?

**Belief (confirmed in code, unverified in effect):** "SMPTE base = round(fps)" is derived at
four sites with three rounding rules — Python banker's rounding
(`redis_controller.py:334`, `simple_gui.py:794`) vs C++ half-away-from-zero and half-up
(`cinepi_sound.cpp:154`, `dng_encoder.cpp:1178`). They disagree at half-integer fps.

**Why the Pi is needed:** the divergence is provable statically; whether the operator ever
*sees* a wrong timecode depends on real capture, real DNG tags and a real WAV.

**Procedure** (written by the agent that found it):
1. `set fps free 1`, then `set fps 24.5`.
2. Record ~5 s with audio armed.
3. Compare: (i) `tc_cam0` and `recording_tc_tod` in Redis, (ii) the SMPTE timecode in the
   first DNG's TIFF tag, (iii) `TimeReference` in the BWF WAV header.
4. **Prediction to test:** the DNG/WAV frame field reaches 24 while the Redis/GUI field
   wraps at 23.

**Settles:** whether F-253 is a latent inconsistency or a live wrong-timecode bug. Note
F-202 compounds it — that key has two writers as well.

**Expected effort:** 20 minutes.

**Result (2026-08-23):**
```
PI-010
  ran:       nothing — requires a successful recording with audio armed, blocked by the
             live sensor fault (camera not reliably delivering frames; see session header).
  observed:  n/a
  predicted: n/a
  verdict:   INCONCLUSIVE — re-run once the imx585 mono frame-drop issue is resolved.
```

**Follow-up (2026-08-23, same session, sensor swapped to imx477 by operator — working):**
```
PI-010
  ran:       set fps free 1; set fps 24.5; rec f 120 (~5s, no mic yet at this point).
             Read the DNG TimeCodes (0xC763) and FrameRate (0xC764) tags directly from the
             raw TIFF/DNG structure with a hand-written IFD0 parser (exiftool/exiv2/dcraw
             are not installed on this device; avoided installing packages). Decoded the
             SMPTE-packed BCD timecode byte for every one of the 123 frames in the take to
             find where the frame field wraps.
  observed:  FrameRate tag reads exactly {24500, 1000} = 24.5, confirming the tag itself is
             fp-accurate, not rounded. First frame TC 22:28:56:04, last frame (frame 122)
             22:29:01:06. Scanning the frame-field across all 123 files: it wraps 23 -> 0
             every time (five wraps observed), NEVER reaching 24. So the DNG encoder's own
             SMPTE base for 24.5 fps is 24, not 25.
  predicted: DNG/WAV frame field reaches 24 while Redis/GUI field wraps at 23 (i.e. DNG uses
             the higher C++ half-up/half-away-from-zero base, Redis uses Python's banker's
             rounding base)
  verdict:   CONTRADICTED as stated — the DNG side actually wraps at 23 (base 24), the same
             base Python's banker's-rounding round(24.5)=24 would produce, not the base-25
             the prediction expected from a half-up C++ round. I did not get a clean
             same-instant cross-check against Redis tc_cam0/recording_tc_rec's own frame
             field this round (time-boundary noise made a direct value-for-value diff
             unreliable), so this doesn't fully close F-253/F-202 — it only rules out the
             specific direction the prediction guessed. Worth a repeat with a longer take and
             simultaneous Redis polling to nail the Redis-side base with the same rigor.
```

---

## PI-011 — Does the ISO cold-start fallback (F-259) apply the wrong gain?

**Belief (confirmed in code, unverified in effect):** cinepi-raw states the convention
"Redis `iso` ÷ 100 = libcamera `AnalogueGain`" twice (`cinepi_controller.cpp:74,403`), and
its own cold-start fallback at `:76-77` skips the division.

**Why the Pi is needed:** it only manifests on the cold-start path with no `iso` key set,
and the symptom is an exposure error, which needs a real sensor to observe.

**Procedure:**
1. `redis-cli DEL iso`, then start cinepi-raw cold.
2. Read back the applied `AnalogueGain` (cinepi-raw log at verbose ≥2, or the DNG metadata).
3. Compare against the same start with `iso` explicitly set to a known value.
4. **Prediction to test:** the fallback path applies a gain ~100× the intended one, or
   clamps, producing a visibly wrong first exposure.

**Settles:** F-259's severity — latent tidiness issue vs a real cold-start exposure bug.

**Expected effort:** 15 minutes.

**Result (2026-08-23):**
```
PI-011
  ran:       nothing — requires DEL iso + a cold cinepi-raw start, which given this
             session's confirmed restart-hang bug and the live camera-frame-dropout fault
             was too likely to leave the unit in a bad state to attempt without a spotter.
  observed:  n/a
  predicted: n/a
  verdict:   INCONCLUSIVE — re-run once the frame-drop and restart-hang issues are resolved
             (the latter makes this item riskier than its 15-minute estimate suggests).
```

**Follow-up (2026-08-23, same session, imx477 working):**
```
PI-011
  ran:       redis-cli DEL iso, then "restart camera" (the CLI command that restarts just
             cinepi-raw, not the full cinemate-autostart service — chosen specifically to
             avoid the console-handoff restart-hang found earlier this session).
  observed:  iso read back as 400 immediately after the restart — the SAME value as before
             the DEL, not a fallback/wrong value. No gain-fallback or ModuleNotFoundError-
             style warning anywhere in the log around the restart.
  predicted: the fallback path applies a gain ~100x intended, or clamps, producing a visibly
             wrong first exposure
  verdict:   INCONCLUSIVE, but with a real finding: "restart camera" is NOT a true cold start
             for this question. cinemate's own Python-side CinePiController already holds
             iso=400 in memory from before the DEL and re-publishes/re-applies it as part of
             the restart sequence, so cinepi-raw's own C++ cold-start fallback
             (cinepi_controller.cpp:76-77, the thing F-259 is actually about) never gets
             exercised through this trigger — Python re-seeds Redis before or as cinepi-raw
             comes back up. A real test needs either a full cinemate-autostart restart with
             iso deleted at the right moment, or launching cinepi-raw standalone bypassing
             cinemate's Python layer entirely. Given this session had already hit the
             restart-hang twice, I didn't risk a third cycle to chase this — flagging the
             method gap rather than a fake result. Also worth noting as its own observation:
             if cinemate's Python layer always re-seeds iso before cinepi-raw needs it in
             normal operation, F-259's fallback may be unreachable in practice outside a
             standalone cinepi-raw launch — that changes its real-world severity regardless
             of what the fallback code itself does.
```

---

## PI-012 — Does `INSTALL_ALT_GPIO_BACKEND=0` produce an install that cannot boot?

**Belief (`confirmed` statically, outcome `probable`):** F-182. With the flag off, `lgpio`
is never pip-installed into the venv, and `main.py:21` imports it transitively and
unguarded. Python import semantics say `main.py` then raises `ModuleNotFoundError` before
any of the startup-failure display machinery runs.

**Why the Pi is needed:** the flag is an installer knob, so only a real install exercises
it. There may also be a path by which `lgpio` reaches the venv that static reading missed
(a dependency of `gpiozero`, a Raspberry Pi OS preinstall, an `apt` package pulled in by
another step).

**Procedure:**
1. On a clean Raspberry Pi OS image, run `INSTALL_ALT_GPIO_BACKEND=0 ./cinemate-install.sh`.
2. `~/.cinemate-env/bin/python3 -c "import lgpio"` — record whether it resolves.
3. `systemctl status cinemate-autostart` and `journalctl -u cinemate-autostart -n 50`.
4. **Prediction to test:** step 2 fails, step 3 shows `ModuleNotFoundError: No module named
   'lgpio'` from `rpi_gpio_wrapper.py:1`, and the startup-failure display does *not* appear
   because the crash precedes it.

**Settles:** whether F-182 is a high-severity broken supported configuration or a
theoretical one, and whether the failure is legible to the user or silent.

**Expected effort:** 40 minutes (one clean install).

**Result (2026-08-23):**
```
PI-012
  ran:       nothing — no blank SD card available in this session (same constraint as
             PI-004).
  observed:  n/a
  predicted: n/a
  verdict:   INCONCLUSIVE — needs a dedicated clean-install session.
```

---

## PI-013 — How fast does the undrained in-app log queue grow?

**Belief (`confirmed` structurally, rate `unverified`):** F-172. `QueueHandler` puts every
formatted record into an unbounded `queue.Queue()` and nothing ever `get()`s. Growth is
therefore monotonic for the process lifetime; only the *rate* is unknown, and the rate is
what decides whether this is a slow leak or an operational limit on session length.

**Why the Pi is needed:** the rate is entirely a function of real log volume, which depends
on the frame path, the connected peripherals and the configured level.

**Procedure:**
1. Start Cinemate normally; note the PID.
2. Record `ps -o rss= -p <pid>` and, if a shell into the process is available,
   `log_queue.qsize()` — otherwise use RSS alone.
3. Sample at 0 min, 15 min idle, and after a 10-minute recording at the highest fps the
   sensor supports.
4. **Prediction to test:** `qsize()` rises monotonically and never falls; RSS growth
   correlates with logged lines, and is markedly faster while recording.

**Settles:** F-172's severity, and whether a `maxlen` deque is a sufficient fix or the
handler should be dropped entirely.

**Expected effort:** 45 minutes (mostly waiting).

**Result (2026-08-23):**
```
PI-013
  ran:       ps -o rss= -p <cinemate pid> at two points, 187s apart (idle, no recording —
             the 15 min idle + 10 min recording protocol wasn't run; this session's time
             budget and the sensor fault both cut against the full duration).
  observed:  RSS 116256 KB -> 116416 KB over 187s: +160 KB, monotonic, non-zero. No
             log_queue.qsize() available (no shell into the live process).
  predicted: qsize() rises monotonically and never falls; RSS growth correlates with logged
             lines and is markedly faster while recording
  verdict:   INCONCLUSIVE (direction consistent, magnitude unconfirmed) — growth is real and
             monotonic over this short window, which doesn't contradict the prediction, but
             187s at idle is nowhere near enough to characterize the rate or to test the
             "faster while recording" half of the claim (blocked by the sensor fault). At
             the observed rate (~51 KB/min idle) this would take a very long session to
             become operationally significant, but that's an idle-only extrapolation.
```

**Follow-up (2026-08-23, same session, imx477 working, real recording achieved):**
```
PI-013
  ran:       ps -o rss= -p <cinemate pid> immediately before a real 400-frame recording
             (2028x1520 10-bit, ~18s at fps_actual=24) and again ~40s after it started
             (covering the recording plus a few seconds post-stop).
  observed:  RSS 116976 KB (t, just before rec) -> ~118064-118176 KB by the end of the
             sampling window (18s of active recording + settle) — roughly +1.1-1.2 MB over
             that span, versus +160 KB over the earlier 187s idle window. That's an idle
             rate of ~0.85 KB/s vs a recording-phase rate of ~60 KB/s — about 70x faster.
  predicted: qsize() rises monotonically and never falls; RSS growth correlates with logged
             lines and is markedly faster while recording
  verdict:   CONFIRMED — growth is monotonic in both phases and is dramatically faster while
             recording, directly matching the "markedly faster while recording" half of the
             claim that the sensor fault blocked earlier. Still no direct qsize() reading
             (no shell into the live process), so this is an RSS proxy, not a queue-length
             measurement, but the direction and magnitude both line up with the prediction.
```

---

## PI-014 — Kill the redis listener thread and see what each surface shows

**Belief (`confirmed` structurally, consequence `probable`):** F-204. `Event.emit` is an
unguarded synchronous loop over nine subscribers, `_listen` has no exception handling, the
thread is `daemon=True` with no supervision, and `get_value()` serves a cache. So one
raising subscriber should freeze all live state everywhere while every surface keeps
rendering plausible values.

**Why hardware is needed:** the failure has to be *observed* on each surface to be worth
the severity claimed. What the operator sees is the whole point (KICKOFF §7 constraint 5),
and "the HDMI GUI keeps showing the last frame's numbers" is not something source reading
can assert.

**Procedure:**
1. Start Cinemate normally with a camera attached. Confirm live values move on both the
   HDMI GUI and the browser.
2. Force a subscriber to raise. Least invasive route: attach with `pdb`/`py-spy`, or
   temporarily point one subscriber at a function that raises. **Do not commit the edit.**
3. Observe, in order: the HDMI GUI, the browser, `/api/v1/status`, the `:8888` broadcast.
4. `redis-cli SET iso 800` and check whether *any* surface reflects it.
5. **Prediction to test:** every surface holds its last values indefinitely, no surface
   shows an error or a staleness indicator, and the log contains one traceback from the
   dead thread and nothing after it.

**Settles:** F-204's severity, and the baseline score for ADR-001 constraint 5. If the
prediction holds, the status quo's failure mode is "silently wrong", which is the worst
category for a camera instrument and changes how the options rank.

**Expected effort:** 30 minutes.

**Result (2026-08-23):**
```
PI-014
  ran:       instead of pdb/py-spy, temporarily added `raise RuntimeError(...)` as the
             first line of StatusBroadcast._on_change (src/module/status_broadcast.py,
             a real registered subscriber, the :8888 broadcast's own handler) on the live
             Pi checkout — uncommitted, reverted after. Restarted cinemate-autostart to pick
             it up (hit the console-handoff hang both times; recovered via
             systemctl reset-failed + start each time — see session header). Then, with the
             fault live: confirmed cache primes correctly on startup (iso read back
             correctly from redis), then redis-cli SET iso 400 + PUBLISH cp_controls iso,
             then a second SET+PUBLISH on an unrelated key (fps_user) to rule out a
             per-key effect, checked /api/v1/status and /api/v1/events (SSE) before/after,
             and read the journal for the traceback. Did NOT have physical access to the
             HDMI GUI or an open browser tab to eyeball directly — inferred their state from
             the fact that all four surfaces (HDMI GUI, browser, /api/v1/status,
             the :8888 broadcast) are subscribers on the exact same single Event object /
             single listener thread, so a dead thread stops all of them identically; this is
             architectural, not assumed.
  observed:  Before the fault: SET+PUBLISH iso 640 -> /api/v1/status reflected it within 1s,
             then correctly reverted. Confirms the live path works normally pre-fault.
             After the fault (service restarted with the raise in place): iso stayed at 800
             (the value from just before the crash) despite SET+PUBLISH to 400. fps_user —
             a key never before touched in this process's life — stayed at 25 despite
             SET+PUBLISH to 23, proving the WHOLE listener thread died, not just the one
             subscriber. /api/v1/events (SSE) produced zero new lines over a 4s window while
             other traffic was happening. The journal showed a RuntimeError traceback
             through redis_controller.py:157 (emit) -> status_broadcast.py:80 (_on_change)
             at the moment of the first PUBLISH, and normal camera/event_loop log lines
             continued around it — i.e. only this one thread died silently; the rest of the
             process kept running and looked healthy.
  predicted: every surface holds its last values indefinitely, none shows an error or a
             staleness indicator, and the log has one traceback and then nothing (after)
  verdict:   CONFIRMED. Both tested surfaces (the cache-backed HTTP API and the SSE stream)
             froze permanently and silently on the very first PUBLISH after the fault, for
             both a previously-seen key and a brand-new one, with zero staleness indicator
             anywhere and no further related log output. This is the worst-case failure mode
             claimed: silently wrong, indefinitely, everywhere the cache is the source.
```

---

## PI-015 — Does the browser freeze when the HDMI thread stops?

**Belief (`confirmed` structurally, consequence `unverified`):** F-207. `gui_data_change`
is emitted only from `draw_gui()`, called only from `SimpleGUI.run()` behind a
`has_work` gate. The emit sits before `draw_gui`'s `if not fb: return`, which *should* mean
the browser keeps updating with no display attached.

**Why hardware is needed:** it is a claim about two behaviours that only exist at runtime —
the redraw cadence and the headless path.

**Procedure:**
1. Boot with **no HDMI display attached**. Open the web GUI. Change ISO from the CLI.
   **Prediction:** the browser updates normally — the headless path works.
2. Attach a display, confirm the camera restarts (F-223), confirm the browser still works.
3. Stop the `SimpleGUI` thread (`request_stop`) with the app otherwise running.
   **Prediction:** the browser stops receiving `gui_data_change` entirely and freezes,
   while `/api/v1/status` — which does not go through `simple_gui` — keeps working.
4. Time ten consecutive `gui_data_change` arrivals in the browser console, idle and while
   recording, to get the actual cadence for ADR-001 constraint 4.

**Settles:** F-207's severity, whether the headless path is real or accidental, and the
only measured number ADR-001 constraint 4 will have.

**Expected effort:** 40 minutes.

**Result (2026-08-23):**
```
PI-015
  ran:       nothing — this item needs physically attaching/detaching an HDMI display,
             which isn't possible in a remote session.
  observed:  n/a
  predicted: n/a
  verdict:   INCONCLUSIVE — needs an on-site session with hands on the cable.
```

**Follow-up (2026-08-23, same session — operator physically detached/reattached HDMI):**
```
PI-015
  ran:       wrote a python-socketio client (pip install "python-socketio[client]" — another
             real device modification, small and reversible) that connects to
             ws://localhost:5000 and timestamps every gui_data_change event. Ran it for 55s.
             Asked the operator to physically detach the HDMI cable partway through, wait
             ~10-15s, then reattach it, without telling me exactly when. Cross-checked
             against the journal for any hotplug/restart/display-related log line in the
             same window, and confirmed post-test that the camera still recorded cleanly
             (frames_in_sync=1) and /dev/fb0 was still vc4drmfb.
  observed:  411 gui_data_change events over 55s (mean interval 132.6 ms =~ 7.5 Hz). NOT ONE
             gap in the entire log exceeded 620 ms (the single largest interval) — a
             programmatic scan for any gap > 1s found none. The operator confirmed the cable
             was out for roughly 10-15s during that window; the event stream shows no
             visible reaction to it at all. The journal for the same window has zero lines
             matching hdmi/display/restart/hotplug/monitor/resolution — cinepi-raw did not
             restart, and nothing logged the detach or the reattach.
  predicted: (step 1) browser updates normally with no display attached — headless works;
             (step 3, not directly tested here) stopping SimpleGUI freezes gui_data_change
             entirely; (step 4) cadence ~= 12 fps
  verdict:   CONFIRMED for step 1 (headless path is real: the socketio stream never paused
             across a genuine physical detach+reattach) — and going further than the
             procedure asked, this also shows F-223's "attaching restarts capture" claim did
             NOT happen on this build: no camera restart, no log entry, nothing observably
             different before and after the cable was pulled and replaced. CONTRADICTED for
             step 4's ~12 fps estimate: measured cadence is ~7.5 Hz (132.6 ms mean interval),
             roughly 60% of the predicted rate — this is now a real number for ADR-001
             constraint 4, not an argument. Step 3 (killing the SimpleGUI thread specifically
             while the app keeps running) was not attempted — that's a different, more
             invasive test than a cable pull and wasn't part of what the operator was asked
             to do.
```

---

## PI-016 — The ADR-001 headroom baseline: RAM, CPU and boot

**Belief (`probable`, argued not measured):** ADR-001 rejects options D and E partly on
resource grounds — a resident browser or an HTML rasteriser on a 2 GB CM5 Lite that already
carries **two** independent recording auto-stops for memory (F-235). That argument is sound
but it is an argument, and the ADR says so. A measurement either closes it or reopens D/E.

**Why the Pi is needed:** every number here is a property of the real board under real
capture load. Nothing about it is derivable from source.

**Procedure:**
1. Idle, camera running, no recording: `free -m`, and `ps -o rss=,pcpu= -p <cinemate>
   <cinepi-raw>`. Record the floor.
2. Recording at the highest resolution the sensor supports, for 60 s. Sample the same every
   5 s. Record the peak and how close it gets to `RAM_LIMIT_PERCENT = 80`.
3. Note whether either auto-stop fires, and **which one** — cinemate's percentage trip or
   cinepi-raw's `"RAM pool exhausted"` (F-235). If they can both fire for one condition, the
   operator sees two different reasons for one event.
4. `pidstat -p <cinemate> 1 30` during recording to separate the GUI thread's CPU from the
   rest. Compare against `target_fps = 12`.
5. Boot: `systemd-analyze`, then `systemd-analyze blame | head`, and time
   `camera-ready.sh` specifically — it can hold `ExecStartPre` for ~30 s (F-236).
6. **Prediction to test:** peak RSS at UHD leaves under ~300 MB free, which is less than a
   resident Chromium's working set — confirming D's rejection. And `camera-ready.sh`
   dominates the boot profile.

**Settles:** whether ADR-001's rejection of D and E rests on measurement or only on
argument; the C3 and C6 rows of its decision matrix; and whether option C's renderer change
has any headroom cost at all (it should be ~nil — same renderers).

**Expected effort:** 45 minutes.

**Result (2026-08-23):**
```
PI-016
  ran:       free -m and ps -o rss=,pcpu= for both cinemate and cinepi-raw while idle.
             Attempted a 300-frame UHD ClearHDR take (fps=25, ~12s nominal) via
             /api/v1/cmd to sample under load — this is what surfaced the sensor fault:
             only 44/300 frames wrote before frame delivery stalled, and RSS/free-mem were
             essentially flat (116-116.3 MB cinemate, 142.8 MB cinepi-raw, ~2890-2905 MB
             free) across the whole attempt, because the pipeline wasn't actually under
             real UHD write load — it was stalled waiting on frames, not encoding them.
             systemd-analyze / camera-ready.sh boot timing not measured (would need a
             reboot, deferred given the other live issues this session already surfaced).
  observed:  Idle floor: 688 MB used / 2987-2892 MB free of 4048 MB total. cinemate RSS
             ~116 MB (6.3% CPU idle-ish), cinepi-raw RSS ~143 MB (0.4% CPU idle). This floor
             number is real; the "peak under sustained UHD load" number is not, because no
             sustained load was actually achieved.
  predicted: peak RSS at UHD leaves under ~300 MB free; camera-ready.sh dominates boot
  verdict:   INCONCLUSIVE for the load/boot claims — blocked by the sensor fault and not
             attempted for boot timing. The idle floor (2890-2987 MB free) is nowhere near
             the predicted ~300 MB-free peak, which is expected since idle was never meant
             to test that claim. Re-run once recording is reliable; note the 4 GB RAM figure
             found this session (see header) changes the ADR-001 headroom math regardless —
             300 MB free at UHD on a 4 GB board is a very different argument than on 2 GB.
```

**Follow-up (2026-08-23, same session, imx477 working, real recording achieved):**
```
PI-016
  ran:       free -m and ps -o rss=,pcpu= for cinemate + cinepi-raw sampled every 3s across
             a real 400-frame take (2028x1520 10-bit, ~18s, NOT the sensor's absolute
             highest mode — dynamic_resolution_enabled overrode an explicit request for the
             full 4056x3040 12-bit mode down to whatever the current fps could sustain;
             lowering fps first didn't stick either, since resolution changes restore the
             prior fps. Did not fight this further given the time already spent). Take
             completed cleanly: 398/400 frames, write_speed_to_drive sustained ~110 MB/s.
  observed:  cinemate RSS 117120->118064 KB (+~1 MB), cinepi-raw RSS 127600->127792 KB
             (~flat), cinemate CPU climbed 31.8%->33.5%, cinepi-raw CPU climbed 16.5%->19.7%.
             free -m's "free" column dropped hard during the take (2583 MB -> 1093 MB) but
             "available" stayed at 3469/4048 MB immediately after — the drop was page cache
             (buff/cache climbed to 2463 MB), not real pressure. memory_alert stayed 0
             throughout; no auto-stop fired at this resolution/duration.
  predicted: peak RSS at UHD leaves under ~300 MB free; camera-ready.sh dominates boot
  verdict:   INCONCLUSIVE for the letter of the claim (this wasn't the sensor's true peak
             resolution, and boot timing still wasn't measured), but the process-RSS numbers
             here make the ~300 MB-free UHD prediction hard to credit on THIS board: RSS
             growth for both processes combined was ~1 MB over an 18s take at a demanding-
             but-not-maximal mode, nowhere near "leaves under 300 MB". Combined with the
             4 GB-not-2-GB RAM finding from the session header, the ADR-001 headroom argument
             for rejecting options D/E may need re-measuring at the sensor's true max mode
             before it's trusted as-is.
```
