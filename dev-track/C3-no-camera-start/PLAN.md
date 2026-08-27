# C3 · Start without a camera, and say so in the GUI

Cinemate boots to a working GUI when no camera is attached: HDMI GUI and web GUI come up
with a visible **NO CAM** indicator, hotspot / web API / settings editor stay reachable for
troubleshooting, and plugging a camera in plus `restart cinemate` returns to normal
operation. Today the same situation produces no GUI at all — on a systemd boot the service
never starts; on a manual start Cinemate crashes during startup.

**Full implementation spec: [`NO-CAMERA-START-PLAN.md`](NO-CAMERA-START-PLAN.md) in this
directory**, written against `dev` 2026-08-26 (cinemate `13ab0225` era; cinemate repo only,
no cinepi-raw changes).

The finding that shapes the step: **only two things block a no-camera start, and everything
behind them already degrades gracefully.** `SensorDetect` handles zero cameras cleanly
(`camera_model = None`, empty mode table), `CinePiManager.start_all()` aborts without
launching cinepi-raw and writes `cameras = []` to Redis — the no-camera state signal
already exists — and every post-controller component (`StoragePreroll`, `RedisListener`,
`SimpleGUI`, web app, `Mediator`) tolerates the absence. The blockers:

| Blocker | Where |
|---|---|
| systemd gate waits 30 s for an `imx` line, then `exit 1` → main.py never runs | `services/cinemate-autostart/camera-ready.sh` via `ExecStartPre` in `cinemate-autostart.service` |
| `CinePiController.__init__` crashes: `_recompute_file_size()` does a plain `res_modes[...]` lookup (every no-camera boot), plus four unguarded `float(get_value(...))` reads of never-seeded keys (fresh Redis only) | `src/module/cinepi_controller.py` |

A third hazard is silent rather than fatal: with no camera, `fps_max` degrades to 1, the
init-time `set_fps()` clamps `fps`/`fps_user` to 1 in Redis, and `cleanup()` persists
`fps_last = 1` — one no-camera boot would drag the next *with*-camera boot down to 1 fps.
The fix must not let the degraded boot corrupt stored operator state.

Decisions taken in the investigating Fable thread (2026-08-26), recorded once here:

- The camera gate becomes **advisory, not blocking**: `ExecStartPre=-…` keeps the 30 s
  wait (its real job — letting a slow-initialising sensor come up before the GUI) but no
  longer vetoes startup. Deleting the gate was rejected: it would regress the
  black-screen-on-boot problem it exists to solve.
- Missing Redis keys get **seed-if-absent defaults** (24 fps / 180°), never unconditional
  writes — a warm Redis keeps the operator's stored values untouched. The init-time
  `set_fps()` is skipped entirely when no camera is present, closing the fps-clamp
  corruption chain.
- The GUI indicator rides the **existing shared state dict**: `populate_values()` gains a
  `camera_missing` flag and a `NO CAM` sensor label, so the web GUI (which consumes that
  dict verbatim) inherits the state in the same change. No new Redis key — the state is
  derivable from `cameras = []`.
- Recovery v1 is **message + existing command**: the indicator tells the operator to
  connect the camera and run `restart cinemate` (full re-exec through fresh detection,
  already a CLI/web command). Hot-plug re-detection without a restart is out of v1 —
  `restart camera` alone is not enough because `SensorDetect`'s mode cache is empty from
  boot — and a background re-probe loop is rejected (heavyweight probe on a timer).

Held open for the plan review, without blocking implementation: the exact HDMI presentation
(status-box badge next to DROP/SYNC vs. a centred message in the empty preview area — the
spec proposes both, badge mandatory, centred message optional) and whether the 30 s gate
wait should shorten.

| commit | change |
|---|---|
| C3.1 | `cinepi_controller.py` · no-camera-safe init: guarded reads with seed-if-absent defaults, `_recompute_file_size()` mode lookup guard, skip init `set_fps()` when `camera_model is None` |
| C3.2 | `main.py` boot path · skip the post-Plymouth `restart_camera()` re-discovery and gate auto storage pre-roll when `cameras == []` |
| C3.3 | GUI · `populate_values()` `camera_missing` + `NO CAM` label + guard its own unguarded `fps_user` read (a throw kills the GUI thread permanently); HDMI badge; web template badge |
| C3.4 | Service · `ExecStartPre=-` in `cinemate-autostart.service`; deployed via the existing `make install` path |
| C3.5 | Docs · troubleshooting/installation pages: what a no-camera boot looks like, how to recover |

**Branch:** `feature/no-camera-start` off `dev` (cinemate only; cinepi-raw untouched —
`cinepi-raw --list-cameras` is still the probe binary, but its behaviour is unchanged).

**Verification.** Desk — new Pi-free tests following the `_test/` `__new__` + fake
pattern (`test_cinepi_controller_startup_sensor_mode.py` is the template): controller init
with empty `res_modes` in both Redis states, `populate_values()` with `cameras = "[]"`,
plus an audit grep for unguarded `float(get_value(...))` on the boot path; full `_test/`
suite green. Hardware — five gates **G0–G4** in the spec, each with its prediction written
in advance; G0 first confirms the two-blocker failure mode on unpatched `dev`, validating
the desk analysis before any fix is trusted. Gate outcomes go to
`cinemate-handbook/lessons/hardware-log.md`.

**Hardware needed:** the dev Pi with the camera cable unplugged — no new hardware. Both
Redis states matter: as-is (warm) and after `redis-cli FLUSHALL` (fresh install), plus a
regression boot with the camera attached.
