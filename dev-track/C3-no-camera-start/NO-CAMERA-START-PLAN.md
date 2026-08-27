# C3 — Start without a camera: implementation spec

Written 2026-08-26 against `dev` (cinemate `13ab0225` era), from a source-reading
investigation in the Fable thread. Cinemate repo only — cinepi-raw is unchanged (it remains
the `--list-cameras` probe binary; its zero-camera output shape does not matter, see
"Unknowns"). Ledger entry: [`PLAN.md`](PLAN.md) beside this file.

Line-number policy follows the handbook: files and functions are named, coordinates are
not.

## Verdict

Small, one repo, one branch. Two blockers stop a no-camera start today; everything behind
them already degrades. The GUI half is cheap because the no-camera state already lands in
Redis (`cameras = []`) and the web GUI consumes the HDMI GUI's `populate_values()` dict
verbatim — one shared field reaches both surfaces. The genuinely subtle part is not
starting — it is **not corrupting stored operator state while degraded** (the fps-clamp
chain below) and **not letting the GUI thread die on a fresh Redis** (it has no
per-iteration exception handling).

## Confirmed source facts

All confirmed by direct reading on `dev` 2026-08-26.

### The systemd path never reaches main.py

- `services/cinemate-autostart/cinemate-autostart.service` runs
  `ExecStartPre=/usr/local/bin/camera-ready.sh` before `main.py`.
- `services/cinemate-autostart/camera-ready.sh`: `MAX_ATTEMPTS=30`, `RETRY_INTERVAL=1`,
  greps `cinepi-raw --list-cameras` output for `^\s*[0-9]+\s*:\s*imx`, exits 1 on timeout.
  A failed `ExecStartPre` fails the unit — main.py never runs. The unit has no `Restart=`;
  `ExecStopPost` hands the console to the failure-display and console-handoff scripts.
- Deployment: the root `Makefile` `install` target copies the unit to
  `/etc/systemd/system/` and `camera-ready.sh` to `/usr/local/bin/`;
  `cinemate-install.sh` drives it via `make -C <repo> install`. Existing Pis therefore
  pick up a unit change with `sudo make install` + `daemon-reload`, no full reinstall.

### The manual path gets far, then dies in one constructor

- `SensorDetect` (`src/module/sensor_detect.py`) is already graceful: zero cameras →
  `detect_camera_model()` logs a warning, `camera_model = None`, `res_modes = {}`. Both
  the empty-output and no-cameras-parsed routes end in the same state.
- `CinePiManager.start_all()` (`src/module/cinepi_multi.py`): `discover_cameras()` retries
  for 10 s, then start_all writes `cameras = []` to Redis (**before** the abort — this is
  the state signal the GUI rides) and returns without launching cinepi-raw.
- `CinePiController.__init__` (`src/module/cinepi_controller.py`) then crashes. In boot
  order:

| Read | Key(s) | Fails when |
|---|---|---|
| `self.fps = int(round(float(get_value(FPS_LAST))))` | `fps_last` | fresh Redis |
| `self.current_fps = float(get_value(FPS_USER))` | `fps_user` | fresh Redis |
| `self.fps_saved = float(get_value(FPS))` | `fps` | fresh Redis |
| `self.exposure_time_s = float(get_value(SHUTTER_A)) / 360 * (1/self.fps)` | `shutter_a` | fresh Redis |
| `_recompute_file_size()` → `self.sensor_detect.res_modes[self.sensor_mode]` | — | **every no-camera boot** (KeyError on `{}`) |

  The fresh-Redis rows exist because nothing seeds these keys: `RedisController` primes
  its cache from whatever Redis holds, `initialize_system()`/`run_application()` seed
  other keys but not fps/shutter, and `start_all()` writes `fps` only if already present.
  On a used camera the keys exist because cinepi-raw and past sessions wrote them and
  Redis persists. `_get_startup_sensor_mode()` already falls back safely (`next(iter(...),
  0)`) — it hands mode `0` to `_recompute_file_size()`, which is where the empty dict
  finally throws.
- `main()` catches the exception, reports "Cinemate crashed during startup"
  (`report_startup_failure()` → tty1 block / persisted failure file) and exits 1.

### The fps-clamp corruption chain (silent, worse than the crash)

With no camera, `_refresh_fps_max()` → `_sensor_readout_fps_max()` hits `int(None)`,
catches, returns 1 → `fps_max = 1` in Redis. The init-time `set_fps(self.fps)` then snaps
to `_fps_steps_capped_at_max()`'s guaranteed-non-empty list — i.e. clamps `fps` and
`fps_user` to **1** and writes both to Redis. On exit, `cleanup()` (in `main.py`) persists
`fps_last = get_value(fps)` = 1. Net effect: one no-camera boot rewrites the operator's
stored frame rate to 1 fps for the next with-camera boot. The fix must break this chain,
not just survive construction.

### Everything after the controller survives

Traced constructor-by-constructor: `StoragePreroll._resolve_sensor_fps_max()` returns
None when no camera name; `RedisListener.__init__` guards its casts (`or 0` / default
args); `Mediator` only subscribes; the web app's connect handler tolerates
`camera_model = None`. Run-loop behaviour under the degraded state is **probable**, not
hardware-verified — G1 exists to catch surprises.

### The GUI is already halfway there — and has one fatal gap

- `SimpleGUI._get_camera_list()` reads the `cameras` Redis key (`or "[]"`);
  `_update_cam_section_labels()` already falls back to a generic `CAM` label and no right
  column on an empty list. `populate_values()` leaves the `sensor` field `""`.
- Precedents for the indicator exist: the `"NO DISK"` text fallback and the DROP/SYNC
  `_draw_status_box` warning badges.
- **The gap:** `populate_values()` itself does
  `round(float(get_value(FPS_USER)))` unguarded, and `SimpleGUI.run()` has **no
  per-iteration exception handling** — a throw exits the draw loop through `finally` and
  the GUI thread is dead for the rest of the session. The web connect handler
  (`src/module/app/main/events.py`) calls `populate_values()` directly, so the same throw
  breaks web connects. On a fresh Redis with the init `set_fps()` skipped (see Design),
  nothing else writes `fps_user` — this read must be guarded and/or the key seeded.
- The web template (`src/module/app/templates/template.html`) renders `V.sensor` directly
  into the CAM section boxes, so a `NO CAM` sensor value reaches the web GUI with zero
  template work; a proper badge needs a small template addition keyed on
  `camera_missing`.

### Recovery machinery that already exists

- `restart cinemate` (CLI/serial/web `/api/v1/cmd`) → `restart_cinemate()` →
  `os.execl` full re-exec → fresh `SensorDetect` detection → normal operation. This is
  the v1 recovery path.
- `restart camera` → `start_all()` re-discovers, **but is not sufficient**: it sets
  `sensor_detect.camera_model` and calls `load_sensor_resolutions()`, yet the
  `sensor_resolutions` cache is empty from the no-camera boot (only
  `detect_camera_model()` fills it), so the mode table stays empty and controller state
  (`fps_max`, step tables) stays wrong. Hot-plug support means re-running detection inside
  `start_all()` and refreshing controller state — out of v1, recorded below.

## Unknowns, stated

- What `cinepi-raw --list-cameras` prints with zero cameras (empty vs. a "no cameras"
  line). Does not matter: both routes end in `camera_model = None` / `cams == []`. G0
  records the actual output for the log.
- Whether any run loop (RedisListener stats path, StoragePreroll auto pre-roll on a media
  mount, status broadcaster) misbehaves over minutes in the degraded state. G1 soaks
  this.
- Boot-to-GUI time with the fix. Predicted ≈ 45 s on a systemd boot (30 s advisory gate +
  two quick SensorDetect probes + 10 s `discover_cameras()`); measured at G1.

## Design

### 1. Advisory gate (service, one line)

`ExecStartPre=-/usr/local/bin/camera-ready.sh` — the `-` prefix makes failure non-fatal.
The script's wait-for-slow-sensor behaviour and its journal logging are preserved
unchanged; its exit 1 stops vetoing startup.

Rejected: deleting the gate (regresses the black-screen-on-boot fix it exists for);
teaching the gate to exit 0 on "definitely absent" (cannot distinguish absent from slow —
the 30 s wait *is* the distinction); shortening `MAX_ATTEMPTS` (held open for plan review,
default stays 30).

### 2. No-camera-safe controller init (`cinepi_controller.py`)

- The four unguarded reads become guarded with defaults, matching the existing idiom
  elsewhere (`float(get_value("fps") or 0)` in `redis_listener.py`): fps-family keys
  default **24**, `shutter_a` defaults **180**.
- **Seed-if-absent, never overwrite:** when a key is missing from Redis, write the default
  back so downstream readers (`populate_values()`, web connect) see a value; when the key
  exists, leave it alone. A warm Redis keeps the operator's stored values untouched.
- `_recompute_file_size()`: `res_modes.get(self.sensor_mode)` + early return on None —
  mirroring the guard it already has for missing width/height.
- **Skip the init-time `set_fps(self.fps)` when `sensor_detect.camera_model is None`.**
  This closes the fps-clamp chain: `fps`/`fps_user` are never rewritten to 1, so
  `cleanup()`'s `fps_last` persist stays honest. Log one line saying why it was skipped.
- Do not special-case `fps_max`: it may sit at 1 in Redis while degraded — nothing reads
  it destructively once `set_fps` is skipped, and the next with-camera boot recomputes it.

### 3. Boot-path behaviour while degraded (`main.py`)

- Skip the post-Plymouth `restart_camera(preview_enabled=True)` handoff restart when the
  `cameras` key is `[]` — there is no preview to rebind above the GUI, and the restart
  costs another 10 s discovery timeout.
- Gate **auto** storage pre-roll on a camera being present (one condition where
  `StoragePreroll` decides to run): with no recorder process, a pre-roll take is a
  pointless stress-write cycle that records nothing. Manual pre-roll commands stay
  available and simply log what they cannot do.
- No other boot-path changes: hotspot, web app, settings editor, recovery console, serial,
  GPIO, status broadcast all start as normal — keeping those alive on a camera-less body
  is the point of the feature.

### 4. The indicator (`simple_gui.py` + `template.html`)

- `populate_values()`: when `_get_camera_list()` is empty, set
  `values["camera_missing"] = True` and `values["sensor"] = "NO CAM"`. Guard its
  `fps_user` read (`or 24`) — with `run()` having no per-iteration catch, this read must
  never throw regardless of seeding.
- HDMI: a `_draw_status_box` badge in the CAM section, same mechanism as DROP/SYNC but a
  distinct colour (this is "unusable", not "losing frames" — do not reuse the DROP
  colour). Optional, held open for review: a centred two-line message in the empty
  preview area ("NO CAMERA DETECTED / connect camera, then: restart cinemate") — the
  preview area is plain background with no cinepi-raw running, so the space is free.
- Web: the `NO CAM` sensor text arrives for free via `V.sensor`; add a badge element
  keyed on `V.camera_missing` with the recovery hint text. Template JS is ES5 — match it.
- Settings editor and recovery console: untouched. They edit files on disk and are the
  main beneficiaries of the feature (reachable for `config.txt` / dtoverlay fixes while
  no camera is detected).

### 5. Docs

- Troubleshooting page: what a no-camera boot looks like now (GUI with NO CAM badge, web
  reachable), the recovery sequence (connect camera → `restart cinemate`), and the
  reminder that `camera-ready.sh` still waits 30 s so a slow sensor is not misread as
  absent.
- Installation page: note that the unit change reaches existing installs via
  `sudo make install` + `sudo systemctl daemon-reload`.

## The degraded-state contract

What the operator gets on a camera-less boot, stated once so tests and docs agree:

| Works | Does not work |
|---|---|
| HDMI GUI with NO CAM badge; web GUI with badge + hint | Preview (no cinepi-raw process) |
| Hotspot, web API, settings editor, recovery console | Recording (`rec` logs and no-ops — no recorder exists) |
| CLI / serial / GPIO dispatch (commands log and degrade, dispatcher survives) | Mode table / resolution controls (empty; commands log why) |
| Storage mount/unmount, format, battery, dmesg monitors | Auto storage pre-roll (gated off) |
| `restart cinemate` recovery | `restart camera` hot-plug recovery (out of v1) |

## Commits

| commit | change |
|---|---|
| C3.1 | `cinepi_controller.py`: guarded reads + seed-if-absent defaults; `_recompute_file_size()` guard; skip init `set_fps()` when no camera |
| C3.2 | `main.py`: skip post-Plymouth `restart_camera()` when `cameras == []`; gate auto pre-roll on camera present |
| C3.3 | `simple_gui.py` + `template.html`: `camera_missing` + `NO CAM` in the shared dict; `fps_user` read guard; HDMI badge; web badge + hint |
| C3.4 | `cinemate-autostart.service`: `ExecStartPre=-`; verify the `make install` path carries it |
| C3.5 | Docs: troubleshooting + installation |

Each commit lands with its tests. C3.1 and C3.3 are the load-bearing ones; C3.2 and C3.4
are one-condition / one-character changes; C3.5 is prose.

## Verification

### Desk (implementing session, no Pi)

New tests, all Pi-free, following the existing `_test/` pattern
(`test_cinepi_controller_startup_sensor_mode.py`: `CinePiController.__new__` + `FakeRedis`
+ `FakeSensorDetect`, per-method):

- `_recompute_file_size()` with `res_modes == {}` returns without touching Redis.
- The guarded init reads: empty FakeRedis → defaults land via seed-if-absent; primed
  FakeRedis → stored values untouched (the anti-corruption property, asserted explicitly:
  no write to `fps`/`fps_user` when `camera_model is None`).
- `populate_values()` with `cameras = "[]"` sets `camera_missing` and `NO CAM`, and does
  not throw with `fps_user` absent.
- Audit grep on the boot path (`cinepi_controller.py`, `simple_gui.py`, `main.py`,
  `storage_preroll.py`) for remaining unguarded `float(get_value(` / `int(get_value(` —
  fix or justify each hit in the PR text.
- Full existing `_test/` suite green.

### Hardware gates (operator, dev Pi, camera cable unplugged)

Method per `cinemate-handbook/working/hardware-session.md`: prediction written before each
gate, verdict after; outcomes appended to `cinemate-handbook/lessons/hardware-log.md`.

| Gate | Setup | Prediction |
|---|---|---|
| G0 | Unpatched `dev`, no camera, systemd boot; then manual `main.py` from SSH | Service: `camera-ready.sh` exits 1 after 30 s, main.py never runs, failure/console handoff takes tty1. Manual: "Cinemate crashed during startup", KeyError from `_recompute_file_size` (warm Redis). Record the actual `--list-cameras` zero-camera output |
| G1 | Patched build, warm Redis, no camera, systemd boot; soak ≥ 10 min | GUI up ≈ 45 s with NO CAM badge; web GUI + settings editor reachable over hotspot; no thread deaths in the log; stored `fps` in Redis unchanged from pre-test value |
| G2 | Patched build, `redis-cli FLUSHALL`, no camera, systemd boot | Same as G1; seeded defaults visible (fps 24); exercises the fresh-Redis read sites |
| G3 | From G1/G2 state: plug camera in, `restart cinemate` from the web GUI | Full normal operation after restart; fps is the stored value (G1) / 24 (G2), **not 1** |
| G4 | Regression: camera attached, normal systemd boot | Behaviour identical to pre-C3 `dev`, including the gate's slow-sensor wait |

G0 runs **first** — it validates the desk analysis before any fix is trusted, and its
failure-mode observations are themselves a hardware-log entry.

## Out of v1 — recorded so they are not re-litigated

- **Hot-plug re-detection** (`restart camera` finding a newly attached sensor without a
  process restart): needs `detect_camera_model()` re-run inside `start_all()` when the
  mode cache is empty, plus controller `fps_max`/step-table refresh. Clean follow-up step
  if wanted; v1 is message + `restart cinemate`.
- **Background re-probe loop** (poll `--list-cameras` while degraded, auto-restart on
  detection): rejected — a heavyweight subprocess probe on a timer, for a rare state with
  a working manual recovery.
- **Shortening the no-camera boot further**: the residual 10 s `discover_cameras()`
  timeout could skip retries when SensorDetect already saw nothing, but that couples the
  two discovery paths; and the gate's 30 s could become configurable. Both cosmetic;
  revisit only if the measured G1 time annoys in practice.
- **A tappable restart button next to the web badge**: the hint text names the command;
  the settings editor already exposes restart actions. Add only if the badge text proves
  insufficient.

## Confidence

- **Confirmed** (direct source reading): both blockers; the crash table; the fps-clamp
  chain; `cameras = []` written before the abort; `SimpleGUI.run()`'s lack of an
  exception catch; the web template's `V.sensor` consumption; `restart camera`'s empty
  mode cache; the Makefile deploy path.
- **Probable** (traced but not executed): the degraded run loops staying healthy over
  time; the ≈ 45 s boot estimate; `rec` and mode commands degrading to logs rather than
  killing dispatcher threads.
- **Unknown**: the zero-camera `--list-cameras` output shape (irrelevant to the code
  path, recorded at G0); long-soak behaviour (G1).
