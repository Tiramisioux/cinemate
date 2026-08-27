# Kickoff prompt for the implementing session

Paste everything below the line into a fresh Sonnet thread.

Note: single repo (cinemate), five commits, no cinepi-raw changes. The hardware gates are
unrun — the prompt tells the implementer to produce the desk-verifiable work and stop
before the Pi. Gate G0 (confirming today's failure mode on unpatched `dev`) belongs to the
operator's hardware session, not this thread.

---

Implement C3 — CineMate starts without a camera and says so in the GUI: a no-camera boot
comes up with a working HDMI GUI and web GUI showing a NO CAM indicator, keeps
hotspot/web/settings-editor reachable, and never corrupts stored operator state; recovery
is plug the camera in and `restart cinemate`.

The full spec is at:
`/Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C3-no-camera-start/NO-CAMERA-START-PLAN.md`
on branch `feature/dev-track` — ledger entry C3 in `PLAN.md` beside it.

Read the spec in full before touching anything, and read
`/Users/patrikeriksson/Documents/cinemate/cinemate-handbook/README.md` plus
`orientation/the-traps.md` and `architecture/gui-state-model.md` first — this change rides
the shared `populate_values()` state dict (surfaces 1 and 2 share state, not
presentation). Every design decision in the spec came out of a source-reading
investigation and operator review: implement them, don't relitigate.

Ground rules:

- One repo, one branch: `cinemate`
  (`/Users/patrikeriksson/Documents/cinemate/cinemate`), branch
  `feature/no-camera-start` off up-to-date `dev`, commits C3.1–C3.5 in order. `cd` does
  not persist between shell calls — use `git -C` and absolute paths.
- **Never `git add -A`** (LFS pointer trap) — stage named files only.
- Do not merge to `dev`, do not push without asking, and **do not touch the Pi**. You are
  producing the desk-verifiable half; gates G0–G4 run later on hardware.
- The web template's JS is ES5 (`var`, `function(){}`) — match it. The template embeds
  base64 font data: filter greps with `awk 'length($0) < 250'`.
- Commit messages: `c3.<n>: <scope> — <one-line outcome>`.

Order matters — C3.1 (controller) first, then C3.2 (boot path), C3.3 (GUI), C3.4
(service), C3.5 (docs). Four places will bite you, all called out in the spec; re-read
those sections before writing them:

1. **Seed-if-absent, never overwrite.** The four guarded reads in
   `CinePiController.__init__` write their default back **only when the key is missing**
   from Redis. A warm Redis must come through byte-identical. The paired change — skipping
   the init-time `set_fps()` when `sensor_detect.camera_model is None` — is what stops
   `fps`/`fps_user` being clamped to 1 and then persisted as `fps_last` by `cleanup()`.
   Both halves, or the corruption chain survives. Write the test that asserts no
   `fps`/`fps_user` write happens during a no-camera init against a primed FakeRedis.
2. **`SimpleGUI.run()` has no per-iteration exception catch.** A `populate_values()`
   throw kills the GUI thread for the rest of the session, and the web connect handler
   calls the same method. Guard the `fps_user` read inside `populate_values()` itself
   (`or 24`) even though C3.1 also seeds it — belt and braces on a thread that cannot
   die.
3. **The state signal is the existing `cameras` Redis key** (`[]` written by
   `start_all()` before it aborts). Do not invent a new Redis key for `camera_missing` —
   it is a `populate_values()` dict field derived from the empty camera list, and the web
   GUI receives it through the dict it already consumes.
4. **The service change must survive deployment.** `ExecStartPre=-` goes in the repo copy
   (`services/cinemate-autostart/cinemate-autostart.service`); confirm the root
   `Makefile` `install` target is what copies it, and say so in the commit message so the
   operator knows existing Pis need `sudo make install` + `daemon-reload`.

Also run the audit the spec asks for: grep `cinepi_controller.py`, `simple_gui.py`,
`main.py`, `storage_preroll.py` for remaining unguarded `float(get_value(` /
`int(get_value(` on the boot path, and fix or explicitly justify each hit.

Done means:

1. The five commits match the spec (deviate only where the spec contradicts current
   source, and say exactly where and why).
2. New Pi-free tests following `_test/test_cinepi_controller_startup_sensor_mode.py`'s
   `__new__` + FakeRedis/FakeSensorDetect pattern, covering: the `_recompute_file_size()`
   guard, seed-if-absent vs. warm-Redis-untouched, the no-write-while-degraded assertion,
   and `populate_values()` with `cameras = "[]"` (flag set, `NO CAM`, no throw with
   `fps_user` absent).
3. Full existing `_test/` suite green.
4. A closing summary that lists: files touched per commit, the audit-grep hits and their
   resolutions, and the exact manual Pi commands for the operator's G1–G4 session
   (`git fetch`/`switch`/`pull --ff-only`, `sudo make install`, `daemon-reload`) — G0
   runs on unpatched `dev` first.

Stop after that summary. Do not start a Pi session, do not run hardware gates, do not
merge.
