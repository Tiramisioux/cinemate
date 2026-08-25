> **Provenance:** verbatim copy (2026-08-25) of the operator-side handoff plan at
> `Documents/cinemate/development/format-drive-raw-pane/PLAN.md` on the workstation
> (outside the repo, per the external-workspace convention), committed here so
> review-branch sessions can read it. The ledger entry is **B14** in
> `REMEDIATION-PLAN.md`. Once the feature merges to `dev`, the code is the truth and
> both copies are historical.

# Format-drive button in the settings editor's RAW pane

Handoff plan, written 2026-08-25 against `cinemate` `dev` @ `13ab0225`; revised same
day after operator decisions (see "Settled design decisions" — all three are
operator-approved, implement them as written). Companion kickoff prompt:
`SONNET-PROMPT.md` in this directory.
For the implementing session: read this whole file first. Every claim below was
verified against source on that revision — file references are the anchor, re-check
line numbers before editing. Work in the `cinemate` repo only (no `cinepi-raw` changes).

**Branch:** `feature/raw-pane-format-drive` off `dev`.

## Goal

Add a "Format drive" control to the settings editor's RAW files pane
(`http://cinepi.local:5000/settings-editor/`, page tab "RAW files", section
`#clips`). The operator picks a filesystem (exFAT default / ext4 / NTFS), confirms
in the existing danger modal, and the command `format <fs>` is dispatched through
the normal command executor. The active RAW drive is reformatted and remounted.

## What already exists — do not rebuild

| Piece | Where | State |
|---|---|---|
| Full format backend | `src/module/ssd_monitor.py` — `SSDMonitor.format_drive()` (~line 1011) | Done. Guards (not mounted; `is_writing_buf`/`is_buffering`), sync, unmount escalation (clean → lazy → `fuser -km` evict → lazy), repartition when partition <90% of disk, `mkfs.{ext4,exfat,ntfs}` with `-L RAW` via `sudo`, 120 s mkfs timeout, remount via `self.mount_drive()`. Returns `bool`. |
| Controller wrapper | `src/module/cinepi_controller.py` (~line 2068) | `format_drive(filesystem=None)` → delegates, default `"exfat"`. Discards the bool — leave as is; see "Verifying success" below. |
| CLI command + dispatcher | `src/module/cli_commands.py` — `'format': (…, [str, None])` (~line 111); `handle_received_data()` (~line 227) | Shipped and documented (`docs/cli-commands.md` line 49). Dispatch holds `_dispatch_lock` for the whole handler (lines 259–300); a 2 s acquire timeout returns `(False, "busy")`. Handler **return values are ignored** — for `format exfat` it calls `func('exfat')` then returns `self._confirm_or_ok(func, 'exfat')`. Read `_confirm_or_ok` and confirm it returns `(True, …)` for a method with no read-back parameter before relying on it. |
| Backend tests | `_test/test_ssd_monitor_format.py` | Exist — don't duplicate; leave green. |
| RAW pane endpoints | `src/module/app/settings_editor.py` — `/api/raw/storage`, `/api/raw/takes…`, `/api/raw/bulk` | The pane's established server pattern. `app.config` carries `CINEPI_CONTROLLER`, `REDIS_CONTROLLER`, `COMMAND_EXECUTOR` (`src/module/app/__init__.py`). |
| Storage summary | `src/module/app/raw_files.py` — `storage_summary()` | Reports label / `active` / `filesystem` (psutil fstype) / `device` / sizes per mounted `/media/RAW*`. Used both by the cards UI and by the endpoint's success check below. |
| Storage cards UI | `templates/settings_editor.html` — `renderStorageCards()` (~line 2929) | Renders one card per mounted drive from `/api/raw/storage`; `active: true` marks `/media/RAW`. |
| Confirm modal + toast | same file — `showConfirm(message, onYes, onCancel, opts)` (~line 3184), `showToast()` (~line 3098) | `opts = { title, okLabel, danger }`. Delete-take already uses the danger variant (~line 3045). |
| Action catalogues | `settings_editor.py` `ACTION_METHODS` (line 108) + JS copy (`settings_editor.html` ~line 3302) | `format_drive` already listed in **both**. No catalogue edit needed. |

## Settled design decisions — operator-approved 2026-08-25, don't relitigate

1. **Dispatch through the command executor.** The endpoint calls
   `COMMAND_EXECUTOR.handle_received_data("format <fs>")` — the same serialised path
   CLI, serial, and `/api/v1/cmd` share. No bespoke direct controller call.
   - Accepted trade-off: the dispatch lock is held for the whole format (worst case
     ≈ 2.5 min: unmount escalation + repartition + mkfs + remount), so other
     CLI/serial/web commands get `busy` meanwhile. Formatting is exclusive by
     nature; the operator accepted this explicitly.
2. **Destructive operations are allowed on the browser surface, ungated.** The
   settings editor already deletes clips with no config flag or token; format
   follows the same rule. The "are you sure" step is the existing danger confirm
   modal, client-side, before anything is sent. Do NOT add an `allow_destructive`
   check, a token, or any server-side confirmation dance to this endpoint.
   - `api.py`'s `DESTRUCTIVE_COMMANDS` gate on `/api/v1/cmd` governs **external
     IoT clients** (which have no confirm UI); it is a different surface and stays
     untouched.
3. **Filesystems: exFAT is the default selection; ext4 and NTFS are equally
   selectable.** One short guidance line (ext4 = most robust for long recordings;
   NTFS = works, not recommended). No filesystem is hidden or disabled.
4. **Active drive only.** The backend formats the mounted active drive
   (`self._device_name`); it cannot target a standby drive. Render the control on
   the `active: true` card only. Per-standby formatting = backend change, out of
   scope.
5. **Synchronous request.** The server is threaded werkzeug (`src/main.py` line
   937, `socketio.run` in a thread) and take-zip downloads already block requests
   this long. No background thread, no job queue.
6. **Refuse while recording (409), before dispatching.** Not a permissions gate — a
   sequencing interlock. `ssd_monitor`'s own guard only covers buffer flush, and
   its eviction path `fuser -km`s the mount, which would kill the running writer
   mid-take.

## Verifying success (the one non-obvious mechanism)

The dispatcher ignores handler return values, so `handle_received_data("format …")`
returns `(True, …)` whether mkfs worked or not. The endpoint therefore verifies
against reality **after dispatch returns**: `format_drive()` remounts before it
returns, so the active mount's filesystem tells the truth.

- Requested fs mounted and active → success.
- Active mount still present with the *old* fs → the unmount/format failed → error.
- No active mount → format failed mid-way (drive left unmounted) → error.

Filesystem-name caveat: psutil's fstype for NTFS may be `ntfs`, `ntfs3`, or
`fuseblk` depending on driver — accept all three as a match for `ntfs`. `ext4` and
`exfat` report literally.

## Edits (three files)

### 1. `src/module/app/settings_editor.py` — new route

Add `ParameterKey` to the imports (`from module.redis_controller import
ParameterKey` — not currently imported there), then after `bulk_raw_action()`:

```python
@settings_editor_bp.route("/api/raw/format", methods=["POST"])
def format_raw_drive():
    body = request.get_json(silent=True) or {}
    fs = str(body.get("filesystem") or "").strip().lower()
    if fs not in ("ext4", "exfat", "ntfs"):
        return jsonify({"ok": False, "message": "filesystem must be ext4, exfat or ntfs"}), 400

    command_executor = current_app.config.get("COMMAND_EXECUTOR")
    if command_executor is None:
        return jsonify({"ok": False, "message": "Command dispatcher not available"}), 503

    redis_controller = current_app.config.get("REDIS_CONTROLLER")
    if redis_controller is not None:
        rec = str(redis_controller.get_value(ParameterKey.IS_RECORDING.value, "0") or "0").strip()
        if rec == "1":
            return jsonify({"ok": False, "message": "Refusing to format while recording"}), 409

    logger.info("Dispatching 'format %s' from the settings editor", fs)
    ok, message = command_executor.handle_received_data(f"format {fs}")
    if not ok:
        return jsonify({"ok": False, "message": message or "dispatch failed"}), (503 if message == "busy" else 500)

    # The dispatcher ignores handler return values, so it cannot report mkfs
    # failure -- verify against reality instead: format_drive() remounts
    # before returning, so the active mount's filesystem tells the truth.
    active = next((s for s in raw_files.storage_summary() if s.get("active")), None)
    fstype = ((active or {}).get("filesystem") or "").lower()
    accepted = {"ext4": ("ext4",), "exfat": ("exfat",), "ntfs": ("ntfs", "ntfs3", "fuseblk")}[fs]
    if active and fstype in accepted:
        return jsonify({"ok": True, "message": f"Formatted as {fs} and remounted."})
    if active:
        return jsonify({"ok": False, "message": f"Format may have failed — drive is mounted as {fstype or 'unknown'}. Check the cinemate log."}), 500
    return jsonify({"ok": False, "message": "Format failed — drive did not remount. Check the cinemate log."}), 500
```

Match the module's existing docstring/comment tone (comments state constraints, not
narration).

### 2. `src/module/app/templates/settings_editor.html` — the control

The template's JS is **ES5** (`var`, `function(){}`, string-concat HTML) — match it.
Careful when grepping this file: it embeds base64 font data; filter long lines
(`awk 'length($0) < 250'`).

a. In `renderStorageCards()` (~line 2929): after building each card, for the
   `s.active` card only, append a format row — a `select.field-input` with
   `exfat` (selected) / `ext4` / `ntfs`, a `Format…` button
   (`btn btn-danger-outline`), and a short `card-help` guidance line
   (ext4 = most robust for long recordings; NTFS = not recommended). Cards are
   rebuilt by `innerHTML` on every refresh, so wire listeners right here after
   `wrap.appendChild(card)` (same pattern as `wireClipRowActions()`), using
   data-attributes, not ids.

b. Click → `showConfirm(message, onYes, null, { title: 'Format this drive?',
   okLabel: 'Format', danger: true })`. This modal **is** the are-you-sure step —
   nothing is sent until the operator confirms. The message must name what dies:
   label, device, size, chosen filesystem — e.g.
   `Format RAW (/dev/sda1, 465.8 GB) as ext4? Every take on it is permanently erased.`
   (`s.device`, `s.total_bytes`, `formatBytes()` are all in scope.)

c. On confirm: disable the select and button, set button text `Formatting…`,
   `showToast('Formatting — this can take a couple of minutes. Other commands will report busy until it finishes.')`, then
   `fetch('/settings-editor/api/raw/format', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ filesystem: fs }) })`.

d. On response: `showToast(res.message)`; then `refreshRawPane()` in every case
   (success shows the fresh empty drive; failure re-renders and re-enables the
   controls). A 503 `busy` means another command held the dispatch lock — the
   toast text already covers it. On fetch rejection (Wi-Fi drop mid-format):
   `showToast('Connection lost — the format may still be running. Refresh in a minute.')`
   then `refreshRawPane()`. Don't auto-refresh mid-format — while unmounted the
   pane would truthfully but confusingly show "No RAW storage mounted".

e. If styling is needed beyond existing classes + small inline styles, add rules
   next to the `.storage-card` block in the `<style>` section.

### 3. `_test/test_settings_editor_format.py` — new

Copy the setup pattern from `_test/test_web_api_blueprint.py` (it stubs `redis`,
`smbus`, and the `module.app` package in `sys.modules` so importing a blueprint
module doesn't execute `module/app/__init__.py`'s `flask_socketio` import — reuse
that mechanism, including its `FakeRedis` and its `make_app` shape: a **real**
`CommandExecutor` wrapping a `MagicMock` controller). Register `settings_editor_bp`,
set `COMMAND_EXECUTOR` and `REDIS_CONTROLLER` in `app.config`, and
`mock.patch` `raw_files.storage_summary` to simulate post-format mount states.
Cases:

| Case | Expect |
|---|---|
| `{"filesystem": "vfat"}` | 400, `controller.format_drive` not called |
| valid fs, `is_recording=1` | 409, not called |
| `COMMAND_EXECUTOR` absent | 503 |
| dispatch lock already held (acquire it from the test before the request) | 503, message `busy` |
| dispatch ok, summary shows active `ext4` | 200, `ok: true`, `format_drive` called once with `"ext4"` |
| dispatch ok, summary shows active old fs (e.g. `exfat` after requesting ext4) | 500, `ok: false` |
| dispatch ok, summary empty (no remount) | 500, `ok: false` |
| requesting `ntfs`, summary shows `ntfs3` | 200, `ok: true` |

Note: `settings_editor.py` imports `module.config_loader`, `boot_config`,
`raw_files` (needs `psutil`), `module.jsonc_edit` — all portable; CI installs
`psutil` (`.github/workflows/checks.yml`). Run the suite exactly as CI does:

```
python -m pytest _test/ -q -p no:randomly
```

## Do NOT

- Modify `ssd_monitor.py`, `cli_commands.py`, `cinepi_controller.py`, or `api.py`.
  In particular leave `api.py`'s `DESTRUCTIVE_COMMANDS` / `allow_destructive` gate
  alone — it protects headless IoT clients, not the browser.
- Add any permission gate, config flag, or token to the new endpoint (decision 2).
- Add `format_drive` to the ACTION_METHODS catalogues — it's already in both copies.
- Add per-standby-drive format, an erase button, or a background job queue.
- `git add -A` — stage the three files explicitly.
- Touch docs: no docs page covers the settings editor yet (grepped 2026-08-25), the
  CLI is unchanged, and `docs/cli-commands.md` already documents `format`. Re-grep
  `settings.editor` under `docs/` before finishing; only if a page has appeared since,
  add the control there.

## Verification

**Desk (required before handoff):** full `_test/` suite green, plus a smoke import
check of the blueprint. Also read `_confirm_or_ok` in `cli_commands.py` and confirm
the dispatch-returns-`(True, …)`-for-`format` assumption holds; if it doesn't, say
so and adapt the endpoint's dispatch-result handling accordingly. No Pi needed for
any of the above edits.

**Pi (operator-driven, DESTRUCTIVE — needs a scratch drive with no wanted takes):**

1. Deliver: push the branch; on the Pi
   `git fetch && git switch feature/raw-pane-format-drive && git pull --ff-only`,
   then restart cinemate (Python-only change, no rebuild).
2. In the RAW pane: format as exFAT → card reappears as `exfat`, label `RAW`,
   full capacity, 0 takes. Repeat for ext4 and NTFS (NTFS may report `ntfs3`).
3. Record a short take on the fresh drive; confirm it lands and lists in the pane.
4. Start recording, attempt format → 409 toast, recording undisturbed.
5. During an in-flight format, send `set iso 800` from the CLI → expect `busy`
   behaviour, and normal dispatch again once the format finishes (accepted
   trade-off of decision 1 — confirm it recovers).
6. CLI regression: `format exfat` from the CLI still works (nothing in its path
   changed — this is a sanity check).
7. Watch for a mount fight with `storage-automount.service` right after format
   (SSDMonitor remounts itself while the automount service also owns `/media/RAW`;
   this is pre-existing CLI-path behaviour, but confirm it holds via the browser path).

After the operator confirms results, append a dated entry to
`cinemate-handbook/lessons/hardware-log.md` (entry format at the top of that file);
ask before pushing that repo.

## Delivery

Commit the three files to `feature/raw-pane-format-drive`, push over HTTPS, PR to
`dev`. Merge only after the Pi checklist passes.
