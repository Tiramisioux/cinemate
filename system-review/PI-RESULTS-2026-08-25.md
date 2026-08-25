# PI results — 2026-08-25

Same live-Pi session as `PI-RESULTS-2026-08-24.md`'s later entries, continued the next day.
Covers three things the 2026-08-24 file did not: the combined-system verification that was
reported only in chat until now (Phase C), the fix round for F-283/F-284/F-285/F-286
(including hardware re-verification of three desk diagnoses written without hardware access),
and the venv-removal architecture decision's follow-up checks. Not a `PI-VERIFICATION-QUEUE.md`
item — that queue is closed (see the 2026-08-24 file). This is post-remediation verification.

## Phase C — merged `dev` running in both repos together, for the first time

Never committed before this file; existed only as chat output. cinemate `dev` (`fcf3c23`,
merged #130/#131/#132/#134) and cinepi-raw `dev` (`bc63598`, merged #59) pulled onto the Pi and
run together.

- cinepi-raw rebuilt clean at `bc63598`: 75/75 ninja targets, no new warnings vs the `ea96f2d`
  baseline built immediately before it in the same session (Phase A).
- `rec f 25` → exactly 25/25 DNGs, "✓ All frames accounted for.", clean stop.
- Web GUI: **port 5000**, not 8000 — 8000 is cinepi-raw's own MJPEG preview port, a distinct
  service. `curl` returned HTTP 200, page title "CineMate"; `/api/v1/status`'s `fps` matched
  `redis-cli GET fps` exactly. Worth recording explicitly: conflating the two ports is a
  plausible hour-long dead end for whoever debugs this next.
- `redis-cli MONITOR` showed continuous live traffic (`cp_stats` publishes, `SET`/`GET` pairs)
  throughout — the control bus is alive under the merged code, not just at idle.

### F-204 re-verification — the strongest single result of the whole review

PI-014 (2026-08-23) proved the defect with `StatusBroadcaster._on_change` raising: every
downstream surface froze silently and permanently on the first `PUBLISH` after the fault.
#130's fix wraps `Event.emit`'s subscriber loop in a per-subscriber `try/except`
(`redis_controller.py`). This session re-ran the identical fault injection against the
*merged* code to test the fix directly, not just the presence of the defect:

1. Same fault: `raise RuntimeError("PI-014 re-run fault injection")` as the first line of
   `StatusBroadcaster._on_change`, uncommitted on the live Pi checkout, `cinemate-autostart`
   restarted to pick it up.
2. `redis-cli SET iso 6400` + `PUBLISH cp_controls iso`, then a second `SET`/`PUBLISH` on
   `fps_user` (a key never touched in that process's life, to rule out a per-key effect —
   same method PI-014 used).
3. Checked the cache-backed `/api/v1/status` endpoint (not raw redis, which trivially reflects
   direct `SET`s regardless of the listener thread's health) before and after.

**Result:** `/api/v1/status` reflected both new values (`iso: 6400`, `fps_user: 23`)
correctly. The log showed the injected exception firing and being caught on *every*
subsequent parameter change — `ERROR: redis_controller Redis subscriber
StatusBroadcaster._on_change failed; continuing with the rest`, repeated dozens of times as
the process kept running normally. Before #130, the first such raise would have killed the
thread outright and produced exactly one traceback followed by silence forever. Reverted the
fault (uncommitted change discarded via `git checkout --`) and confirmed the log returned to
clean afterward.

PI-014 proved the defect was real and severe. This proves the fix closes it, on the exact
mechanism PI-014 used to demonstrate the failure — not a different, easier test.

## Fix round — F-283, F-284, F-285, F-286

Three of these were desk diagnoses (source-only, no hardware) handed off for verification.
**All three needed correction on hardware** — none was simply confirmed as written. See "Desk
diagnoses: confirmed or refuted" below for what specifically held and what didn't.

| finding | branch | PR | merged | what shipped |
|---|---|---|---|---|
| F-283 | `fix/f283-console-handoff-auth-hang` | [#135](https://github.com/Tiramisioux/cinemate/pull/135) | yes, `4f765c4` | `sudo -n` on both `systemctl start` calls in `cinemate-console-handoff.sh`. Closes the reported symptom (hang → `failed`) only — see below, a second race is documented open, not fixed |
| F-284 | `fix/f284-blkid-fresh-probe-empty-result` | [#136](https://github.com/Tiramisioux/cinemate/pull/136) | yes, `2c73b22` | `_blkid_value()` no longer treats an empty-but-successful command as final; falls through to the cache-backed query. Logging added to `_find_raw_device()`'s previously-silent `return []` |
| F-286 (core) | `fix/f286-dynres-explicit-request-guard` | [#137](https://github.com/Tiramisioux/cinemate/pull/137) | yes, `d35dfef` | Explicit, sustainable requests for the desired mode now honored directly, ahead of the `(area, fps_max)` tie-break. Also wired up the missing `dynamic_resolution_enabled` toggle (CLI + settings-editor catalogue, both copies) |
| F-286 (tie-break) | `feat/f286-tiebreak-bitdepth-priority` | #139 | not yet | Follow-up, implementing the design proposed in #137: on a genuine downgrade, bit depth now ranks above `fps_max` in the tie-break |
| F-285 | `fix/f285-pot-vs-explicit-set-race` | #140 | not yet | Three changes together: (a) `AnalogControls._dispatch()` now takes `CommandExecutor._dispatch_lock`; (b) a movement gate (`_has_moved`/`_record_dispatch`, `MOVEMENT_THRESHOLD_RAW=3`) requires genuine ADC movement since the last dispatch, not just a mapped-value difference from a stale cache; (c) `CommandExecutor._confirm_or_ok()` reads back what a command actually set and reports a mismatch instead of a blind `ok` |

Each PR's own description has the full commit message and test plan; not duplicated here.
Regression-test counts: F-283 +1 file (2 tests), F-284 +2 tests in an existing file, F-286
core +2 tests / tie-break follow-up +1 test, F-285 +1 new file (8 tests) + 3 tests in an
existing file. All hardware-verified in addition to the off-hardware suite (below).

### F-285 — hardware verification (Grove Base HAT, ISO pot, channel 0)

The Grove Base HAT is physically present on this unit but disabled by default in
`settings.jsonc` (`input_peripherals.pots[iso].channel = "None"`) — enabled for this session,
restored afterward.

- **Starve case** (pot actively turning): 5 rapid explicit `set iso 6400` calls all correctly
  logged `set iso 6400 did not stick; live value is '3200'` instead of a bare `ok`. (6400 is
  not a valid step in this session's `arrays.iso.steps` — `set_iso`'s own range clamp took it
  to 3200, the max step. This incidentally also confirms (c) surfaces clamp mismatches, not
  only pot contention; the pot-contention path specifically was confirmed by cross-checking
  against the pot's own concurrently-changing value in the same log window.)
- **Isolated case** (pot stationary — confirmed via 35+ seconds with no `ISO changed` log
  line): `set iso 800` (a valid step) checked three times over several seconds, held at `800`
  throughout. No discrepancy warning, no silent reversion. This is the core fix for the
  reported symptom.

### Desk diagnoses: confirmed or refuted

Three findings were diagnosed from source with no hardware and handed off for verification.
Recorded in the same style as the PI predictions — a diagnosis that needed correction is a
good ledger entry, not a bad one.

**F-283 — CONFIRMED at the root, but the diagnosis of the fix was incomplete.**
The desk diagnosis (`cinemate-console-handoff.sh:44` missing `--no-block`, deadlocking against
`Conflicts=`/`Before=` during `ExecStopPost`) was **wrong about the mechanism**. `bash -x`
confirmed the script hangs at that exact line, but not on a `--no-block` deadlock — on an
interactive PolicyKit prompt (`AUTHENTICATING FOR org.freedesktop.systemd1.manage-units`) that
`ExecStopPost`'s non-interactive context can never answer. `sudo -n` (not `--no-block`) is
what fixes it, and `--no-block` was already present on the working `plymouth-start` call one
branch up in the same script for an unrelated reason. **The second route explicitly asked
about — `Job ... was cancelled` / `Requested transaction contradicts existing jobs` in
`journalctl` — did appear**, but from a *different* source than either original guess: a
second, independent call to `systemctl start getty@tty1` inside `main.py`'s own
`restore_local_console_prompt()`, racing the same `Conflicts=getty@tty1.service` from a
different code path entirely. Four escalating mitigations were tried against this second race
(`--job-mode=ignore-dependencies`, a deferred timer with re-check, a debounced timer, and
dropping `Conflicts=` entirely) — all four failed on hardware; the last one made things worse
(`TTYVHangup=yes` then SIGHUPs the unit's own `ExecStartPre` if a getty is alive on tty1,
breaking a fresh start, not just a restart). **Correcting the finding's evidence line**: the
symptom is real and the hang/`failed` fix (`sudo -n`) is solid and hardware-verified across
many restarts — but a second, narrower, unfixed race remains (unit lands `inactive` instead of
`active` after some restarts; self-recovers, never hangs, never lands `failed`). See #135's
description for the full list of what was tried and rejected.

**F-284 — CONFIRMED, and the mechanism question is answered: mechanism (a), not (b), not
both.** The diagnosis correctly located the defect in `_find_raw_device()`
(`ssd_monitor.py:621`), not `mount_drive()` — **the finding's evidence line pointing at
`mount_drive()` is now corrected** to point at `_blkid_value()`
(`ssd_monitor.py:555`) instead. Of the two candidate mechanisms named (stale cache, or the
`timeout=1.0` firing and being swallowed): **stale/short-circuited result, not a timeout.**
Diagnostic instrumentation timed every `blkid` call across 10 reproduced failures — every one
completed in 3-18ms, nowhere near the 1.0s cutoff. The actual mechanism: `_blkid_value`'s
`fresh=True` path tries `blkid -p` (raises `PermissionDenied` as unprivileged `pi`, correctly
falls through) then `blkid -c /dev/null` (needs the same raw access it doesn't have either,
but on this blkid version returns **empty output with exit 0** instead of raising) — and the
old code treated any successful exit as final, never reaching the cache-backed query one step
further that actually has the answer (confirmed by hand: `blkid -s LABEL -o value
/dev/nvme0n1` returns `RAW` instantly, matching stage 1's own cache-based enumeration). This
also depended on a detail neither original diagnosis had: **this NVMe volume has no partition
table** — `LABEL=RAW` lives directly on `/dev/nvme0n1`, no `/dev/nvme0n1p1` exists — which is
why the whole-disk node's raw probe hits the unprivileged-permission wall in the first place.

**F-286 — CONFIRMED as written, including the "worse than the finding says" framing**, and one
correction: **the `IMX477_MODES` fixture supplied in the handoff was reconstructed from
PI-016's notes, not measured — replaced with the real table**, pulled directly from
`cinepi-raw --list-cameras` on this hardware:

```
SRGGB10_CSI2P: 1332x990 120.50fps · 2028x1080 74.74fps · 2028x1520 53.77fps ·
               4056x2160 19.58fps · 4056x3040 14.00fps
SRGGB12_CSI2P: 1332x990 101.68fps · 2028x1080 62.81fps · 2028x1520 45.19fps ·
               4056x2160 16.39fps · 4056x3040 11.72fps
```

(8-bit modes exist on the sensor but are filtered out by `settings.jsonc`'s `bit_depths`
whitelist before cinemate's table is built — not part of the live collision.) The fps_max
values at 4056x3040 (14.00 / 11.72) match the numbers PI-016 recorded exactly, so the
reconstruction was accurate; replacing it with the measured table was precautionary, not a
correction of substance. Both the core fix (#137) and the tie-break follow-up (#139) were then
verified against this real fixture, and #137's fix was additionally verified with a real
recording: `set fps free 1`, `set fps 10`, `set resolution 0` through the normal CLI surface
(mode 0 = `4056:3040:12:U` in this process's live numbering — confirmed by cycling
`set resolution 0..9` and reading back `resolution_target_width/height/bit_depth`, since
`SensorDetect` renumbers per-process per prior sessions' notes). Recorded a take and parsed
the DNG's own TIFF tags directly, not the GUI/redis display: `ImageWidth=4056`,
`ImageLength=3040`, `BitsPerSample=12`. Real 12-bit capture at full resolution through the
normal command surface — exactly what PI-016 could not do without patching source.

## The venv-removal decision — architecture, not remediation

**Decided by the operator on reasoning, not measurement — record this as a decision, not a
fixed finding, so a later session does not read it as remediation.** Cinemate's Python
packages now install to the system interpreter (`pip install --user --break-system-packages`)
instead of a dedicated virtualenv, matching the pattern `cinemate-recovery.service` already
used deliberately for the same reason. `feature/no-venv-install` (F-279 `sudo -v` hang,
F-280 raspi-firmware 404, F-281 settings.jsonc comment destruction, F-282 relative tuning
path — all four fixed in the same branch) merged as [#138](https://github.com/Tiramisioux/cinemate/pull/138)
(`6a15ed8`). `#133` (B6 dependencies) — the last remediation PR — rebased to match the new
install mechanism (`"${pip_cmd[@]}" -r "$req" -r "$req_hw"` in place of `$VENV_DIR/bin/pip`)
and merged as [#133](https://github.com/Tiramisioux/cinemate/pull/133) (`7e7515f`); its
requirements-file content and `versions.env` pairing manifest were unchanged — PI-004 already
vindicated them.

Two checks run afterward, **for the record, not for the decision** — neither gates anything;
the operator made this call with the overlap risk already on the table.

### 3a. apt/pip overlap

`--break-system-packages` is not itself the risk; overlap is — a package pip puts in
`~/.local` that apt also provides in `/usr/lib/python3/dist-packages`, where `pi` gets the pip
copy (earlier in `sys.path`, see 3b) while other apt-managed consumers get the apt one, and an
`apt upgrade` can move one without the other. PI-012 already proved this class of overlap is
real (`python3-lgpio` arrives via apt as a `python3-gpiozero` dependency regardless of the
installer's own flag).

Intersected the full `requirements.txt` + `requirements-hardware.txt` package list against
`apt list --installed 'python3-*'` on this Pi. **Not empty: 4 packages overlap** —
`gpiozero`, `lgpio`, `pyudev`, `smbus2`.

Version check: `pyudev` (apt `0.24.0-1`, resolves to `0.24.0`) and `smbus2` (apt `0.4.2-1`,
resolves to `0.4.2`) currently match. `gpiozero`/`lgpio` have no importable `__version__` to
compare directly, but on **this specific Pi**, `pip list --user --break-system-packages` shows
none of the four packages actually installed to `~/.local` at all — `import gpiozero`
currently resolves to `/usr/lib/python3/dist-packages` (apt) and `import lgpio` to
`/usr/local/lib/python3.11/dist-packages` (the C-library egg from `install_lgpio_backend()`,
not pip). **This machine's install predates the no-venv installer path** (it was updated by
pulling merged `dev` directly, not by re-running `cinemate-install.sh`), so the apt/pip split
described above is not currently *active* on this hardware — it is a property of what a
genuinely fresh install through the new installer would produce, not something observed here.
Nothing in the list looks alarming; recorded as the risk register the operator asked for.

### 3b. Recovery console isolation (F-221)

```
sudo python3 -c "import sys; print('\n'.join(sys.path))"
```
```
/usr/lib/python311.zip
/usr/lib/python3.11
/usr/lib/python3.11/lib-dynload
/usr/local/lib/python3.11/dist-packages
/usr/local/lib/python3.11/dist-packages/rgpio-0.2.2.0-py3.11.egg
/usr/local/lib/python3.11/dist-packages/lgpio-0.2.2.0-py3.11-linux-aarch64.egg
/usr/lib/python3/dist-packages
```
```
python3 -c "import sys; print('\n'.join(sys.path))"     # as pi
```
```
/usr/lib/python311.zip
/usr/lib/python3.11
/usr/lib/python3.11/lib-dynload
/home/pi/.local/lib/python3.11/site-packages
/usr/local/lib/python3.11/dist-packages
/usr/local/lib/python3.11/dist-packages/rgpio-0.2.2.0-py3.11.egg
/usr/local/lib/python3.11/dist-packages/lgpio-0.2.2.0-py3.11-linux-aarch64.egg
/usr/lib/python3/dist-packages
```

**Confirmed as expected.** Root's `sys.path` contains nothing under `/home/pi` — the one
difference between the two is `pi`'s own `/home/pi/.local/lib/python3.11/site-packages`. The
isolation `cinemate-recovery.service` (root) needs from `cinemate-autostart.service` (pi) is
preserved: directory separation now does the job the venv used to do. **F-221 can be
dispositioned `strength` with evidence, not assumption.**
