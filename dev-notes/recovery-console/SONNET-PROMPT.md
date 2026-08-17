# Execution prompt — Cinemate Recovery Console

Paste the block below into a fresh thread. It is self-contained.

---

```
/cinemate-dev

Implement the Cinemate Recovery Console. Your source of truth is already written — read it
before doing anything else:

  cinemate/dev-notes/recovery-console/IMPLEMENTATION-PLAN.md

Do not re-derive the codebase survey. Section 2 of the plan lists 16 verified facts with
file:line references from cinemate feature/settings-jsonc @ a3680322. Re-check a line number
if it has moved, but do not re-investigate the conclusions.

WHAT THIS IS
A stdlib-only web console on :8080, running as its own root systemd service, that lets the
operator diagnose a failed Cinemate start, edit settings.jsonc and config.txt, and restart
Cinemate — from a phone, over the camera's hotspot, with no laptop and no SSH.

The hotspot ALREADY survives a Cinemate crash (plan fact F1). Do not rebuild it. The gap is
the web surface. If you find yourself writing hotspot creation code outside Phase 1's
credential ladder, you have misread the plan.

STATE RIGHT NOW
- The branch ALREADY EXISTS and should already be checked out: feature/recovery-console,
  cut from dev @ a3680322.
- The plan is ALREADY COMMITTED on it as 84babd4a. Do not cut a new branch, do not rebase
  onto dev, do not rewrite the plan files.
- No implementation code exists yet. Nothing has been installed on the Pi.
- Phase 0 has NOT run. The Pi was unreachable when the plan was written.
- Start by confirming: git -C /Users/patrikeriksson/Documents/cinemate/cinemate status
  should show feature/recovery-console and a clean tree.

REPO AND BRANCH
- Owning repo: cinemate ONLY, at /Users/patrikeriksson/Documents/cinemate/cinemate
  (this is the dev clone; the top-level /Users/patrikeriksson/Documents/cinemate is a
  separate main-branch clone — do not edit it)
- If the tree is dirty with unrelated work, preserve it and use a temporary worktree under
  /private/tmp instead. Do not stash or force-checkout over someone else's changes.
- cinepi-raw and libcamera are NOT touched. If you think they are, stop and say why before
  editing anything.

HOW TO WORK
- Follow the phases in plan section 9. Each phase has a gate. Do not start a phase until the
  previous gate passes.
- Phase 0 is verification on the Pi, not code. It answers open questions 1 and 2 in plan
  section 11 — whether NetworkManager already persists the AP profile with autoconnect, and
  whether :8080 is free on the running unit. Question 1 changes the shape of Phase 1. Report
  the findings before writing code.
- Plan section 7 has an "Explicitly do not" list. Honour it.
- Phases 1 and 2 each ship real value alone. If we stop after either one, the result must be
  coherent and documented, not a half-landed feature.
- Stop and ask if a gate fails twice, or if any change looks like it needs a third-party
  dependency in the recovery path, a second systemd unit for the config.txt timer, or edits
  to cinepi-raw.

HARD CONSTRAINTS
- cinemate-recovery.py imports STANDARD LIBRARY ONLY. No flask, no jinja, no redis, nothing
  from src/module/. "The venv is broken" and "redis is down" are supported failure modes that
  this console must survive. This is the single most important constraint in the plan.
- The recovery service's systemd unit must have NO Wants= or After= on cinemate-autostart.
  That coupling is the bug being fixed.
- Section 4 is the fallback ladder and it is the heart of the design. Every rung must be
  implemented and unit-tested, including the ones that only fire when something else is
  already broken. A fallback you cannot test is not a fallback.
- Every write follows section 4.5 exactly: backup, temp file in the same directory, fsync,
  os.replace, fsync the directory. No exceptions, no shortcuts for "small" files.
- Settings validation (4.4) fails OPEN on rung 3 — if it cannot validate, it still writes and
  labels the write unvalidated. The file being edited is already broken; refusing to write
  would strand the operator. Safety comes from the backup.
- config.txt editing defaults to OFF (allow_config_txt: false) and must arm the confirm-or-
  revert marker (4.6) on every successful write.
- Never let a free-form service name reach subprocess. Allowlist only: cinemate-autostart,
  wifi-hotspot, storage-automount.
- Do not rename wifi-hotspot.service. Renaming orphans the enabled unit on existing installs.
- A missing system.recovery block in settings.jsonc must behave as the documented defaults.
  Requiring an edit to settings.jsonc to get a working recovery console is circular.

TESTING
- Everything in plan sections 4.2–4.6 is pure logic. Test it on the Mac, no hardware.
- Convention is _test/test_*.py, run with:
  python3 -m unittest discover -s _test -p "test_*.py"
- The vendored jsonc.py MUST ship with a golden test asserting behavioural equality against
  module.config_loader.strip_jsonc. That test is the only thing preventing a third silently
  drifting JSONC parser in this tree (plan fact F14). Do not skip it.

DELIVERY
- Default handoff is: commit on feature/recovery-console, push with explicit HTTPS
  (git -C <repo> push -u https://github.com/Tiramisioux/cinemate.git feature/recovery-console),
  then give me the exact Pi commands to run myself — including the settings.jsonc stash/pop
  around the branch switch, and the `sudo make -C services enable-cinemate-recovery` step.
- Do not drive the Pi yourself unless I ask for an agent-driven run. Phase 0 verification is
  the exception: read-only inspection over SSH is fine and expected.
- After each phase, tell me the gate result plainly. If a gate failed, say so and show the
  output — do not describe a phase as done when it is not.

WHEN THE CODE LANDS
- Add docs/recovery-console.md and wire it into mkdocs.yml. It must include the pull-the-SD-
  card fallback from plan section 4.1 — that is the honest limit of what the console can
  recover, and hiding it would be dishonest.
- Correct docs/system-services.md: it currently opens with "three long-running services".
- Document the hotspot credential ladder in docs/hotspot-logic.md.
- Add a changelog entry in docs/changelog.md.
- Update plan section 11 with the answers to the open questions, and change the status line
  at the top of the plan from "not implemented" to what actually landed.
```

---

## Notes for whoever pastes this

- The prompt deliberately leads with **"the hotspot already survives a crash."** That was the single biggest misconception going in, and an implementer who does not internalise it will spend the first phase rebuilding something that already works.
- **Phase 0 can change Phase 1.** If NetworkManager already persists the AP with `autoconnect=yes`, the watchdog stops being a keep-alive and becomes a credential reconciler — a smaller, better change. Do not let Phase 1 start before that question is answered on hardware.
- The **stdlib-only rule is not stylistic**. It is what makes the console survive the failure modes it exists to diagnose. Any PR that adds a third-party import to the recovery path should be rejected on sight, even if it is "just" a templating library.
- **Fact F4 is shippable on its own.** A broken `settings.jsonc` currently makes the hotspot come up as `CinePi`/`11111111` instead of the configured SSID — so the operator's phone will not auto-join, in exactly the situation where they need it most. If this whole plan gets shelved, land Phase 1 anyway.
- Phase 5 (config.txt) is the only phase that can brick a unit. It is last, it is default-off, and it has an auto-revert. If schedule pressure appears, drop Phase 5 before dropping Phase 4 — a phone-editable `settings.jsonc` covers the overwhelmingly common failure, which is a typo in the file the operator edits most.
- If you want the recovery console to also show live camera status, or to grow buttons for common camera settings — that is a **separate** follow-up. Every control added to this service is another thing that can break the one path that is supposed to always work.
