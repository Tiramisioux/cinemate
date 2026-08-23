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
| PI-010 | S04 | F-253 | open |
| PI-011 | S04 | F-259 | open |

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
