# C0 · Format drive from the settings editor's RAW pane

> **STATUS: DONE — implemented, merged and hardware-verified. Nothing here is open work.**
>
> | | |
> |---|---|
> | Implementation | `e54e691b` on `feature/raw-pane-format-drive`, merged to `dev` via [PR #152](https://github.com/Tiramisioux/cinemate/pull/152) |
> | Shipped | `POST /settings-editor/api/raw/format` (`settings_editor.py`), the control on the active storage card (`settings_editor.html`), and `_test/test_settings_editor_format.py` — exactly the three files the spec called for, implementing all six settled design decisions |
> | Hardware | **Full destructive checklist passed 2026-08-26**, operator-confirmed: all three filesystems format and remount from the browser, a take records on the fresh drive, format-while-recording refused with 409, a concurrent CLI command reports `busy` and *recovers*, the CLI `format` path unregressed, no mount fight with `storage-automount.service`. Entry in `cinemate-handbook/lessons/hardware-log.md` (2026-08-26) |
> | Not established | which fstype string NTFS actually reported, and how long a format held the dispatch lock — both unreported on the day. Do not infer them |
>
> `FORMAT-DRIVE-PLAN.md` and `SONNET-PROMPT.md` beside this file are **historical**: the code
> is the truth now, exactly as their own provenance banners predicted. Do not hand the kickoff
> prompt to a session — the work it describes is finished.
>
> **Regression spot-check — CLOSED 2026-09-01.** After `settings_editor.html`/`.py` churn
> (control-row layout, phone stacking, the dotted action/command rule, the `free mode` →
> `free stepping` rename, and a hardening of the *generic* action catalogue's `format_drive`
> entry to `"no_arg": "required"`), the operator confirmed on the Pi that all three
> filesystems — exFAT, ext4, NTFS — still format and remount clean from the browser control.
> The two facts the 2026-08-26 run left unestablished (which fstype string NTFS reports,
> how long a format holds the dispatch lock) were **not** captured in this pass and remain
> open — see the "Not established" row above.
>
> **Provenance:** moved 2026-08-25 from the review ledger
> (`system-review/deliverables/REMEDIATION-PLAN.md` §3 on
> `claude/cinemate-system-review-kickoff-cilicc`, commit `84bcb98b`, where it was batch **B14**) to this development
> track — the original "one ledger holds everything" placement was reversed by the operator
> the same day it was made: C0 is a feature, not remediation. Content below is otherwise
> the ledger entry as written. Closes no findings.

The RAW files pane browses, downloads and deletes takes but cannot prepare a drive — yet
the format backend has existed all along: `SSDMonitor.format_drive()` (unmount escalation,
repartition when the partition underfills the disk, `mkfs.{ext4,exfat,ntfs}` labelled
`RAW`, remount), the CLI `format` command, and `_test/test_ssd_monitor_format.py`. C0 is
the missing UI wiring only.

**Full implementation spec: [`FORMAT-DRIVE-PLAN.md`](FORMAT-DRIVE-PLAN.md) in this
directory** — a verbatim copy of the operator-side handoff plan, written against `dev`
(`13ab022`). The operator-settled decisions, recorded once here:

- Dispatch goes **through the command executor** (`handle_received_data("format <fs>")`
  — the same serialised path CLI/serial/web-API share), accepting that the dispatch lock
  reports `busy` to other commands for the format's duration. Formatting is exclusive by
  nature.
- The browser surface allows destructive operations **ungated**, exactly like the pane's
  existing clip delete; the existing danger confirm modal is the are-you-sure step.
  `api.py`'s `allow_destructive` gate keeps protecting headless IoT clients and is
  untouched.
- exFAT is the default selection; ext4 and NTFS equally selectable. Active drive only.
  Refuse-while-recording (409) as a sequencing interlock, not a permissions gate.

| commit | change | closes |
|---|---|---|
| C0.1 | `POST /settings-editor/api/raw/format` — validates the filesystem, refuses while recording, dispatches `format <fs>` via `COMMAND_EXECUTOR`, then verifies against the remounted filesystem (the dispatcher ignores handler return values, so the active mount is the only truthful status source; accept `ntfs`/`ntfs3`/`fuseblk` as NTFS) | — |
| C0.2 | The control on the active storage card: exFAT-default select + `Format…` danger button + confirm modal naming device, size and filesystem; ES5 to match the template | — |
| C0.3 | `_test/test_settings_editor_format.py` — blueprint tests off `test_web_api_blueprint.py`'s pattern (real `CommandExecutor`, mocked controller, patched `storage_summary`) | — |

**Branch:** `feature/raw-pane-format-drive` off `dev`; merge only after hardware passes.

**Verification:** desk — the full `_test/` suite green. Hardware — **destructive, needs a
scratch drive**: all three filesystems format and remount with label `RAW` at full
capacity; a format attempt during recording is refused; `busy` during an in-flight format
recovers afterwards; no mount fight with `storage-automount.service` after the remount.
The checklist with exact steps is in the plan file.
