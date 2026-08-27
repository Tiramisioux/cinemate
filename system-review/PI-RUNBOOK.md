# Pi runbook — the hardware session, self-contained

**For:** a session running where the Raspberry Pi is reachable. **Nothing in this file
depends on the review ledger** — everything you need is here.

**You are recording observations, not fixing anything.** No commits to the camera's code,
no edits to `src/`. If something is broken, write down what you saw; someone decides what
to do about it afterwards.

---

## Before you start

**Say which revisions you are testing.** Everything below is meaningless without it:

```
git -C ~/cinemate   rev-parse HEAD && git -C ~/cinemate   status -sb | head -1
git -C ~/cinepi-raw rev-parse HEAD && git -C ~/cinepi-raw status -sb | head -1
uname -a && cat /proc/device-tree/model && free -m
```

Paste that at the top of your results.

## How to record a result

For each item, write four lines:

```
PI-0NN
  ran:       <what you actually did, if it differed>
  observed:  <what happened>
  predicted: <copied from the item>
  verdict:   CONFIRMED | CONTRADICTED | INCONCLUSIVE
```

**A CONTRADICTED prediction is the most valuable outcome in this file.** These predictions
were written by reading source code with no hardware. Several of them are probably wrong.
Say so plainly — do not reconcile a result to match the prediction, and do not soften it.

If something cannot be run (missing hardware, a step that does not apply), write
INCONCLUSIVE and why. That is a real result too.

---

# Tier 1 — do these three even if you do nothing else

## PI-014 · Kill the redis listener and watch every surface

**Settles the worst defect the review found.** The claim: one raising subscriber killed the
listener thread permanently, and because reads come from a cache rather than from redis,
every surface then showed *plausible frozen values with no error anywhere*.

1. Start Cinemate normally with a camera attached. Confirm live values move on both the
   HDMI GUI and the browser.
2. Force a subscriber to raise. Least invasive: attach with `py-spy`/`pdb`, or temporarily
   point one subscriber at a function that raises. **Do not commit that edit.**
3. Observe **in this order** and note each: the HDMI GUI · the browser · `/api/v1/status`
   · the `:8888` broadcast.
4. `redis-cli SET iso 800` — does *any* surface reflect it?
5. Check the log for a traceback, and whether anything appears after it.

**Predicted:** every surface holds its last values indefinitely, none shows an error or a
staleness indicator, and the log has one traceback and then nothing.

**If you are testing a build that includes the fix**, the prediction inverts: the traceback
is logged, the other subscribers still run, and step 4 updates normally. Note which build
you are on.

⏱ ~30 min

## PI-004 + PI-012 · A clean install, twice

**Gates the dependency PR.** Two questions: does a clean install work at all, and is
`INSTALL_ALT_GPIO_BACKEND=0` — a documented, supported option — actually bootable?

1. Blank SD card, fresh Raspberry Pi OS Lite Bookworm 64-bit. Run the installer normally.
2. Confirm the camera reaches ready and records a clip.
3. `~/.cinemate-env/bin/pip list` — is `flask` present? Is `pyserial`? **Neither is
   explicitly installed by anything**; both are believed to arrive as transitive
   dependencies. Note what actually pulled them: `pip show flask` → `Required-by`.
4. Second clean install: `INSTALL_ALT_GPIO_BACKEND=0 ./cinemate-install.sh`
5. `~/.cinemate-env/bin/python3 -c "import lgpio"` — does it resolve?
6. `systemctl status cinemate-autostart` and `journalctl -u cinemate-autostart -n 50`

**Predicted:** step 3 shows both present but only transitively. Step 5 fails, and step 6
shows `ModuleNotFoundError: No module named 'lgpio'` from `rpi_gpio_wrapper.py:1` — with
the startup-failure display *not* appearing, because the crash precedes it.

⏱ ~90 min, mostly waiting on two installs

## PI-009 · Count the free DRM overlay planes

**The last open question in the GUI architecture decision.** Everything else about it has
been settled from source; this has not, and cannot be.

1. With cinepi-raw running: `modetest -p` (or `drm_info`). Record **how many overlay planes
   exist on the primary CRTC and how many are already claimed.**
2. Repeat with `--same-hdmi` on and off — the clone path consumes a plane.
3. Note which connector is primary and whether the GUI's framebuffer appears as a plane at
   all, or is composited some other way.

**Predicted:** unknown, deliberately. This is the one item with no prediction, because the
whole point is that reading the source could not produce one. Report the plane table as-is.

⏱ ~20 min

---

# Tier 2 — worth doing in the same sitting

| | question | procedure | predicted |
|---|---|---|---|
| **PI-002** | Do the tests pass on hardware? | `cd ~/cinemate && python3 -m pytest _test/ -q -p no:randomly` | **Pass, ~4 s.** Already confirmed off-hardware, 386 tests. On the Pi, watch for any test that passes by silently skipping the thing it claims to check |
| **PI-016** | RAM/CPU/boot headroom | Idle then recording at max resolution: `free -m`, `ps -o rss=,pcpu=`, sample every 5 s for 60 s. Then `systemd-analyze blame \| head` | Peak leaves under ~300 MB free at UHD. `camera-ready.sh` dominates boot — it can hold `ExecStartPre` ~30 s |
| **PI-013** | Does the log queue grow without bound? | Note the PID, sample `ps -o rss= -p <pid>` at 0 / 15 min idle / after a 10-min take | Monotonic growth, faster while recording. **Fixed in the correctness PR** — if testing that build, expect it to plateau |
| **PI-015** | Browser cadence and the headless path | Boot with **no HDMI attached**, open the web GUI, change ISO from the CLI. Then attach a display and confirm the camera restarts. Then time 10 `gui_data_change` arrivals in the browser console | Headless works. Attaching restarts capture. Cadence ≈ 12 fps |
| **PI-008** | Which orphaned redis keys move? | `redis-cli MONITOR` during a full session — boot, record, stop, unmount. Grep for: `awb compress thumbnail thumbnail_size shutter_s rawCrop raw_crop pll_kp pll_ki pll_deadband_us pll_phase_err_us pll_req_dur_us` | Most never appear. Any that do are a live contract nobody documented |
| **PI-006** | Does the audio VU meter work end to end? | Connect a USB mic, watch the HDMI GUI's right edge and the browser | VU bars move in both; a `WAV` badge appears once a take has both DNGs and a WAV sidecar |
| **PI-010** | Timecode rounding divergence | Record at 23.976 and 29.97. Compare the DNG timecode against the folder name and the GUI | Four sites compute "SMPTE base" with three different rounding rules; a mismatch shows at fractional rates or nowhere |
| **PI-011** | ISO cold-start fallback | `redis-cli DEL iso`, start cinepi-raw cold, read back the applied `AnalogueGain` | The fallback applies a gain ~100× intended, or clamps — a visibly wrong first exposure |
| **PI-007** | Is the control path racy? | Trigger a GPIO button and a web command for the same parameter simultaneously, repeatedly | Three input paths are serialised; **six bypass that lock entirely**. Whether it is observable is the question |

## Tier 3 — only if you have time

**PI-001** do the four dead HTML templates get deployed? (`ls ~/cinemate/src/module/templates/`)
· **PI-003** are the two `.patch` files applied, pending, or vestigial? (`git -C ~/cinepi-raw log --oneline | head`)
· **PI-005** is the meson `/path/to/...` fallback ever taken? (grep the build log)

---

## When you are done — commit the results, do not just report them

**Append your observations to `system-review/PI-VERIFICATION-QUEUE.md`, under the item they
belong to, and push.** Results that exist only as chat text are one context window from
gone; results in git can be read by any later session, which is how this whole review has
been carried across eleven of them.

```
git checkout claude/cinemate-system-review-kickoff-cilicc
# append under each PI-0NN heading, then:
git add system-review/ && git commit -m "pi: results from the hardware session" && git push
```

Append under the existing item rather than editing its procedure — the prediction has to
stay visible next to what actually happened, or the record loses its point.

**Then** post the same block in chat: all items, in order, four lines each. Do not summarise
or interpret; the raw observations are the deliverable. In particular, do not drop an
INCONCLUSIVE or a CONTRADICTED because it looks untidy — those two are why the session
exists.

Only `system-review/` should be touched. No commits to `src/`, and never to `dev`.
