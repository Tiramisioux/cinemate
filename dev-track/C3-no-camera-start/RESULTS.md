# C3 results — shipped 2026-09-02

`PLAN.md` and `NO-CAMERA-START-PLAN.md` (this directory) describe the step as planned:
five commits (C3.1–C3.5), formal hardware gates G0–G4 with predictions stated in advance.
Neither file was updated once implementation started — this is the record of what actually
shipped, filed after the fact from the branch's own commit history and
`cinemate-handbook/lessons/hardware-log.md`.

**Shipped to `dev`** via [PR #183](https://github.com/Tiramisioux/cinemate/pull/183)
("C3: CineMate starts without a camera and says so in the GUI"), merge commit `e5e3b530`,
2026-09-02T17:55Z. Branch `feature/no-camera-start` off `dev`, cinemate only as planned
(cinepi-raw untouched); deleted from `origin` after merge.

## Scale: 24 commits, not 5

`c3.1`–`c3.23` plus one `c3.audit`, not the C3.1–C3.5 in `PLAN.md`. The extra 19 commits are
not polish — two real hardware failures and a post-hardware code-review pass drove them, all
tracked in `hardware-log.md`:

| Commit | What forced it |
|---|---|
| `cf061dfe` c3.1 · `734f7be0` c3.2 · `9e4ec09e` c3.3 · `0034753a` c3.4 · `4e2c198c` c3.5 | The original plan, as filed |
| `91e9634f` c3.audit | Guard `draw_gui()`'s unguarded `WIDTH`/`HEIGHT` re-read, found auditing c3.1–c3.5 before the first hardware pass |
| **First hardware pass, `fdff38f8` (c3.1–c3.9) — FAILED.** Operator: *"i dont see the warning message. it just gets stuck at the welcome message."* `AttributeError: 'CinePiController' object has no attribute 'file_size'` killed the GUI thread — a gap in c3.1's own guard — plus the `wb_cg_rb_array` bug was still live and stored operator state was destroyed (`sensor_mode` 6→0, `fps_max`→1, `fps_steps`→`[1]`) | `fdff38f8` c3.9 fixes the hardware-confirmed crash |
| `fa6ceae2` c3.10 · `9d59557c` c3.11 · `bcf789b0` c3.12 · `dea7a9c1` c3.13 · `579c7e4a` c3.14 · `036a0c78` c3.15 · `88e3120f` c3.16 | Closing what c3.9 exposed: `SimpleGUI.run()` had **zero per-iteration exception handling** (c3.11, not in the original plan at all — any single bad frame killed the GUI thread for the session); `file_size` needed a real no-camera value (c3.10); WB curve, `sensor_mode`, `fps_max` all needed the same guard-not-write treatment C3.1 gave `fps`/`fps_user` (c3.12–c3.14 — D4 was only half-implemented by the plan); a new `installed_files.py` drift check (c3.15, unplanned) because c3.4's advisory gate never reaches an existing Pi via `git pull` — the unit is copied by `make install`, not symlinked; the `camera-ready.sh` timeout cut 30s→8s (c3.16, "D7 (operator decision, 2026-09-02)" — the plan explicitly left this open) |
| **Second hardware pass, `5c5c9bf3` (c3.10–c3.16 on `dev`) — PASSED.** Operator: *"great! it works!"* HDMI GUI paints CAMERA NOT FOUND, web GUI reachable, all three first-pass mechanisms closed | — |
| `64598fda` c3.17 · `829a6078` c3.18 | Presentation, from seeing it live: dropped the NO CAM badge entirely (c3.3 shipped it; c3.17 removed it — "already unmissable" once the full-width message was seen on real hardware), reworded the power warning |
| `bc02d67b` c3.19 · `97f191ca` c3.20 · `6d70e6e0` c3.21 · `daa7ce46` c3.22 · `724ae73b` c3.23 | Post-hardware code review, "review items 1–8," none in the original plan: `rec` had no camera gate at all — a take with no recorder to ever end it (c3.19); `set resolution` on an empty mode table raised a `KeyError` that silently killed the CLI/serial dispatcher thread (c3.20); a second unguarded WB tuning-file `open()` duplicated the exact bug class c3.9/c3.12 were meant to have closed (c3.21); `sensor_detect.py`'s `custom_modes` setting could silently manufacture a non-empty `res_modes`/`camera_model` for a camera that was never detected — per c3.22's own commit message, this "undermines the rest of this branch" since every degraded-boot guard keys on `res_modes` being empty (c3.22); test coverage for the above (c3.23) |

Desk: full `_test/` suite green — 749 passed, 400 subtests (PR #183 body), including a new
integration-style test (`_test/test_no_camera_boot_integration.py`, first appears at c3.19)
that builds a real `CinePiController` via its actual `__init__`, not the `__new__()`-bypass
pattern the plan's own Desk-verification section proposed.

## Hardware verification: real, but not the plan's G0–G4

`hardware-log.md` has no entries labeled G0/G1/G2/G3/G4 — the two passes above are informal,
both a manual foreground `python3 src/main.py`, never a `cinemate-autostart.service` boot.
The core defect (a no-camera boot reaching a usable GUI with a clear indicator) is
hardware-confirmed. Still open, flagged by both `hardware-log.md` and PR #183's own body:

- **The systemd launch path.** The advisory `ExecStartPre=-` (c3.4) and the shortened 8s
  `camera-ready.sh` gate (c3.16) have never been exercised via an actual service boot —
  G1/G2/G4 territory in the plan.
- **D4, the state-corruption guarantee.** No `redis-cli mget` before/after diff was captured,
  no camera-reattach-then-confirm-stored-mode test was run — the plan's G3.
- **The wrong-`dtoverlay` misconfiguration case.** Only the no-ribbon-cable failure mode was
  ever tested — open in both the plan's G0 "Unknowns" and both hardware-log entries.
- **`c3.18`–`c3.23`** (the refuse-to-record gate, the CLI-thread-killing `KeyError` fix, the
  second WB tuning-file bug, the `sensor_detect` fake-camera fix) landed *after* the second
  hardware pass and have never themselves been run on real hardware — desk-verified only.

PR #183's own merge rationale, for the record: safe regardless of the open items, because
"the failure it fixes is strictly worse than what it replaces."

## For whoever runs the outstanding gates

Rerun G0/G1/G2/G4 as an actual `cinemate-autostart.service` boot (not manual foreground) —
current confidence in the advisory gate and the 8s timeout is desk-only. Capture a
`redis-cli mget` before/after a no-camera boot for G3. Test a wrong-`dtoverlay` boot, not
just no-ribbon. None of this blocks anything — C3 is merged and the core fix stands — it is
the gap between "merged" and "hardware-gated" this file exists to keep visible.
