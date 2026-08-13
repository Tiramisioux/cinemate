# Execution prompt — Cinemate Web API

Paste the block below into a fresh thread. It is self-contained.

---

```
/cinemate-dev

Implement the Cinemate Web API. Your source of truth is already written — read these
three files before doing anything else, in this order:

  1. cinemate/dev-notes/web-api/IMPLEMENTATION-PLAN.md   ← internals, phases, gates
  2. cinemate/docs/web-api.md                            ← the wire contract
  3. cinemate/docs/building-control-units.md             ← what client devices expect

Do not re-derive the codebase survey. Section 2 of the plan lists 15 verified facts with
file:line references from cinemate dev @ 07d3186d. Re-check a line number if it has moved,
but do not re-investigate the conclusions.

REPO AND BRANCH
- Owning repo: cinemate ONLY, at /Users/patrikeriksson/Documents/cinemate/cinemate
  (this is the dev clone; the top-level /Users/patrikeriksson/Documents/cinemate is a
  separate main-branch clone — do not edit it)
- Cut feature/web-api from dev. Confirm the tree is clean first; if it is not, preserve
  unrelated dirty work and use a temporary worktree under /private/tmp instead.
- cinepi-raw and libcamera are NOT touched by this feature. If you think they are, stop
  and say why before editing anything.

HOW TO WORK
- Follow the phases in plan section 8. Each phase has a gate. Do not start a phase until
  the previous gate passes.
- Phase 0 is verification on the Pi, not code. It answers the two open questions in plan
  section 10 — the real hotspot gateway IP, and whether the web server actually starts
  when Cinemate creates the hotspot itself. Both may change what the docs say. Report the
  findings before writing code.
- Plan section 6 has a "do not" list. Honour it. In particular: never reimplement command
  parsing, argument coercion, or the `rec` special case in the API layer — call
  CommandExecutor.handle_received_data and nothing else. That single dispatcher IS the
  feature.
- Stop and ask if a gate fails twice, or if any change looks like it needs eventlet,
  gevent, a new command vocabulary, or edits to SerialHandler.

HARD CONSTRAINTS
- The CLI and the serial path must behave identically after your changes. They share the
  dispatcher you are modifying. Verify both, do not assume.
- No eventlet, no gevent. Flask-SocketIO runs threaded on Werkzeug (plan fact F13), so
  every open SSE connection holds a thread. Cap SSE; UDP broadcast is the scalable path.
- Defaults must be safe on a stock unit. The hotspot password ships as 11111111, so
  allow_destructive defaults to false and blocks reboot/shutdown/erase/format.
- A missing system.web_api block in settings.json must behave as the documented defaults.
  Users must not have to edit settings.json to get a working API.
- Plain text is the default response format. A microcontroller must never need a JSON
  parser for the common path.

DELIVERY
- Default handoff is: commit on feature/web-api, push with explicit HTTPS
  (git -C <repo> push -u https://github.com/Tiramisioux/cinemate.git feature/web-api),
  then give me the exact Pi commands to run myself — including the src/settings.json
  stash/pop around the branch switch.
- Do not drive the Pi yourself unless I ask for an agent-driven run. Phase 0 verification
  is the exception: for that, read-only inspection over SSH is fine and expected.
- After each phase, tell me the gate result plainly. If a gate failed, say so and show the
  output — do not describe a phase as done when it is not.

WHEN THE CODE LANDS
- Remove the "specification / not implemented" admonitions from the tops of
  docs/web-api.md and docs/building-control-units.md.
- Correct any address, port or behaviour in those two docs that Phase 0 proved wrong.
  The docs were written ahead of the code; the running system wins.
- Add a changelog entry in docs/changelog.md.
- Update dev-notes/web-api/IMPLEMENTATION-PLAN.md section 10 with the answers to the open
  questions, and mark the status line at the top as implemented.
```

---

## Notes for whoever pastes this

- The prompt deliberately does **not** restate the API spec. Restating it invites drift between the prompt and `docs/web-api.md`. The docs are the contract.
- Phase 0 can change the docs. That is intended — both doc pages currently assert `10.42.0.1`, which is inferred, not measured. See plan section 10, question 1.
- If you want the browser GUI migrated onto the same API (removing the duplicated control logic in `src/module/app/main/events.py`), that is a **separate** follow-up branch. Do not fold it in; it makes the diff hard to review and couples a UI regression risk to an additive feature.
