# Cinemate Recovery Console — implementation plan

**Status:** Shipped. All five phases are implemented and unit-tested (355/355 tests pass). Phases 0-3's hardware gates (section 9) have run on the live Pi and passed — see section 11. Phases 4/5 (the settings.jsonc editor's write path and the config.txt confirm-or-revert machine) are implemented and unit-tested but their *hardware* gates were not exercised end-to-end on the Pi in this round — the settings editor route was reached and displayed correctly, but no save was performed live, and config.txt editing was never enabled (`allow_config_txt` stayed at its default `false`) or tested. Merged to `dev`.
**Owning repo:** `cinemate` only. `cinepi-raw` and `libcamera` are untouched.
**Branch:** `feature/recovery-console`, cut from `cinemate` `dev` @ `a3680322`, merged back into `dev`.
**Source of truth:** this file.

---

## 1. Goal

When Cinemate fails to start, the operator must still be able to — **from a phone, over the camera's own hotspot, with no laptop and no SSH**:

1. see *why* it failed,
2. edit `settings.jsonc` and `/boot/firmware/config.txt`,
3. restart Cinemate.

Non-goal: replacing the Cinemate web GUI. The recovery console is deliberately ugly, deliberately dependency-free, and deliberately not a camera UI.

Non-goal: moving the hotspot into a separate git repository. The isolation that matters is a **process and dependency boundary**, not a repo boundary — see section 3.

---

## 2. Verified starting state

All facts below were read from `cinemate` `feature/settings-jsonc` @ `a3680322`. Do not re-derive them; do re-verify any line number that has moved.

| # | Fact | Evidence |
|---|---|---|
| F1 | The hotspot **already** survives a Cinemate crash. `wifi-hotspot.service` is root-run, `Restart=always`, and has no dependency on `cinemate-autostart.service` | `services/wifi-hotspot/wifi-hotspot.service` |
| F2 | The watchdog is a 25-line shim that polls every 60 s and reaches into the Cinemate source tree | `services/wifi-hotspot/wifi-hotspot.py:8` (`sys.path.insert`), `:10`, `:19-23` |
| F3 | It runs under `/usr/bin/python3`, **not** the venv — and that works, because `config_loader` imports only `json`/`logging`/`pathlib` | unit `ExecStart=`; `src/module/config_loader.py:1-3` |
| F4 | A broken `settings.jsonc` makes the hotspot come up as **`CinePi` / `11111111`**, not the configured SSID. `_load_settings` catches every exception and returns `{}`; `_extract_credentials({})` then yields the compiled-in defaults | `src/module/wifi_hotspot.py:44-58`, `:61-74` |
| F5 | Two independent owners create the hotspot, with no ordering constraint between them | `src/main.py:677` (`start_hotspot`) and the watchdog loop (F2) |
| F6 | The Flask UI and `/api/v1` are built ~250 lines into `run_application()`, so any earlier exception means no HTTP surface at all | `src/main.py:920`, `:924` (binds `0.0.0.0:5000`) |
| F7 | The web server is additionally gated on an interface already having an IP. Lose that race and the UI is gone for the whole session | `src/main.py:919` `network_available()`; documented in `docs/hotspot-logic.md` |
| F8 | `main()` catches `SettingsLoadError` and bare `Exception`, prints a block to tty1, returns 1 | `src/main.py:1055` (re-verified @ `3ac26d88`, was `:1053-1075`) |
| F9 | `cinemate-autostart.service` has **no `Restart=` directive**. A crash leaves it dead until manual intervention | `services/cinemate-autostart/cinemate-autostart.service`; confirmed live on the Pi, `Restart=no` (Phase 0) |
| F10 | The failure block is persisted to disk and is readable by another process | `Environment=CINEMATE_STARTUP_FAILURE_FILE=/home/pi/.cache/cinemate/startup-failure.ansi` at `src/main.py:59-61`; writer at `:217-218` (re-verified @ `3ac26d88`, was `:211`) |
| F11 | **No `config.txt` code path exists anywhere in `src/`.** The only affordance is the `editboot` bashrc alias | `grep -rn "config\.txt" src/` → zero hits; `cinemate-install.sh` bashrc block |
| F12 | Support services install through one umbrella Makefile driven by a single variable | `services/Makefile:4` — `SUBSERVICES := storage-automount wifi-hotspot redis-log-maintenance` |
| F13 | The `pi` sudoers drop-ins grant `mount`/`umount`/`main.py`/venv binaries — **not** `systemctl` | `cinemate-install.sh:1514` and the block above it |
| F14 | The installer already vendors a **second** copy of `strip_jsonc`, with a "keep in sync by hand" comment, because the heredoc runs under system python3 | `cinemate-install.sh:1586-1589` |
| F15 | Port map in use: `5000` Flask, `8000` cinepi-raw MJPEG preview, `8888` UDP status broadcast, `6379` redis. `8080` is free | `src/main.py:924`; `src/module/web_api_settings.py`; `grep -rn 8080` → no hits outside a CSS colour |
| F16 | Settings live at `/home/pi/cinemate/settings.jsonc`; venv at `/home/pi/.cinemate-env` | `src/main.py:51`; `src/module/wifi_hotspot.py:37`; autostart unit `ExecStart=` |

### Consequences

- **F1** — "move the hotspot out so it survives" is already done. Do not rebuild it. The gap is the **web surface**, not the AP.
- **F4** — the failure mode is worse than "no UI". In the exact scenario where the operator most needs to reach the camera, the network's *name changes*. Fixing this is Phase 1 and is worth shipping on its own.
- **F6/F7/F8** — a recovery console cannot live inside `main.py` at any position. It must be a different process.
- **F3/F14** — stdlib-only is already the proven pattern for out-of-app code on this device. Follow it; do not import flask into the recovery path.
- **F9** — an independent, cheap improvement, but it interacts with the tty1 failure display. See open question 4.
- **F11** — config.txt editing is entirely new functionality and is the highest-risk item in this plan. It is deliberately last.

---

## 3. Architecture

```
                    ┌─ NetworkManager AP profile (autoconnect)   ← hotspot exists before any Python
                    │
wifi-hotspot.service ─── reconciles credentials, 60 s              [root, stdlib, no cinemate dep]
                    │
cinemate-recovery.service ── :8080  status / logs / edit / restart [root, stdlib, no cinemate dep]
                    │                         │
                    │                         └── systemctl restart cinemate-autostart
                    │
cinemate-autostart.service ── :5000 Flask UI + /api/v1             [pi, venv, redis, cinepi-raw]
                              :8888 UDP broadcast
```

Three services, one direction of dependency. The bottom row may die at any time without affecting the two above it. Nothing above imports anything from `src/module/`.

**Why not a separate git repo.** The installer already loops `SUBSERVICES` (F12) — adding a fourth is a one-word change. A second repo means a second clone, a second update path, and a second copy of the settings schema to keep aligned. That schema was restructured twice on this branch alone (`c171975e`, `2fcdcc37`). Schema drift between two repos would become the new failure mode, and it would fail precisely when recovery is needed. The crash-survival property comes from the systemd unit and the empty dependency list, not from the `.git` boundary.

---

## 4. Fallback ladder

This is the core of the design. Every layer degrades to a simpler one; no layer can take the layer below it down with it.

### 4.1 What still works as things break

| What is broken | Hotspot | Recovery `:8080` | Cinemate `:5000` |
|---|---|---|---|
| Nothing | configured SSID | yes | yes |
| Cinemate crashed at startup | configured SSID | yes | **no** |
| `settings.jsonc` unparseable | **last-good SSID** (today: reverts to `CinePi`) | yes, read-only edit surface | no |
| venv / pip broken | configured SSID | yes | no |
| redis down | configured SSID | yes | no |
| `wifi-hotspot.service` dead | NM autoconnect profile keeps AP up | yes | depends |
| Recovery service crashed | configured SSID | `Restart=always`, back in 5 s | unaffected |
| `config.txt` fatal, Pi will not boot | — | — | — |

The last row is the honest limit. Nothing running on the Pi can recover a Pi that does not boot. The documented fallback is: pull the SD card, mount the FAT boot partition on any Mac or Windows machine, restore `config.txt` from the `.bak` this plan requires to always exist. That must be printed in the recovery UI next to the config.txt editor, not buried in docs.

### 4.2 Hotspot credential ladder (Phase 1)

Applied in order, on every reconcile pass:

1. `settings.jsonc` parses → use `system.wifi_hotspot`, and write the result to `/var/lib/cinemate/hotspot.last-good.json`
2. parse fails → use `/var/lib/cinemate/hotspot.last-good.json`
3. cache missing or unreadable → compiled-in `CinePi` / `11111111`

Whichever rung is used, write the rung and the reason to `/var/lib/cinemate/hotspot.state`. The recovery console displays it. The operator must be able to learn *"you are on the cached SSID because settings.jsonc is broken"* without reading a journal.

This is the whole fix for F4, and it is small.

### 4.3 Recovery console config ladder (Phase 2)

The bootstrap paradox: the recovery service cannot read its own configuration only from `settings.jsonc`, because "`settings.jsonc` is unparseable" is its primary use case.

1. `settings.jsonc` parses → `system.recovery` block
2. parse fails → `/etc/cinemate-recovery.conf`, flat `key=value`, written by the installer
3. missing → compiled-in defaults (`enabled=true`, `port=8080`, `token=""`, `allow_config_txt=false`)

### 4.4 Settings validation ladder (Phase 4)

1. venv python + `module.config_loader.load_settings` → **the exact error the operator would see on tty1**, with line, column and context. Zero duplicated parsing logic.
2. venv missing or import fails → system python3 + the vendored `jsonc.py` + `json.loads` → generic parse error
3. neither available → allow the write, label it **"unvalidated"** in the UI

Rung 3 is deliberately fail-**open**. The file being edited is already broken; refusing to write it would strand the operator. Safety comes from the backup, not from the refusal.

### 4.5 Write discipline (Phases 4 and 5)

Every write, without exception:

1. read current bytes, write to `/var/lib/cinemate/backups/<name>.<utc-timestamp>.bak`
2. write the new content to a temp file **in the same directory**
3. `flush()` + `os.fsync()`
4. `os.replace()` — atomic within a filesystem
5. `fsync()` the directory

Keep the last 10 backups per file. Never delete the oldest.

### 4.6 config.txt confirm-or-revert (Phase 5)

After a successful `config.txt` write, drop `/var/lib/cinemate/config-pending.json` recording the backup path.

On every start, the recovery service checks for that marker:

- present → start a countdown (default 300 s) and show a red **KEEP THIS CONFIG** banner on every page
- operator clicks Keep → delete the marker, done
- countdown expires → restore the backup, delete the marker, `reboot`

No second systemd unit. The state machine lives in the recovery service and inherits its `Restart=always`.

This recovers *boots that succeed but are broken* — no camera, no HDMI, no network. It cannot recover a Pi that never reaches userspace; see 4.1.

### 4.7 Hard rules the recovery service must never break

- Never restarts `NetworkManager`.
- Never stops `wifi-hotspot.service` — it may only *restart* it, and only behind a re-arm timer that restores the AP if the connection is not re-established within 60 s.
- Never edits its own unit file or its own script.
- Never imports anything outside the standard library.
- Never requires redis, the venv, `cinepi-raw`, or a mounted `/media/RAW`.

---

## 5. HTTP surface

Plain HTML, server-rendered, one file. A little vanilla JS for the journal tail. No framework, no CDN, no build step — it must render on an old phone with no internet.

| Route | Method | Purpose | Phase |
|---|---|---|---|
| `/` | GET | Dashboard: service states, hotspot rung + reason, disk free, uptime | 2 |
| `/why` | GET | Rendered `/home/pi/.cache/cinemate/startup-failure.ansi` (F10), ANSI → HTML | 2 |
| `/log` | GET | `journalctl -u cinemate-autostart -n 200 --no-pager`, `?n=` capped at 2000 | 2 |
| `/service/<name>/<action>` | POST | `restart` \| `stop` \| `start`; `<name>` restricted to an allowlist | 3 |
| `/edit/settings` | GET, POST | textarea; POST validates via 4.4, backs up via 4.5 | 4 |
| `/edit/config` | GET, POST | same; arms 4.6; hidden unless `allow_config_txt` | 5 |
| `/confirm-config` | POST | clears the pending marker | 5 |
| `/health` | GET | `ok` as `text/plain` — liveness for scripts | 2 |

Service allowlist for `/service/`: `cinemate-autostart`, `wifi-hotspot`, `storage-automount`. Nothing else, ever. No free-form service name reaches `subprocess`.

---

## 6. Settings

New block in `settings.jsonc` and `settings.schema.json`:

```json
"system": {
  "recovery": {
    "enabled": true,
    "port": 8080,
    // Required on every request once non-empty. Leave "" only on a
    // trusted/isolated hotspot -- but note this console can restart the
    // camera and edit config.txt.
    "token": "",
    // false hides the config.txt editor entirely. Default false: a bad
    // config.txt can make the Pi unbootable, and nothing running on the
    // Pi can recover that.
    "allow_config_txt": false,
    // Seconds to confirm a config.txt change before it auto-reverts.
    "config_confirm_timeout_s": 300
  }
}
```

A missing `system.recovery` block must behave exactly as these defaults. The operator must not have to edit `settings.jsonc` to get a working recovery console — that would be circular.

Installer writes the same values to `/etc/cinemate-recovery.conf` as flat `key=value` (ladder rung 2, section 4.3).

---

## 7. File-by-file changes

| File | Change | Risk |
|---|---|---|
| `services/cinemate-recovery/cinemate-recovery.py` | **new.** The whole console. stdlib only: `http.server.ThreadingHTTPServer`, `subprocess`, `json`, `os`, `shutil`, `pathlib`, `html`. | new file |
| `services/cinemate-recovery/jsonc.py` | **new.** Vendored stdlib-only JSONC stripper. Third copy in the tree (F14) — ship it with a golden test asserting behavioural equality against `module.config_loader.strip_jsonc`. | Low |
| `services/cinemate-recovery/cinemate-recovery.service` | **new.** `After=network.target`. **No** `Wants=`/`After=` on `cinemate-autostart` — that coupling is the bug being fixed. `Restart=always`, `RestartSec=5`, `User=root`. | new file |
| `services/cinemate-recovery/Makefile` | **new.** Copy of the `wifi-hotspot` Makefile with names changed. | Low |
| `services/Makefile` | add `cinemate-recovery` to `SUBSERVICES` (F12) | Low |
| `services/wifi-hotspot/wifi-hotspot.py` | credential ladder 4.2; write `hotspot.state`; reconcile rather than only create | Low |
| `src/module/wifi_hotspot.py` | `_load_settings` must distinguish *absent* from *unparseable* and report which. It currently collapses both to `{}` (F4). | **Medium** — used by both owners |
| `src/main.py` | `start_hotspot()` becomes a no-op when `wifi-hotspot.service` is active, so there is one owner (F5) but no regression when the service is not installed | Low |
| `settings.jsonc`, `settings.schema.json` | `system.recovery` block | Low |
| `cinemate-install.sh` | `ENABLE_RECOVERY_CONSOLE_SERVICE` flag; `enable-cinemate-recovery`; write `/etc/cinemate-recovery.conf`; create `/var/lib/cinemate/` | Low |
| `docs/system-services.md` | fourth service; correct the "three long-running services" opening line | Docs |
| `docs/recovery-console.md`, `mkdocs.yml` | **new** operator page: how to reach it, what it can do, and the pull-the-SD-card fallback from 4.1 | Docs |
| `docs/hotspot-logic.md` | document the credential ladder and the `hotspot.state` file | Docs |

### Explicitly do not

- Do **not** import flask, jinja, redis, or anything from `src/module/` into `cinemate-recovery.py`. "The venv is broken" is a supported failure mode.
- Do **not** rename `wifi-hotspot.service`. Renaming orphans the enabled unit on every existing install.
- Do **not** put the recovery console on `:5000`, `:8000` or `:8888` (F15).
- Do **not** add a second systemd unit for the config.txt confirm timer. It belongs in the recovery process (4.6).
- Do **not** let a free-form service name reach `subprocess`. Allowlist only (section 5).
- Do **not** build a camera control UI here. Every control added is another thing that can break the recovery path.
- Do **not** touch `cinepi-raw` or `libcamera`. If you think you need to, stop and say why.

---

## 8. Security posture

The console runs as root, can restart the camera, and can edit `config.txt`. The hotspot password ships as `11111111`.

- `token` defaults to `""` — matching `system.web_api` — but `allow_config_txt` defaults to **false**. The dangerous capability is off by default even on an open hotspot.
- Read-only routes (`/`, `/why`, `/log`, `/health`) stay reachable without a token so a locked-out operator can always *diagnose*. Only mutating routes check it.
- Log every mutating action to the journal with the client IP.

---

## 9. Phases and gates

Each phase must pass its gate before the next starts. Phases 1 and 2 each ship real value alone.

| Phase | Deliverable | Gate |
|---|---|---|
| **0** | Verify assumptions on the Pi. No code. | `nmcli -f connection.autoconnect con show Hotspot` records whether NM already persists the AP; `ss -tlnp \| grep 8080` shows the port free; `systemctl stop cinemate-autostart` → hotspot **stays up** and SSID is unchanged (proves F1 on hardware) |
| **1** | Hotspot credential ladder + single owner | Corrupt `settings.jsonc`, reboot → hotspot comes up on the **last-good SSID**, not `CinePi`; `/var/lib/cinemate/hotspot.state` names the rung and the reason; restore the file → configured SSID returns within one reconcile pass |
| **2** | `cinemate-recovery.service`, read-only | `systemctl stop cinemate-autostart`, then from a **phone on the hotspot**: `:8080/` shows `cinemate-autostart: inactive`, `/why` shows the real startup failure text, `/log` shows the journal. `:5000` is dead throughout |
| **3** | Service control | Restart Cinemate from the phone; it comes back; the recovery console stays up across the restart. Stop → `/` reflects it within 2 s |
| **4** | `settings.jsonc` editor | Submit invalid JSONC → rejected, and the error shown is **the same text tty1 shows**; submit valid → backup exists under `/var/lib/cinemate/backups/`, Cinemate restarts clean; kill the venv and retry → rung 2 error, still writable |
| **5** | `config.txt` editor + confirm-or-revert | Write a benign change, reboot, **do not** confirm → auto-reverted and rebooted within the timeout; repeat and confirm → change persists, marker cleared |

---

## 10. Test notes

Everything in sections 4.2–4.6 is pure logic with no hardware in it. Test it on the Mac.

- Convention is `_test/test_*.py`, run with `python3 -m unittest discover -s _test -p "test_*.py"` from the repo root.
- Unit-testable without a Pi: the credential ladder (all three rungs plus the state file), the atomic-write sequence, backup rotation at 10, the validation ladder's three rungs, the confirm-or-revert state machine, the service allowlist, and ANSI→HTML rendering of the failure block.
- The vendored `jsonc.py` needs a golden test against `module.config_loader.strip_jsonc` over the same corpus — that test is the only thing standing between this and a third silently-drifting parser (F14).
- Fake `subprocess` for `systemctl` and `nmcli`. Do not shell out in tests.
- Regression that must not break: `wifi-hotspot.service` must still work on a unit where `/var/lib/cinemate/` does not exist yet.

---

## 11. Open questions

1. **Does NetworkManager already persist the AP with `connection.autoconnect=yes`? ANSWERED (Phase 0, 2026-08-17, live unit).** No. The profile is persisted to disk (`/etc/NetworkManager/system-connections/Hotspot.nmconnection`, mode 0600) but ships with `autoconnect=false`. However `802-11-wireless-security.psk-flags` is `0` (system-owned, not agent-owned), so the stored PSK is usable with no login session and no secret agent — flipping `autoconnect` to `yes` is sufficient to make layer 0 real. Phase 1 implements this: `WiFiHotspotManager.set_autoconnect()` in [wifi_hotspot.py](../../src/module/wifi_hotspot.py) asserts `connection.autoconnect=yes` on every reconcile pass when `system.wifi_hotspot.enabled` is true, and `no` when it is false (so disabling the hotspot in settings isn't undone by NM at the next boot). The watchdog was reshaped as planned, from pure keep-alive to a full reconciler (`reconcile()`), not just a demotion.
2. **Is `:8080` free on the running unit? ANSWERED (Phase 0, live unit).** Yes. Full port map observed: `5000` Flask (pid 885), `8000` cinepi-raw MJPEG (pid 1245), `6379` redis, `53` dnsmasq (`10.42.0.1`, AP-scoped), `22` sshd, `631` cupsd (localhost only, not in F15's map but harmless). No docs server was running at verification time. `8080` free.
   - Corollary not previously stated: the AP subnet is `10.42.0.1/24` (`wlan0`), so the console's real address is `http://10.42.0.1:8080` — now documented in [docs/recovery-console.md](../../docs/recovery-console.md).
3. **Should the console bind hotspot-only or all interfaces?** Unchanged from the plan: binds `0.0.0.0`. Not revisited.
4. **Should `cinemate-autostart` get `Restart=on-failure`?** (F9.) Confirmed live: `Restart=no` on the running unit. Still out of scope for this branch; not decided.
5. **Should the settings editor offer a schema-aware form instead of a textarea?** Not revisited. Phase 4 (`/edit/settings`) shipped as a textarea, per the original plan.

### Phase 0 hardware findings (2026-08-17, `cinepi.local` = `192.168.2.2`, kernel `6.12.93+rpt-rpi-2712`, repo at `dev`@`06c5983`)

All checks were read-only.

- **F1 confirmed via the resolved systemd dependency graph**, not a live stop test: `wifi-hotspot.service` has `BindsTo=∅ PartOf=∅ Requisite=∅`; `cinemate-autostart.service` has `Wants=∅ BindsTo=∅ PartOf=∅` and its `ExecStopPost=` hooks (`cinemate-startup-failure-display.sh`, `cinemate-console-handoff.sh`) touch neither networking nor the hotspot. `systemctl list-dependencies --reverse cinemate-autostart` shows nothing depends on it below `multi-user.target`. No coupling exists in either direction.
- `/var/lib/cinemate` did not exist on this unit before Phase 1/2 landed — confirms the section 10 regression note was describing the *current*, not a hypothetical, state.
- `/home/pi/.cache/cinemate/startup-failure.ansi` was absent (clean start) — `/why` must treat absence as the healthy case.
- F13 (sudoers) confirmed live: `pi` may sudo `mount`/`umount`/`ntfs-3g`/`mount.ext4`/`main.py`/`run_cinemate.sh`/venv binaries — no `systemctl`. This is the concrete reason the recovery console must run as root.
- `redis-log-maintenance.timer` was inactive/disabled on this unit despite being in `SUBSERVICES` — pre-existing, unrelated to this branch.

A live console smoke test on the Mac (simulated broken `settings.jsonc`, simulated `cinemate-autostart: failed`, faked `systemctl`/`journalctl`) exercised every route (`/`, `/why`, `/log`, `/edit/settings`, `/edit/config`, `/service/<name>/<action>`, `/health`) and found two real bugs the unit tests could not see on their own: `RecoveryHandler.runner` needed `staticmethod()` (a bare function on the class is a descriptor and silently binds `self` as its first positional argument), and `systemctl()` needed to catch `OSError` around a missing `systemctl` binary rather than 500. Both are fixed and covered by the smoke test's structure, though the smoke test itself is not part of the persisted `_test/` suite (it exercises HTTP end-to-end, which is out of scope for the stdlib-only ladder tests).

### Phases 1-3 hardware gate results (2026-08-17, live unit, verified by user)

All three gates passed, with two deployment gotchas surfaced along the way that are worth recording for the next branch that touches this path.

**Deployment gotcha 1 — `services/wifi-hotspot/wifi-hotspot.py` is an installed copy, not a live import.** `src/module/wifi_hotspot.py` (the manager class, holding the ladder logic) is imported at runtime via `sys.path.insert(0, "/home/pi/cinemate/src")`, so a plain `git pull` + `systemctl restart wifi-hotspot` picks it up immediately. But the *entrypoint* script the service actually execs is a separate installed copy at `/usr/local/bin/wifi-hotspot.py`, refreshed only by `make install-wifi-hotspot`. A first test round against a bare `restart` silently exercised the pre-existing entrypoint and produced misleading "the ladder isn't doing anything" symptoms (no `hotspot.state`, SSID always `CinePi`) that had nothing to do with the new code. Fixed by running `sudo make -C services install-wifi-hotspot && sudo systemctl restart wifi-hotspot`; standard Pi handoff instructions for this repo should include the explicit `install-<service>` step, not just `restart`, whenever a service's entrypoint script changed.

**Deployment gotcha 2 — mid-session branch collision.** Partway through Phase 1/2 implementation, something outside the implementing session checked out `feature/settings-editor-ui` in the same local clone and committed twice there, while uncommitted recovery-console work was still sitting in the working tree. No commits landed on the wrong branch — recovered cleanly via `git stash push -u` → `git switch feature/recovery-console` → `git stash pop` (one clean auto-merge, no conflicts). Two local clones or sessions sharing one working tree is a real hazard on this repo; worth a worktree per concurrent task.

**Phase 1 — PASS.** After the entrypoint reinstall, `wifi-hotspot.service` correctly reconciles and writes `/var/lib/cinemate/hotspot.state`; the console's status page renders it as *"Hotspot SSID CinePi from rung 1 (settings): settings.jsonc parsed"*. This unit's configured SSID happens to equal the compiled-in default (`CinePi`), so the plan's literal "not CinePi" visual check can't discriminate rung 2 (cache) from rung 3 (default) on this specific hardware — the rung+reason display is the actual proof mechanism the plan wanted, and it works. Rung 2 was not separately exercised with a distinct custom SSID; the mechanism (`read_last_good`/`write_last_good` round-trip) is covered by the unit test suite instead.

**Phase 2 — PASS.** With `settings.jsonc` corrupted, `:5000` confirmed dead via `ss -tlnp` while `:8080` served a real browser (screenshot evidence) showing `cinemate-autostart: failed` in red against `wifi-hotspot`/`storage-automount: active` in green.

**Phase 3 — PASS.** The console's Restart button was exercised through both outcomes: `systemctl restart cinemate-autostart → exit 1` against broken settings, and a full recovery to `active` once settings were restored.

**F10 (persisted startup failure) — reconfirmed correct, not a bug.** Two rounds of live testing initially looked like `persist_startup_failure()` was silently failing (directory created, file never appearing). Root cause was test methodology, not the code: `cinemate-autostart.service`'s `ExecStopPost=` scripts (`cinemate-startup-failure-display.sh`, `cinemate-console-handoff.sh`) take 9-12 seconds to complete against a 5s `TimeoutStopSec`, so `systemctl restart` issued back-to-back collides mid-transition and logs a cosmetic `Job for cinemate-autostart.service canceled.` — while the actual crash-and-report cycle just hadn't finished yet. A test that separates `stop` (wait ~12s) from `start` (wait ~5s) shows the file written correctly, 539 bytes, exact tty1-format content. This stop-sequence slowness is pre-existing, unrelated to this branch, and not fixed here — but it means the console's own restart handler (section 5, `/service/<name>/<action>`) should be read as "fire and poll `/`", not "trust the immediate exit code," since a `restart` can report `canceled` on the systemd side while the underlying operation still completes correctly a few seconds later.

**Settings.jsonc recovery technique confirmed live.** `settings.jsonc` is git-tracked and, on this unit, had zero uncommitted drift from the branch at the time of an accidental `echo '{broken' > settings.jsonc` corruption. `git checkout -- settings.jsonc` cleanly and safely restored the exact pre-corruption content — a materially better recovery path than trusting an ad hoc `/tmp` copy, which in this session had itself been silently corrupted by a mistimed backup command. Worth remembering as the default "I broke settings.jsonc by hand" recovery move on any unit where the file isn't known to carry uncommitted local edits.

**Not exercised on hardware this round:** Phase 4's actual `/edit/settings` write path (a `Save` was never clicked against real hardware — only the GET view, showing the broken content, was observed) and all of Phase 5 (`config.txt` editing stayed at its default `allow_config_txt: false`, untested). Both are unit-tested and considered code-complete per the plan's original scope, but their live gates remain open for a future round.
