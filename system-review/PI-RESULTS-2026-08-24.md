# PI results — 2026-08-24

All 16 items in `PI-VERIFICATION-QUEUE.md` are now `done`, across two sessions
(2026-08-23 hardware session, 2026-08-24 blank-card session). Full ran/observed/verdict
detail lives under each `## PI-0NN` heading there — this file is the summary and the
merge/finding roll-up, not a replacement for it.

## Summary table

| PI | verdict | findings it moves | what changes |
|---|---|---|---|
| PI-001 | CONFIRMED | F-001 | Dead templates are deployed to every camera, not just sitting in the repo — B2's deletion has real effect, not just repo hygiene |
| PI-002 | CONFIRMED | F-006, F-222, F-272, F-278 | 381 passed + 241 subtests on real hardware too, zero skips — matches the off-hardware baseline exactly. B4.6 can gate at zero |
| PI-003 | CONFIRMED (vestigial) | census §11 | Both cinepi-raw patch files are stale exports of an already-landed commit — independently corroborates B2.3's own reasoning |
| PI-004 | CONFIRMED | F-003, F-186, F-276, F-279, F-280 | Clean install works end-to-end, after fixing two real installer bugs (F-279, F-280). flask and pyserial both confirmed transitive-only |
| PI-005 | CONTRADICTED | census §11 | pkg-config resolves cleanly; the `/path/to/...` meson fallback is dead defensive code, not a live landmine |
| PI-006 | CONFIRMED / CONTRADICTED | F-016 | VU meter works end to end (confirmed on the physical display); DEL-mid-take degradation does NOT reproduce — audio_vu is republished too fast to observe missing |
| PI-007 | CONFIRMED | F-025, F-268, F-269, F-285 (new) | Not an occasional race: a live pot 100% starves explicit CLI `set iso` commands for as long as it's connected and moving. F-285 elevates severity with hardware proof |
| PI-008 | CONTRADICTED / CONFIRMED | F-027 | "Most never appear" does not hold — all 11 keys showed up. Two groups: an undocumented cinepi-raw launch-config contract, and live per-frame phase-lock telemetry with zero reader |
| PI-009 | CONFIRMED | ADR-001 constraint 2 | GUI (fbcon) holds a genuine DRM plane; cinepi-raw's own preview held none under the tested conditions — narrower and more concrete than the review's "two interfaces racing" framing |
| PI-010 | CONTRADICTED | F-253 | DNG timecode frame field wraps at base 24 (Python's convention), not the predicted base 25 (C++ half-up), for a 24.5fps take |
| PI-011 | CONFIRMED | F-259 | Cold start clamps analogue gain to the sensor's absolute maximum (22.26x) while writing a plausible-looking `iso: 400` to redis — ~5.6x silent overexposure, no error anywhere. Real, but likely unreachable via normal cinemate-autostart operation since Python re-seeds iso first |
| PI-012 | CONTRADICTED | F-182 | `python3-lgpio` ships via apt as a `python3-gpiozero` dependency, independent of `INSTALL_ALT_GPIO_BACKEND` — the predicted crash does not happen |
| PI-013 | CONFIRMED | F-172 | Log-queue growth is ~70x faster while recording than idle (60 KB/s vs 0.85 KB/s RSS proxy) — matches the prediction directly |
| PI-014 | CONFIRMED | F-204 | The worst defect in the review, confirmed decisively: one raising subscriber freezes every downstream surface silently and permanently |
| PI-015 | CONFIRMED / CONTRADICTED | F-207 | Headless path genuinely works (411 events over a real physical HDMI detach+reattach, zero gaps); measured cadence ~7.5Hz not the predicted ~12fps; no camera restart observed on reattach either |
| PI-016 | CONTRADICTED | ADR-001 headroom argument | At the sensor's true peak (4056x3040 12-bit, forced via a temporary bypass of `dynamic_resolution_enabled`), available memory never dropped below ~2970MB of 4048MB total. The ~300MB-free-at-peak argument does not hold on this (4GB, not 2GB) board |

## Merge verdict

- **cinemate #130 (B3 · correctness)** — **SAFE.** PI-014 and PI-013 both independently confirm, on real hardware, the severity of the two defects this PR's headline fixes address (F-204, F-172). Nothing found this session contradicts its approach to any of the seven fixes.
- **cinemate #131 (B4 · style + CI)** — **SAFE.** PI-002 confirms the test suite it wants to gate in CI passes cleanly on real hardware (381 passed + 241 subtests, zero skips), matching the off-hardware baseline the PR was built against.
- **cinemate #132 (B2 · dead code)** — **SAFE.** PI-001 confirms the dead HTML templates are genuinely dead but deployed (F-001) — the deletion has real effect. Nothing in this session's testing exercised any other symbol this PR removes.
- **cinemate #133 (B6 · dependencies)** — **NEEDS-CHANGE.** Inspected the branch directly: it still installs via `$VENV_DIR/bin/pip install -r requirements.txt -r requirements-hardware.txt`, which architecturally conflicts with `feature/no-venv-install` (this session, separate from the PI queue — the operator asked for the venv to be dropped entirely; Cinemate's Python packages now install to the system interpreter via `pip install --user --break-system-packages`). PI-004 confirms the underlying goal — tracking flask/pyserial as transitive-only, a portable/hardware requirements split — is sound and worth keeping. The install mechanism needs reconciling with whichever venv decision survives; the requirements-file *content* does not need rework.
- **cinepi-raw #59 (B2 · dead sources)** — **SAFE.** PI-003 independently reached the exact conclusion this PR already implements — `add-tc.patch` is a byte-identical wrapper duplicate of `add-redis-timecode.patch`, both vestigial exports of an already-landed commit (`471bba0`).

## New findings

Appended to `FINDINGS.md`, continuing from F-278:

- **F-279** (high) — `sudo -v` hangs forever on stock Raspberry Pi OS sudoers. Fixed on `feature/no-venv-install`.
- **F-280** (high) — pinned `raspi-firmware` download 404s (wrong apt pool). Fixed.
- **F-281** (high) — `configure_settings_json()` destroys all 71 settings.jsonc comments on every install, not just via the web editor (F-271's sibling, different code path). Fixed.
- **F-282** (low) — `tuning_file_override.path` was relative and CWD-dependent. Fixed.
- **F-283** (medium) — `systemctl restart cinemate-autostart` reliably hangs on `ExecStopPost=cinemate-console-handoff.sh`, lands in `failed`. Reproduced 5+ times, not yet fixed.
- **F-284** (medium) — `unmount`/`mount` CLI pair unreliable for the NVMe RAW volume; `mount_drive()` misses what `blkid` finds instantly. Not yet fixed.
- **F-285** (high) — hardware proof that F-268/269's pot-vs-CLI race is a 100% starve, not an occasional collision: 20/20 explicit `set iso` calls lost to a live pot.
- **F-286** (medium) — `choose_resolution()`'s tie-break can never select a higher-bit-depth mode at a sensor's max resolution when a same-resolution higher-fps-max lower-bit-depth mode exists; `dynamic_resolution_enabled` has no external toggle.

F-279 through F-282 are already fixed on `feature/no-venv-install` (3 commits: `8db800a` venv removal + the `sudo -v` fix, `c95da81` the raspi-firmware pool fix, `8e9301a` the settings.jsonc comment fix + tuning-path fix). F-283 through F-286 are open, unfixed observations.

**Also not in the queue, not a `FINDINGS.md` entry:** at the operator's explicit request, mid-session, Cinemate's Python packages no longer install into a dedicated virtualenv — they install to the system interpreter (`pip install --user --break-system-packages`), matching the pattern `cinemate-recovery.service` already used deliberately. This is an architecture change, not a discovered defect, but it's why #133 above is NEEDS-CHANGE and why PI-004/PI-012's results are captured against a build that differs from the original venv-based installer.

## Not run

Every one of the 16 queued items was attempted and is `done`. Two narrower sub-cases inside
otherwise-done items were not reached — flagging them as not attempted rather than folding
them into the item's overall verdict:

- **PI-009's `--same-hdmi` toggle comparison** (on vs off, counting the plane cost of the
  clone path) — not attempted. Would need a cinepi-raw restart with the flag set, deferred
  given the restart-hang (F-283) risk at the time.
- **PI-015 step 3** (stopping the `SimpleGUI` thread specifically, distinct from the physical
  HDMI cable pull that was tested) — not attempted; a different, more invasive test than what
  the operator was asked to do physically.
- **PI-004/PI-012's originally-specified "two separate blank-card installs"** — ran as one
  blank-card install (PI-004) plus a targeted in-place reproduction of what
  `INSTALL_ALT_GPIO_BACKEND=0` skips (PI-012), not a second full re-flash. Noted as a
  deviation in both items' result blocks; the specific claims each item asks about were
  still directly tested.
