# Kickoff prompt for the implementing session

> **SPENT — do not use.** This prompt was consumed on 2026-08-26. C0 is implemented
> (`e54e691b`), merged to `dev` (PR #152) and hardware-verified the same day. Handing it to a
> session would make it re-implement finished work. Kept for provenance only — see
> [`PLAN.md`](PLAN.md) for the status block and the one remaining regression spot-check.

Paste everything below the line into a fresh Sonnet thread.

---

Implement the format-drive button in CineMate's settings editor RAW pane.

The full spec is at:
`/Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C0-format-drive/FORMAT-DRIVE-PLAN.md`
on branch `feature/dev-track` — ledger entry C0 (formerly B14) in `PLAN.md` beside it. (The operator-side
original of the spec lives outside the repo at
`Documents/cinemate/development/format-drive-raw-pane/PLAN.md`; the two are identical.)

Read the plan in full before touching anything. Every design decision in it is
operator-approved — implement them, don't relitigate.

Ground rules:

- Repo: `/Users/patrikeriksson/Documents/cinemate/cinemate`. Create branch
  `feature/raw-pane-format-drive` off up-to-date `dev`. `cd` does not persist between
  shell calls — use `git -C` and absolute paths.
- The format backend already exists (`SSDMonitor.format_drive` + the CLI `format`
  command). You are adding exactly three files' worth of change:
  1. `POST /settings-editor/api/raw/format` — validates the filesystem, refuses while
     recording (409), dispatches `format <fs>` through
     `COMMAND_EXECUTOR.handle_received_data()`, then verifies success by inspecting
     which filesystem is actually mounted afterwards (the dispatcher ignores handler
     return values).
  2. The control on the active storage card in `templates/settings_editor.html` —
     exFAT default, ext4 and NTFS equally selectable, the existing danger confirm
     modal as the are-you-sure step, `Formatting…` disabled state, toast + pane
     refresh on completion.
  3. `_test/test_settings_editor_format.py`, following
     `_test/test_web_api_blueprint.py`'s setup pattern.
- Do NOT modify `ssd_monitor.py`, `cli_commands.py`, `cinepi_controller.py`, `api.py`,
  or anything under `docs/`. No permission gates, config flags, or tokens on the new
  endpoint — the browser surface is deliberately ungated, like the pane's existing
  clip delete.
- The template's JS is ES5 (`var`, `function(){}`) — match it. The file embeds base64
  font data: filter greps with `awk 'length($0) < 250'`.
- Before wiring the endpoint, read `CommandExecutor._confirm_or_ok` in
  `src/module/cli_commands.py` and confirm that dispatching `format exfat` returns
  `(True, …)` — the plan's post-dispatch mount inspection depends on it. If it
  doesn't hold, adapt as the plan's Verification section says, and tell me.

Done means:

1. The three changes match the plan (deviate only where the plan contradicts current
   source, and say exactly where).
2. `python -m pytest _test/ -q -p no:randomly` is fully green — new tests and the
   existing suite.
3. Committed on `feature/raw-pane-format-drive` with the files staged explicitly
   (never `git add -A`), pushed to GitHub over HTTPS.
4. You hand me: the manual Pi update commands (`git fetch`,
   `git switch feature/raw-pane-format-drive`, `git pull --ff-only`, restart
   cinemate — Python-only change, no rebuild) and the Pi test checklist from the
   plan's Verification section. That checklist is destructive — I'll run it myself
   on a scratch drive.

Do not merge to `dev`, do not open a PR unless I ask, and do not touch the Pi
yourself. Stop and ask if a plan assumption fails.
