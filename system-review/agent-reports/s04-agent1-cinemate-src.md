# S04 Agent 1 — cinemate `src/` dead & redundant code

- **Scope:** `src/` (47 Python files, 19,794 LOC)
- **ID block:** F-100..F-149
- **Method:** static only. No Raspberry Pi. `rg`/`grep -n` citations, re-grepped before writing.
- **Date:** 2026-08-18

> Findings are appended in confirmation order. A consolidated table is at the end of
> this file under **Summary table**.

## Findings

### F-100 — `rotary_encoder.py` is a dead parallel implementation

| F-100 | medium | confirmed | cinemate | dead-code | `rotary_encoder.py` / `SimpleRotaryEncoder` never imported; superseded by `gpio_input.RotaryEncoder` | src/module/rotary_encoder.py:4 |

`src/module/rotary_encoder.py:4` defines `SimpleRotaryEncoder`. Nothing in the repo imports
`module.rotary_encoder` or references `SimpleRotaryEncoder` — a repo-wide grep for
`rotary_encoder` outside `.git/` and `system-review/` returns only the plural config key
`rotary_encoders` (`settings.jsonc:290`, `src/module/config_loader.py:374`,
`src/module/gpio_input.py:101`, `settings.schema.json:276`) and a logger colour entry
`src/module/logger.py:32`. The live implementation is `class RotaryEncoder` at
`src/module/gpio_input.py:616`, constructed at `src/module/gpio_input.py:113` from the
`rotary_encoders` config list.

The two have **drifted**: the dead one hardcodes method names as
`getattr(self.cinepi_controller, f"inc_{self.setting}")` (`src/module/rotary_encoder.py:19`,
`:23`), while the live one takes an `actions` dict from settings
(`src/module/gpio_input.py:617`) and routes through the settings-driven action dispatch.
The dead file's contract (`inc_*`/`dec_*` naming) no longer matches how the project
configures encoders, so it is not a usable fallback. Note the logger colour key
`'rotary_encoder'` at `src/module/logger.py:32` is a separate, also-unused entry — no
`logging.getLogger('rotary_encoder')` exists anywhere.

**Action:** delete `src/module/rotary_encoder.py` (24 LOC). **Risk:** none observed; no
importer, no `importlib`/`getattr` module-name construction anywhere in `src/` (see F-1xx
dynamic-import audit below). **Needs Pi:** no.

### F-101 — Compiled bytecode committed to git, including for a module that no longer exists

| F-101 | medium | confirmed | cinemate | redundancy | 5 `.pyc` files committed to git despite `.gitignore`; one is for a deleted `adc` module | src/module/__pycache__/adc.cpython-39.pyc |

`git ls-files` reports five tracked bytecode files:
`src/module/__pycache__/__init__.cpython-39.pyc`, `adc.cpython-39.pyc`,
`framebuffer.cpython-39.pyc`, `keyboard.cpython-39.pyc`, `simple_gui.cpython-39.pyc`.
`.gitignore` ignores `__pycache__/` at `.gitignore:2`, `.gitignore:180` and
`.gitignore:205`, and `*.pyc` at `.gitignore:183` — i.e. the rule exists three times over
and these files predate it, so `.gitignore` cannot evict them (`git rm --cached` is
required).

Two of the five are bytecode for modules that are dead or gone:

- `adc.cpython-39.pyc` — there is **no** `src/module/adc.py`; `find src -name 'adc*.py'`
  returns nothing. The ADC code now lives at `src/module/grove_base_hat_adc.py`. This is
  stale bytecode for a module deleted at some earlier point.
- `keyboard.cpython-39.pyc` — bytecode for `src/module/keyboard.py`, already confirmed dead
  as **F-031**.

Committed `.pyc` for a *missing* source file is worse than clutter: on a Python 3.9 target
(the Pi's system Python for this project, given the `cpython-39` tag), a stale
`__pycache__` entry whose source is absent is normally ignored by the import system, but
it advertises a module name that no longer exists to anyone reading the tree, and it makes
`grep`-based dead-code analysis produce false positives. It also means the repo ships
binary artifacts that differ per build and dirty every `git status` on a Pi that has run
the code.

**Action:** `git rm --cached -r src/module/__pycache__` and let `.gitignore` do the rest;
optionally collapse the three duplicate `__pycache__/` rules in `.gitignore`.
**Risk:** none — bytecode is regenerated on import. **Needs Pi:** no.

### F-102 — Six of `Mediator`'s thirteen methods are unreachable

| F-102 | medium | confirmed | cinemate | dead-code | 6/13 `Mediator` methods have no subscriber and no caller | src/module/mediator.py:34 |

`Mediator` is live: instantiated at `src/main.py:941`. But it wires only four handlers, all
in `__init__` (`src/module/mediator.py:19-22`):
`handle_cinepi_message`, `handle_redis_event`, `handle_fps_change`, `handle_shutter_a_change`.
A repo-wide grep for `.subscribe(` (all 17 call sites) confirms no other code subscribes a
`Mediator` method, and no code calls one directly. The following are therefore unreachable:

| Method | Def line | Why dead |
|---|---|---|
| `load_ssd_settings` | src/module/mediator.py:34 | No caller anywhere. Reads `system.storage.recognized_ssds` from a JSON path never supplied. |
| `handle_ssd_event` | src/module/mediator.py:48 | No caller; not subscribed to `ssd_monitor` |
| `handle_ssd_unmount` | src/module/mediator.py:55 | No caller; not subscribed |
| `recording_stop` | src/module/mediator.py:59 | Only caller is `handle_ssd_unmount` at src/module/mediator.py:57, itself dead |
| `handle_write_status_change` | src/module/mediator.py:66 | No caller; not subscribed |
| `handle_stop_recording_timeout` | src/module/mediator.py:159 | Only reference is the `threading.Timer` built inside `handle_write_status_change` at src/module/mediator.py:72, itself dead |

Note `handle_ssd_unmount` → `recording_stop` and `handle_write_status_change` →
`handle_stop_recording_timeout` are two-node dead subgraphs, so a naive "is this name
mentioned anywhere?" check would wrongly clear four of the six. Also note `ssd_monitor`'s
real subscribers are elsewhere and use a different event
(`self.ssd_monitor.mount_event.subscribe(...)` at `src/module/cinepi_controller.py:146` and
`src/module/storage_preroll.py:59`) — SSD handling migrated out of the mediator and the
mediator's copies were never removed.

`load_ssd_settings` is additionally stale in a second way: it reads a
`system.storage.recognized_ssds` settings path. Whether that key still exists in
`settings.jsonc` is Agent 2's scope (dead config keys), but it is worth cross-checking —
if the key is also gone, both halves of the feature are orphaned.

**Action:** delete the six methods (~55 LOC). **Risk:** low, but confirm on a Pi that no
out-of-tree script constructs a `Mediator` and calls these — see queue entry below.
**Needs Pi:** no for the deletion decision; the grep is complete within the repo.

### F-103 — `Mediator` stores two constructor arguments it never reads

| F-103 | low | confirmed | cinemate | dead-code | `self.usb_monitor` and `self.redis_listener` assigned but never used | src/module/mediator.py:11 |

`Mediator.__init__` takes eight collaborators (`src/module/mediator.py:8`). Grepping each
`self.<attr>` across the 177-line file:

- `self.redis_listener` — assigned at `src/module/mediator.py:11`, **zero** other references.
- `self.usb_monitor` — assigned at `src/module/mediator.py:16`, **zero** other references.

Both are passed positionally from `src/main.py:941`. This is a false coupling: it makes
`Mediator` look like it participates in USB and redis-listener flows when it does not, and
it forces `main.py` to have both objects constructed before the mediator for no reason.

**Action:** drop both parameters from the signature and the `main.py:941` call.
**Risk:** none — purely additive removal. **Needs Pi:** no.

### F-104 — Permanently-false `hasattr` guard hides a lost feature (`toggle_background_color`)

| F-104 | medium | confirmed | cinemate | dead-code | `hasattr(self.stream, "toggle_background_color")` can never be true; branch is unreachable | src/module/mediator.py:151 |

`src/module/mediator.py:151`:

```python
if self._is_writing and hasattr(self.stream, "toggle_background_color"):
    try:
        self.stream.toggle_background_color()
```

`self.stream` is assigned from the eighth constructor argument (`src/module/mediator.py:15`).
Its only producer is `src/main.py:941`, which passes the local `stream` — and that local is
initialised to `None` at `src/main.py:929` and, when a network is present, rebound at
`src/main.py:935` to a plain `threading.Thread` wrapping `socketio.run`. Neither `None` nor
`threading.Thread` has a `toggle_background_color` attribute.

`toggle_background_color` is **not defined anywhere in the repository**. A repo-wide grep
(excluding `.git/`) returns exactly three hits, all *call* or *guard* sites and no `def`:
`src/module/mediator.py:151`, `src/module/mediator.py:153`, and `_test/_mediator.py:91`.

So the guard at `src/module/mediator.py:151` is unconditionally false and lines 152-155 are
unreachable. This is drift, not merely clutter: `stream` used to be an object with this
method (consistent with the now-dead `src/stream.py`, **F-013**), and when `main.py` changed
to hand over a raw `Thread`, the defensive `hasattr` turned a would-be `AttributeError`
into silence. The "flash the preview background while writing" behaviour is gone and nothing
reports it. The `try/except Exception` at `src/module/mediator.py:152`/`:154` is a second
layer of the same silencing.

**Action:** either delete lines 151-155, or restore the feature by passing the object that
actually owns the framebuffer (`simple_gui`) instead of the thread. Do not leave the
`hasattr` — it is the reason the regression is invisible.
**Risk:** deleting is behaviour-preserving (the branch never runs today).
**Needs Pi:** no to confirm it is dead — the type of `stream` is fixed in `main.py`. Yes to
confirm the *user-visible* consequence (does the preview still indicate writing by some
other path, e.g. `gpio_output.set_rec_light` at `src/module/mediator.py:89`?).

### F-105 — `usb_monitor.py` opens four ad-hoc Redis connections instead of reusing `RedisController`

| F-105 | medium | confirmed | cinemate | redundancy | Four independent `StrictRedis` clients with hardcoded `localhost:6379`, bypassing `RedisController` | src/module/usb_monitor.py:141 |

**Correction to the brief:** the target described these as bypassing "the injected
controller". There is no injected controller to bypass — `USBMonitor` is constructed at
`src/main.py:611` as `USBMonitor(ssd_monitor, settings=settings)` and never receives a
`RedisController`. The finding is real but the shape is different: `usb_monitor.py`
re-implements Redis access from scratch because it was never wired to the object that owns it.

Four call sites each do a local `import redis` and build their own client:

| Site | Function | Line of `StrictRedis(...)` |
|---|---|---|
| `_refresh_capture_gain_from_redis` | src/module/usb_monitor.py:134 | src/module/usb_monitor.py:141 |
| `publish_mic_selection` | src/module/usb_monitor.py:433 | src/module/usb_monitor.py:439 |
| `clear_mic_selection` | src/module/usb_monitor.py:454 | src/module/usb_monitor.py:458 |
| `_is_recording_active` | src/module/usb_monitor.py:574 | src/module/usb_monitor.py:581 |

All four hardcode `host="localhost", port=6379, db=0`. `RedisController.__init__`
(`src/module/redis_controller.py:162`) takes `host`, `port`, `db` as parameters and builds
its single client at `src/module/redis_controller.py:163`. Today the sole production
construction (`src/main.py:608`) uses the defaults, so the endpoints agree — but the
parameterisation exists, and the moment anyone uses it, audio silently detaches from the
rest of the system while every other consumer follows. The failure mode is quiet by
construction: all four sites swallow `Exception` into `logging.debug` (e.g.
`src/module/usb_monitor.py:143-145`, `:452`, `:465`), so a wrong endpoint produces no
visible error, just permanently-default capture gain and no `MIC_*` publication.

**Connection churn during a take.** `_is_recording_active` (`src/module/usb_monitor.py:574`)
builds a fresh TCP connection on every call and never closes it. Its caller is the nested
`run()` at `src/module/usb_monitor.py:605`, invoked at `src/module/usb_monitor.py:609`; when
recording *is* active, `run()` re-arms itself at `src/module/usb_monitor.py:615` with
`delay_seconds=1.0`. So while a take is rolling, this creates **one new Redis connection per
second, indefinitely**, relying on GC to reap the sockets. That is precisely the window in
which the system should be doing least work. `redis-py` clients are connection-pooled and
designed to be long-lived and shared; constructing one per poll defeats the pool entirely.

**Action:** inject the existing `RedisController` into `USBMonitor`/`AudioMonitor` (or at
minimum hoist a single module-level client) and read `redis_controller.r`. **Risk:** low;
the read/write semantics are identical. **Needs Pi:** no to confirm the code shape — the
call graph is static and complete. **Yes** to quantify the churn: on a Pi, run
`redis-cli info clients` and `ss -tn state established '( dport = :6379 )' | wc -l` during a
60-second take and confirm the connection count climbs roughly linearly, then stays flat
after the fix.

### F-106 — Redis key strings duplicated outside `ParameterKey`

| F-106 | medium | confirmed | cinemate | redundancy | `CAPTURE_GAIN_REDIS_KEY` re-declares an existing `ParameterKey`; `"is_recording"` used as a bare literal | src/module/usb_monitor.py:14 |

`src/module/redis_controller.py` defines the `ParameterKey` enum as the single registry of
Redis key names. Two entries are shadowed by hand-written duplicates in `usb_monitor.py`:

- `src/module/usb_monitor.py:14` — `CAPTURE_GAIN_REDIS_KEY = "audio_capture_gain_db"`.
  The same string is already `ParameterKey.AUDIO_CAPTURE_GAIN_DB` at
  `src/module/redis_controller.py:19`. Two independent literals for one key; renaming the
  enum member updates every other consumer and silently leaves audio gain reading the old
  name.
- `src/module/usb_monitor.py:582` — `client.get("is_recording")` as a bare string, where
  `ParameterKey.IS_RECORDING = "is_recording"` exists at `src/module/redis_controller.py:45`
  and is used properly elsewhere, e.g. `src/module/redis_controller.py:200`.

This is a lower bound — only key strings that happen to match an enum *value* are visible to
grep, and keys assembled at runtime are not. At least these two.

**Action:** import `ParameterKey` in `usb_monitor.py` and delete the local constant.
**Risk:** none — the string values are identical today, verified by inspection of both
definitions. **Needs Pi:** no.

### F-107 — `MIC_*` Redis keys are written and deleted by cinemate but read by nothing in cinemate

| F-107 | low | probable | cinemate | dead-code | Five `MIC_*` keys published/cleared with no in-repo reader | src/module/usb_monitor.py:441 |

`publish_mic_selection` writes five keys in one `mset` (`src/module/usb_monitor.py:441-445`):
`MIC_PCM_ALIAS`, `MIC_FORMAT`, `MIC_CHANNELS`, `MIC_RATE`, `MIC_CARD_NAME`.
`clear_mic_selection` deletes exactly those five (`src/module/usb_monitor.py:459`).

A repo-wide grep for all five names (excluding `.git/` and `system-review/`) returns **only**
those two sites. Nothing in cinemate ever reads them.

**Why this is `probable`, not `confirmed`:** the plausible reader is the sibling repo
cinepi-raw, which shares this Redis instance — `src/module/usb_monitor.py:520` says outright
"VU is expected from cinepi-raw Redis", establishing that cross-process Redis contracts are
how these two components talk. If cinepi-raw reads `MIC_*`, this is a legitimate
cross-repo interface that merely lacks documentation on the cinemate side. If it does not,
~15 lines of publish/clear machinery plus a per-call Redis connection are pure waste.

**Blocks / handoff:** this cannot be settled inside my scope. **Agent 3 (cinepi-raw,
F-200..F-249)**: please grep cinepi-raw for `MIC_PCM_ALIAS` (the most distinctive of the
five) and record the answer. If cinepi-raw has no reader either, promote this to
`confirmed` dead-code. **Needs Pi:** no — a grep of the other repo settles it. A Pi check
(`redis-cli keys 'MIC_*'` then `redis-cli monitor | grep MIC_` while plugging a USB mic)
would show whether anything subscribes in practice.

### F-108 — `SSDMonitor.stop()` is never called and contains a latent `AttributeError`

| F-108 | high | confirmed | cinemate | dead-code | `SSDMonitor.stop()` has no caller; its body would raise `AttributeError` on `self._jthread` if it did | src/module/ssd_monitor.py:155 |

Two defects that mask each other.

**(a) `stop()` is dead.** `SSDMonitor.stop` is defined at `src/module/ssd_monitor.py:152`.
A repo-wide grep for `ssd_monitor.stop` across `src/` returns no call site. The shutdown
path is `cleanup()` at `src/main.py:954`, registered via `atexit.register(cleanup)` at
`src/main.py:1035`; it stops `dmesg_monitor` (`src/main.py:984`), `command_executor`
(`:986`), `status_broadcaster` (`:988`), `serial_handler` (`:1005`), `i2c_oled` (`:1012`)
and `quad_rotary` (`:1016`) — **but never `ssd_monitor`**. So `self._stop_evt` is never set
and the SSD monitoring thread is never joined on exit.

**(b) If it were called, it would raise.** `src/module/ssd_monitor.py:155` is
`self._jthread.join()`. Every reference to `_jthread` in the file is:

```
140:        # self._jthread = threading.Thread(
143:        # self._jthread.start()
155:        self._jthread.join()
```

The only assignment is inside the commented-out block at `src/module/ssd_monitor.py:140-144`.
`self._jthread` is therefore never set on any code path, and `stop()` would raise
`AttributeError: 'SSDMonitor' object has no attribute '_jthread'` immediately after
`self._thread.join()` at `src/module/ssd_monitor.py:154` — i.e. after signalling the stop
but before `logging.info("SSD monitoring stopped.")` at `:156`.

Severity is **high** rather than medium because of the interaction: the natural fix for (a)
is "add `ssd_monitor.stop()` to `cleanup()`", and doing that alone converts a silent
omission into a raising `atexit` handler on every shutdown — during the exact window when
the storage device is being released. Anyone fixing one without seeing the other makes it
worse. Fix (b) first: delete `src/module/ssd_monitor.py:155`.

**Needs Pi:** no to confirm either half — both are settled by grep over a closed call
graph. **Yes** to confirm the consequence of (a): on a Pi, `systemctl stop cinemate` and
check with `journalctl -u cinemate` whether the SSD thread outlives the process or the unit
hangs until its stop timeout.

### F-109 — `SSDMonitor._journal_loop` (70 LOC) is dead, and keeps a system dependency alive

| F-109 | medium | confirmed | cinemate | dead-code | 70-line `_journal_loop` unreachable; sole reference is a commented-out thread target | src/module/ssd_monitor.py:1254 |

`_journal_loop` is defined at `src/module/ssd_monitor.py:1254` and runs to the end of the
file (`src/module/ssd_monitor.py` is 1323 lines), making it ~70 LOC and the file's last
method. Its only reference anywhere is the commented-out `target=self._journal_loop` at
`src/module/ssd_monitor.py:141`. Nothing else calls it.

The dead function keeps two things alive that would otherwise be removable:

- the guarded `from systemd import journal` at `src/module/ssd_monitor.py:14` and the
  `_HAVE_JOURNAL` flag set at `:15`/`:17`, whose only consumer is `src/module/ssd_monitor.py:1304`
  — inside the dead function;
- the `python3-systemd` apt package, installed by `cinemate-install.sh:523`. With
  `_journal_loop` dead, nothing in `src/` imports `systemd` for any live purpose.

That last point is **cross-scope**: **Agent 2 (F-150..F-199)** already has "7 unused
installer packages" (F-032) — `python3-systemd` at `cinemate-install.sh:523` is a candidate
for that list, contingent on this finding. Worth confirming there is no other importer of
`systemd` outside `src/` (e.g. in `services/`) before removing the package.

**Action:** delete `_journal_loop`, the `try`/`except` import at
`src/module/ssd_monitor.py:14-17`, and the commented block at `:139-144`.
**Needs Pi:** no.

### F-110 — Vestigial `timekeeper` guard in `main.py` is permanently false

| F-110 | low | confirmed | cinemate | dead-code | `timekeeper` is set to `None` and never reassigned; the shutdown guard can never fire | src/main.py:658 |

`main.py` does not import `module.timekeeper` at all — it is absent from the import block at
`src/main.py:16-47`. Every mention of the name in the file is:

```
658:    timekeeper = None
1026:        if timekeeper and hasattr(timekeeper, "stop"):
1027:            timekeeper.stop()
```

`timekeeper` is initialised to `None` at `src/main.py:658` and never reassigned, so the
guard at `src/main.py:1026` is unconditionally false and `src/main.py:1027` is unreachable.

This is the leftover socket of the already-confirmed dead module **F-017**
(`src/module/timekeeper.py`, 243 LOC). Note the belt-and-braces `hasattr(timekeeper, "stop")`
here is the same defensive idiom as **F-104** — in both places a `hasattr` guard is what
converts "this feature was removed" into "this code appears to still handle the feature".
When F-017 is actioned, these three lines must go with it, or `timekeeper.py` will look
re-addable.

**Action:** delete `src/main.py:658` and `src/main.py:1026-1027` alongside F-017.
**Needs Pi:** no.

### F-111 — Commented-out code blocks across `src/` (at least 8 sites, ~90 lines)

| F-111 | low | confirmed | cinemate | readability | At least 8 multi-line commented-out code blocks, two of them file-tail dumps | src/module/framebuffer.py:173 |

Scanning `src/` for runs of >=6 consecutive comment lines of which >=3 parse as code:

| Site | Lines | What it is |
|---|---|---|
| src/module/framebuffer.py:173-194 | 22 | Whole `if __name__ == "__main__":` FPS test harness, commented out at file tail (file is 194 lines) |
| src/module/simple_gui.py:763-785 | 23 | Shutter-angle "nominal + exposure fraction" display, entire feature |
| src/module/simple_gui.py:2120-2129 | 10 | File-tail dump — see below |
| src/module/simple_gui.py:1367-1377 | 11 | `write_speed` box rendering |
| src/module/framebuffer.py:98-107 | 10 | A second, alternate `Framebuffer.__init__` reading `/sys/class/graphics` |
| src/module/redis_listener.py:1110-1119 | 10 | Auto-FPS adjustment from rolling average framerate |
| src/module/ssd_monitor.py:139-146 | 8 | The journal-listener thread — see F-108, F-109 |
| src/module/cinepi_controller.py:2033-2040 | 8 | An `if`/`else` whose guard was commented but body kept — see F-112 |

This is a lower bound: the heuristic requires six consecutive lines and misses shorter
blocks and interleaved ones.

Two deserve individual mention.

**`src/module/simple_gui.py:2120-2129`** is the last 10 lines of a 2129-line file and is not
a coherent block at all. It contains a commented duplicate of `emit_gui_data_change`
(`src/module/simple_gui.py:2120`) whose live twin is defined at
`src/module/simple_gui.py:313` and used at `src/module/simple_gui.py:1772`; and then, at
column 0 with indentation that could never have compiled inside the class, an FSCK snippet
(`src/module/simple_gui.py:2123-2129`) calling `redis.get_value(...)`, `show_red_icon`,
`show_green_icon`, `show_gray_icon` — none of which exist anywhere in `src/`. It is paste
residue, not a disabled feature.

**`src/module/framebuffer.py:98-107`** is a genuine parallel-implementation hazard: a second
`__init__` for the same class, sitting directly above the live one, differing in how it
derives `size`/`stride`/`bits_per_pixel`. A reader cannot tell which is current without
running it.

**Action:** delete all eight. Any that represent wanted-but-unfinished features
(`redis_listener.py:1110-1119` auto-FPS; `simple_gui.py:763-785` shutter display) should
become issues, not comments — as comments they rot silently, which is exactly what happened
to `simple_gui.py:777`'s reference to `exposure_time_fractions` while the live attribute
moved on (`src/module/cinepi_controller.py:1003`, `:2099`).
**Needs Pi:** no.

### F-112 — A commented-out `if` left its body live, silently changing behaviour

| F-112 | high | confirmed | cinemate | correctness | Guard `if self.ssd_monitor.is_mounted:` commented out; body now runs unconditionally and the CFE-HAT branch calls a method that does not exist | src/module/cinepi_controller.py:2033 |

`src/module/cinepi_controller.py:2033-2040` (the body of `def unmount` at `src/module/cinepi_controller.py:2032`):

```python
        # if self.ssd_monitor.is_mounted:
        self.ssd_monitor.unmount_drive()
        # else:
        #     if self.ssd_monitor.cfe_hat_present:
        #         logging.info("No drive currently mounted. CFE HAT detected — attempting to mount CFE...")
        #         self.ssd_monitor.mount_cfe()
        #     else:
        #         logging.info("No drive currently mounted and no CFE HAT present. Nothing to do.")
```

This is not dormant code — it is *active* code whose guard was removed. Two consequences:

1. `unmount_drive()` is now invoked **unconditionally**, including when no drive is mounted.
   `is_mounted` is a real live property (`def is_mounted` at
   `src/module/ssd_monitor.py:162`), so the check was meaningful.
2. The entire CFE-HAT auto-mount path is gone — and it could not be restored by simply
   uncommenting. `cfe_hat_present` is real (`@property` at `src/module/ssd_monitor.py:208`,
   backed by `self._cfe_hat_present = self._detect_cfe_hat()` at `src/module/ssd_monitor.py:147`),
   but **`mount_cfe` does not exist anywhere in the repository** — a repo-wide grep for
   `mount_cfe` excluding `.git/` returns exactly one hit, the commented call itself at
   `src/module/cinepi_controller.py:2038`. So the commented `else` branch is not a disabled
   feature that can be switched back on; it references a method that was deleted (or never
   written). Restoring it verbatim would raise `AttributeError`.

Severity **high**: this sits on the storage-mount path of a camera, the code reads as if the
guard is still there (the `# if` is the first line, so a skimming reader sees a conditional),
and the behaviour change is invisible in `git blame` terms to anyone reading the current file.

**Whether the unconditional call is harmful is `unverified` and needs a Pi**: it depends on
whether `SSDMonitor.unmount_drive()` (`src/module/ssd_monitor.py:853`) is a no-op when
nothing is mounted or whether it shells out to `umount` and logs an error. **Pi test:** with
no SSD attached, invoke `CinePiController.unmount` (`src/module/cinepi_controller.py:2032`)
and watch `journalctl -u cinemate` for `umount` failures. Either way the source should say what it means — restore the guard or
delete the dead `else`.

### F-113 — `FSCK_STATUS` is written three times and read by nothing

| F-113 | medium | confirmed | cinemate | dead-code | fsck result published to Redis but no live consumer; only reader is a commented-out GUI snippet | src/module/ssd_monitor.py:44 |

`REDIS_KEY_FSCK_STATUS = "FSCK_STATUS"` is defined at `src/module/ssd_monitor.py:44` with the
comment `# "OK …" | "FAIL …"`, and written on three paths:
`src/module/ssd_monitor.py:260` (initialised to `"unknown"`),
`src/module/ssd_monitor.py:804`, and `src/module/ssd_monitor.py:816`.

A repo-wide grep for `FSCK_STATUS` (excluding `.git/` and `system-review/`) finds exactly one
would-be reader — and it is commented out: `src/module/simple_gui.py:2123`, inside the
paste-residue block described in F-111. The key is not in the `ParameterKey` enum
(`src/module/redis_controller.py`), so it is not exposed through the normal parameter
plumbing to the web API or the settings editor either.

So a filesystem-check result — genuinely useful, exactly the kind of thing an operator wants
before a shoot — is computed, formatted into an `"OK …"`/`"FAIL …"` message, stored, and then
read by nobody. The intended consumer (a red/green/grey icon in the GUI) exists only as the
dead snippet at `src/module/simple_gui.py:2123-2129`.

**This is the more interesting reading of the evidence than "delete the writes":** the writes
are cheap and correct; what is missing is the display. Recommend surfacing `FSCK_STATUS`
rather than removing it — add it to `ParameterKey` so it rides the existing
`redis_parameter_changed` path already subscribed by the GUI at
`src/module/simple_gui.py:222`.

**Caveat (why not `probable`):** as with F-107, cinepi-raw shares this Redis instance and
could in principle read the key. I mark this `confirmed` for *cinemate* specifically —
the claim "no cinemate code reads it" is fully settled by grep. **Agent 3**: a grep of
cinepi-raw for `FSCK_STATUS` would close the remaining gap.
**Needs Pi:** no.

### F-114 — Two parallel VU-meter implementations; the `arecord` one is fully dead

| F-114 | medium | confirmed | cinemate | redundancy | Superseded `arecord -vvv` VU path still present alongside the live Redis `audio_vu` path | src/module/usb_monitor.py:467 |

VU metering has been reimplemented and the old implementation was never removed. Both halves
are still in the tree.

**Live path** — `simple_gui` reads a Redis key published by cinepi-raw:
`RECORDER_VU_REDIS_KEY = "audio_vu"` (`src/module/simple_gui.py:21`),
read in `_get_recorder_vu_levels` (`src/module/simple_gui.py:1166`, key fetched at
`src/module/simple_gui.py:1172`), smoothed by `update_smoothed_vu_levels`
(`src/module/simple_gui.py:1184`, called at `src/module/simple_gui.py:2108`) and drawn by
`draw_right_vu_meter` (`src/module/simple_gui.py:1463`, called at
`src/module/simple_gui.py:1924`).

**Dead path** — `AudioMonitor` shells out to `arecord -vvv` and scrapes stderr:

| Symbol | Location | Status |
|---|---|---|
| `vu_monitor_loop` | src/module/usb_monitor.py:467 | no caller anywhere in the repo |
| `get_vu_levels` | src/module/usb_monitor.py:535 | no caller anywhere in the repo |
| `self.vu_levels` | src/module/usb_monitor.py:113 | written at `:478`, `:491`, `:493`, `:532`; read only by the two dead methods above |
| `self.vu_history` | src/module/usb_monitor.py:116 | appended at `src/module/usb_monitor.py:494`; never read |
| `handle_vu_output` | src/main.py:633 | already **F-018**; its subscription is commented out at `src/main.py:743` |

Two comments in the source state the migration outright, which is what raises this from
"suspicious" to confirmed:

- `src/module/usb_monitor.py:520` — `"AudioMonitor prepared hardware params; VU is expected
  from cinepi-raw Redis."`
- `src/module/simple_gui.py:1935` — `vu = self.vu_smoothed  # Or .usb_monitor.audio_monitor.vu_levels if you want raw`

The second is the clearest signal: it names the dead attribute as the alternative source,
so a future maintainer is actively invited to re-adopt the abandoned path.

`self.vu_history` (`src/module/usb_monitor.py:116`) is worth separate note — it is a
`deque(maxlen=10)` that is appended to on every parsed line and never read by anything. Pure
accumulation.

**Related, same feature:** `cinepi_multi.py` still carries `'vu': re.compile(r'\[VU\]')` in
`self.log_filters` (`src/module/cinepi_multi.py:218`). Unlike the above this is *live* — the
dict is iterated at `src/module/cinepi_multi.py:264` and gated on `self.active_filters` at
`:265` — so it currently suppresses `[VU]` log lines from cinepi-raw. Keep it, or drop it
deliberately, but it should be decided together with F-018.

**Action:** delete `vu_monitor_loop`, `get_vu_levels`, `self.vu_levels`, `self.vu_history`
and their write sites, together with F-018. **Risk:** low — nothing reads them.
**Needs Pi:** no for the deletion. **Yes** to confirm the live path is genuinely the only
one working: on a Pi with a USB mic, confirm `redis-cli get audio_vu` changes while
recording and that the on-screen meter moves.

### F-115 — `USBDriveMonitor` class (67 LOC) is never instantiated

| F-115 | medium | confirmed | cinemate | dead-code | Entire `USBDriveMonitor` class unreferenced outside its own definition | src/module/usb_monitor.py:33 |

`class USBDriveMonitor` is defined at `src/module/usb_monitor.py:33` and spans to
`src/module/usb_monitor.py:99` (the next class, `AudioMonitor`, begins at
`src/module/usb_monitor.py:100`) — roughly 67 LOC.

A repo-wide grep for `USBDriveMonitor`, excluding `.git/` and `system-review/`, returns
**exactly one hit: the `class` statement itself**. It is never instantiated, never imported,
never named in `settings.jsonc`, docs or templates. `main.py` imports and constructs only
`USBMonitor` (`src/main.py:20`, `src/main.py:611`), a different class defined at
`src/module/usb_monitor.py:538`.

Its method `start_monitoring` (`src/module/usb_monitor.py:79`) is likewise uncalled — note
this is *not* the same symbol as `DmesgMonitor._start_monitoring`
(`src/module/dmesg_monitor.py:61`, called at `src/module/dmesg_monitor.py:22`), which is
live; the near-identical names are a trap for a careless grep.

The class is a drifted parallel implementation of drive hot-plug detection, not merely an
unused helper. It runs its own `pyudev` monitor on `subsystem='block'`
(`src/module/usb_monitor.py:37`) and drives `SSDMonitor` directly via
`self.ssd_monitor.update_on_add(...)` at `src/module/usb_monitor.py:76` and
`src/module/usb_monitor.py:93`, polling at `src/module/usb_monitor.py:80`. The live
`USBMonitor` filters different subsystems entirely — `'sound'`, `'usb'` and `'usb_storage'`
at `src/module/usb_monitor.py:551`, `:552` and `:571`. So the dead class watches `block`
devices, a scope nothing in the live path covers; anyone reading the file could reasonably
conclude block-device hot-plug is handled when it is not.

**Action:** delete the class. **Risk:** low — confirm first that nothing outside this repo
imports `module.usb_monitor.USBDriveMonitor` (nothing inside does). **Needs Pi:** no.

### F-116 — Six uncalled single-field accessors in `sensor_detect.py`, one of them a superseded duplicate

| F-116 | medium | confirmed | cinemate | redundancy | 6 wrapper accessors around `get_resolution_info` never called; `get_packing` is silently wrong on Pi 4 | src/module/sensor_detect.py:616 |

`SensorDetect` exposes seven near-identical one-line wrappers, each calling
`get_resolution_info(camera_name, sensor_mode)` and returning a single field. Six have **no
caller anywhere in the repository** (verified against a 4.6 MB corpus covering `src/`,
`settings.jsonc`, `resources/`, `docs/`, `services/`, `_test/` and the HTML templates; the
same corpus shows a known settings-driven method such as `set_zoom` with 19 hits, so the
method is sound):

| Method | Line | Field returned |
|---|---|---|
| `get_sensor_resolution` | src/module/sensor_detect.py:571 | whole mode dict from `res_modes` |
| `get_width` | src/module/sensor_detect.py:604 | `width` |
| `get_height` | src/module/sensor_detect.py:608 | `height` |
| `get_bit_depth` | src/module/sensor_detect.py:612 | `bit_depth` |
| `get_packing` | src/module/sensor_detect.py:616 | `packing` |
| `get_file_size` | src/module/sensor_detect.py:809 | `file_size` |
| `get_hdr` | src/module/sensor_detect.py:840 | `hdr` |

(That is seven rows; `get_sensor_resolution` is the odd one out, wrapping `self.res_modes`
directly rather than `get_resolution_info`.)

The reason they are unused is that every real caller fetches the dict once and indexes it,
which is strictly better — one lookup instead of N. Live examples:
`src/module/cinepi_controller.py:651` (`resolution_info.get('bit_depth')`),
`src/module/cinepi_controller.py:1551`, `src/module/cinepi_controller.py:1623`,
`src/module/cinepi_multi.py:355`, `src/module/cinepi_multi.py:773`,
`src/module/simple_gui.py:1016`.

**`get_packing` is the one that matters.** It is not merely unused — it is a *wrong* answer
kept next to the right one. `get_packing_for_platform`
(`src/module/sensor_detect.py:620`) resolves packing through
`packing_by_platform[platform]` in `sensors.json` and auto-detects Pi 4 vs Pi 5 when
`is_pi4` is omitted, per its docstring at `src/module/sensor_detect.py:621-633`. It is the
live one — called at `src/module/cinepi_controller.py:1554`,
`src/module/cinepi_multi.py:363` and `src/module/cinepi_multi.py:775` — and
`src/module/cinepi_multi.py:40-43` documents it as "the single canonical implementation".
`get_packing`, four lines above it, ignores the platform entirely and returns the raw
`packing` field. The two sit adjacent with a four-line gap and near-identical names; picking
the shorter one gives packed/unpacked wrong on Pi 4 hardware, and the failure would appear
as corrupt DNG data, not an exception.

**Action:** delete all six (~20 LOC). If any are wanted as public API, keep only
`get_packing_for_platform` and rename it to `get_packing` so the wrong choice is unavailable.
**Risk:** low — no callers. **Needs Pi:** no to delete. The Pi-4 packing consequence is
already documented in the codebase's own comments, so no hardware test is needed to justify
removal; it would only be needed to demonstrate the bug, which is not worth doing.

### F-117 — The 46-entry action catalogue exists twice, hand-synced, and the validating endpoint is unused

| F-117 | high | confirmed | cinemate | redundancy | `ACTION_METHODS` duplicated verbatim in Python and JS; `GET /api/actions`, the only thing that validates it, has no consumer | src/module/app/settings_editor.py:63 |

The list of controller actions the settings editor offers is maintained **twice**, in two
languages, with no generation step between them:

- Python: `ACTION_METHODS = [` at `src/module/app/settings_editor.py:63`
- JavaScript: `var ACTION_METHODS = [` at `src/module/app/templates/settings_editor.html:3261`

I extracted the `value` field from both. **46 entries each, same set, same order** — a
verbatim transliteration. Any new action must be added in both places, in the same position,
or the UI and the API disagree.

Worse, the two are not actually peers. The Python copy has exactly one consumer:
`get_actions()` at `src/module/app/settings_editor.py:293`, serving
`GET /api/actions` (route declared at `src/module/app/settings_editor.py:292`). A repo-wide
grep for the string `api/actions`, excluding `.git/` and `system-review/`, returns **exactly
one hit — the route declaration itself**. The template never fetches it; it builds its
dropdown from its own hardcoded copy (`ACTION_METHOD_MAP` at
`src/module/app/templates/settings_editor.html:3310`, consumed by `buildActionMethodSelect`
at `:3312` and the loop at `:3318`).

So the Python catalogue and the endpoint are dead weight, and the browser runs on the
unvalidated duplicate.

**This is not hypothetical — the duplication has already produced a bug.** `get_actions()`
computes an `available` flag per entry (`src/module/app/settings_editor.py:295-301`) by
reflecting over the live controller with `_public_method_names`
(`src/module/app/settings_editor.py:115`). That check exists precisely to catch catalogue
entries that no longer resolve. Because nothing consumes its output, it has caught nothing.
See F-118.

**Action:** delete the JS copy and have the template fetch `GET /api/actions`, making the
Python list the single source and turning the existing `available` flag into a live guard.
That removes ~46 duplicated lines from the template and gives the reflection an audience.
**Risk:** medium — this changes page load to depend on an API round-trip; the dropdown must
handle the fetch failing. **Needs Pi:** no to confirm the duplication (pure text comparison).
**Yes** to validate the fix: load the settings editor in a browser against a running Pi and
confirm the method dropdown still populates and that entries whose methods are missing are
visibly marked or omitted.

### F-118 — `ACTION_METHODS` offers `set_log`, which is not a controller method

| F-118 | high | confirmed | cinemate | correctness | Catalogue entry `set_log` resolves to nothing; the real method is `set_log_encode` | src/module/app/settings_editor.py:94 |

Comparing all 46 `ACTION_METHODS` values against the method names defined on
`CinePiController` (`    def ` at class-body indentation in
`src/module/cinepi_controller.py`), exactly one has no match: **`set_log`**.

Both copies of the catalogue carry it:

- `src/module/app/settings_editor.py:94` — `{"group": "CineMate Log", "value": "set_log", "label": "Set CineMate Log target", "arg": {"type": "select", "options": ["off", "10", "12"]}}`
- `src/module/app/templates/settings_editor.html:3290` — the identical entry in JS

A repo-wide grep for `set_log` (word-boundary, excluding `.git/` and `system-review/`)
returns only those two lines. The method that actually exists is `set_log_encode` at
`src/module/cinepi_controller.py:666`.

**Consequence.** The settings editor presents "Set CineMate Log target" in its method
dropdown. A user who binds it to a button gets `"method": "set_log"` written into
`settings.jsonc`. At dispatch time the hardware layers do
`getattr(self.cinepi_controller, method_name, None)` — `src/module/gpio_input.py:263`,
`:398`, `:467`, `:551`, `:601`, `:635`, and `src/module/i2c/quad_rotary_controller.py:114` —
which returns `None` and the press silently does nothing. No exception, no log line at the
default level. The user concludes the button is broken.

This is exactly the failure mode the `available` flag in `get_actions()` was written to
prevent (`src/module/app/settings_editor.py:295-301`), and it slipped through because
nothing consumes that endpoint — see F-117. The header comment at
`src/module/app/settings_editor.py:56-62` even records that a previous pass fixed three such
entries by hand (`'erase'` → `'erase_drive'`, `'format'` → `'format_drive'`, and dropping
`'storage_preroll'`); `set_log` is a fourth instance of the same class of defect, introduced
or missed after that cleanup.

**Good news for the blast radius:** no shipped settings file uses it. I cross-checked every
`"method": "..."` string in `settings.jsonc` (12 distinct), `resources/settings/settings_default.jsonc`
(12) and `resources/settings/settings_komodo.jsonc` (13) against the controller — **all
resolve**. So the defect is confined to what the editor *offers*, not to what ships.

**Action:** change both entries to `set_log_encode`, or remove them. Then action F-117 so the
next drift is caught automatically. **Risk:** low. **Needs Pi:** no to confirm the mismatch.
**Yes** to confirm the silent-no-op behaviour end-to-end: bind a button to `set_log` on a Pi,
press it, and observe that nothing happens and nothing is logged.

### F-119 — Seven uncalled `CinePiController` methods, verified against the reflective-dispatch surface

| F-119 | medium | confirmed | cinemate | dead-code | 7 controller methods with no static caller, no `settings.jsonc` binding and no catalogue entry | src/module/cinepi_controller.py:768 |

`CinePiController` methods are frequently invoked reflectively, so "no static caller" is not
sufficient evidence. I checked each candidate against **all four** dispatch surfaces:

1. static callers in `src/`;
2. `"method": "..."` strings in `settings.jsonc` (12 distinct), `resources/settings/settings_default.jsonc` (12) and `resources/settings/settings_komodo.jsonc` (13);
3. the `ACTION_METHODS` catalogues (`src/module/app/settings_editor.py:63` and `src/module/app/templates/settings_editor.html:3261`);
4. a whole-repo text corpus (4.6 MB, all file types, excluding `.git/` and `system-review/`) — as a control, `set_zoom` scores 19 hits in this corpus and `set_iso` 15.

The following score **1** — the `def` line and nothing else:

| Method | Line | Note |
|---|---|---|
| `calculate_exposure` | src/module/cinepi_controller.py:768 | duplicate — see below |
| `load_wb_steps` | src/module/cinepi_controller.py:852 | reads `settings['arrays']['wb']['steps']` |
| `set_free_mode` | src/module/cinepi_controller.py:870 | bulk setter for the four `*_free` flags |
| `update_shutter_angle_for_fps` | src/module/cinepi_controller.py:895 | |
| `_get_current_fps` | src/module/cinepi_controller.py:1121 | private helper, never called |
| `get_current_sensor_mode` | src/module/cinepi_controller.py:1832 | non-trivial imx585 HDR-mode disambiguation |
| `set_fps_multiplier` | src/module/cinepi_controller.py:2006 | see below |

Two are more than clutter.

**`calculate_exposure` is a drifted duplicate eight lines from its twin.** It computes
`float(shutter_a_nom) / 360.0 / float(fps)` from Redis
(`src/module/cinepi_controller.py:769-771`). The live code computes the identical formula
from instance state at `src/module/cinepi_controller.py:760`:
`self.exposure_time_nominal = (self.shutter_angle_nom / 360) / self.current_fps`. Same maths,
two different sources of truth (Redis vs. in-memory attributes), adjacent in the file. If
they ever disagree — and Redis vs. instance state is exactly where they would — a maintainer
has no way to know which is authoritative.

**`set_fps_multiplier` is the setter of an attribute nothing reads.** `self.fps_multiplier`
is initialised to `1` at `src/module/cinepi_controller.py:168` and assigned at
`src/module/cinepi_controller.py:2008` inside this uncalled method. Grepping `fps_multiplier`
across `src/` returns only those three lines plus the log statement at
`src/module/cinepi_controller.py:2009`. Nothing ever reads the value. The entire feature —
attribute, lock-protected setter and log line — is inert.

**`get_current_sensor_mode` is the one to think about before deleting.** Unlike the others it
carries real domain knowledge (the comment beginning at `src/module/cinepi_controller.py:1840`
explains that height alone is ambiguous on the imx585 because the 12-bit HDR modes share
dimensions with the plain 12-bit and the 16-bit HDR modes, so a height-only match used to
select the wrong sibling). Deleting it discards that reasoning. Either keep it with a note saying why it is
retained, or make sure the equivalent logic exists on the live path before removing it.

**Action:** delete `calculate_exposure`, `set_fps_multiplier` + `self.fps_multiplier`,
`_get_current_fps`, `load_wb_steps`, `set_free_mode`, `update_shutter_angle_for_fps`. Review
`get_current_sensor_mode` separately. **Risk:** low for the six; medium for
`get_current_sensor_mode` if its logic is not duplicated on the live path.
**Needs Pi:** no — the four-surface check above closes the reflective-dispatch gap.
**Residual risk:** a user's own `settings.jsonc` on their Pi could bind one of these names.
That is a real gap I cannot close statically. **Pi check:** `grep '"method"' /home/pi/cinemate/settings.jsonc`
on a deployed unit and confirm none of the seven appear.

### F-120 — Five unused `@property` accessors and a self-described legacy method in `ssd_monitor.py`

| F-120 | low | confirmed | cinemate | dead-code | 5 properties and `get_mount_status` have no reader | src/module/ssd_monitor.py:166 |

`SSDMonitor` exposes a block of read-only properties at
`src/module/ssd_monitor.py:161-186`. Five have no reader anywhere in the repo — note the
grep pattern `\bname\b` matches attribute access (`obj.space_left_gb`) as well as the
definition, so a score of 1 means the property is never *read*, not merely never imported:

| Property | Line | Backing field |
|---|---|---|
| `space_left_gb` | src/module/ssd_monitor.py:166 | `self._space_left` |
| `device_type` | src/module/ssd_monitor.py:170 | `self._device_type` |
| `filesystem_type` | src/module/ssd_monitor.py:174 | `self._filesystem_type` |
| `mount_options` | src/module/ssd_monitor.py:178 | `self._mount_options` |
| `recorder_profile` | src/module/ssd_monitor.py:182 | `self._recorder_profile` |

By contrast the neighbouring `is_mounted` (`src/module/ssd_monitor.py:162`) and `space_left`
(`src/module/ssd_monitor.py:186`) are live, so this is not a case of the whole block being
externally consumed by some mechanism grep cannot see.

Separately, `get_mount_status` at `src/module/ssd_monitor.py:1249` documents its own
deadness in the source:

```python
    def get_mount_status(self) -> bool:   # just in case other code uses it
        """Old API – true if /media/RAW is currently mounted."""
```

"Old API", "just in case other code uses it" — no other code does. It is a duplicate of the
live `is_mounted` property (`src/module/ssd_monitor.py:162`); both return `self._is_mounted`.

**Action:** delete the five properties and `get_mount_status`. **Risk:** low. These are the
kind of accessor an out-of-tree script might touch, but nothing in the repo does.
**Needs Pi:** no.

### F-121 — Three uncalled methods in the 115-line `dmesg_monitor.py`

| F-121 | low | confirmed | cinemate | dead-code | `read_dmesg_log`, `handle_file_change`, `reset_undervoltage_flag` have no caller | src/module/dmesg_monitor.py:29 |

`DmesgMonitor` (`src/module/dmesg_monitor.py:6`) is live — constructed in `main.py` (imported
at `src/main.py:33`) and stopped at `src/main.py:984`. But three of its eight methods are
unreachable:

| Method | Line |
|---|---|
| `read_dmesg_log` | src/module/dmesg_monitor.py:29 |
| `handle_file_change` | src/module/dmesg_monitor.py:53 |
| `reset_undervoltage_flag` | src/module/dmesg_monitor.py:57 |

The live path is `run` (`src/module/dmesg_monitor.py:21`) → `_start_monitoring`
(`src/module/dmesg_monitor.py:61`, called at `src/module/dmesg_monitor.py:22`), which
subprocesses `dmesg` directly. `read_dmesg_log` and `handle_file_change` are the remains of
an earlier file-watching approach that `_start_monitoring` replaced.

`reset_undervoltage_flag` is the notable one: undervoltage is a genuine field problem on a
battery-powered camera, and the only way to clear the flag once raised is a method nobody
calls. Whether that matters depends on whether the flag is meant to latch for the session —
which the code does not say either way.

**Action:** delete `read_dmesg_log` and `handle_file_change`. Decide deliberately about
`reset_undervoltage_flag`: either wire it to something (a GUI dismiss, a recording start) or
remove it and document that the flag latches until restart. **Needs Pi:** no to confirm the
deadness. **Yes** to decide the undervoltage question: trigger an undervoltage event on a Pi
(load the 5V rail) and observe whether the warning ever clears on its own.

### F-122 — Complete module-reachability result for `src/` (closes the "unreferenced module" question)

| F-122 | medium | confirmed | cinemate | dead-code | Exactly 4 of 48 modules are unreachable from `main.py`, totalling 376 LOC; no others | src/module/rotary_encoder.py:1 |

I built the import graph over all 48 Python modules in `src/` — resolving absolute imports,
`from module import x` submodule forms, and **relative** imports (`from .main.routes import
main_routes` etc., which a naive absolute-only resolver misreports) — and did a reachability
search from `src/main.py`.

**42 of 48 modules are reachable.** The six that are not:

| Module | Path | LOC | Verdict |
|---|---|---|---|
| `stream` | src/stream.py | 21 | dead — already **F-013** |
| `module.timekeeper` | src/module/timekeeper.py | 243 | dead — already **F-017** (see also F-110) |
| `module.keyboard` | src/module/keyboard.py | 88 | dead — already **F-031** |
| `module.rotary_encoder` | src/module/rotary_encoder.py | 24 | dead — **F-100** |
| `__init__` | src/__init__.py | 0 | package marker, correct |
| `module.i2c` | src/module/i2c/__init__.py | 1 | package marker, correct |

Total genuinely dead module code: **376 LOC**, of which 352 were already known. F-100 is the
only new module.

**The relative-import handling is the load-bearing part of this result.** With absolute-only
resolution the answer is 36/48 reachable, and the six `module.app.*` modules — `api.py` (225
LOC), `boot_config.py` (210), `settings_editor.py` (355), `raw_files.py` (183),
`main/events.py` (124), `main/routes.py` (39) — appear unreachable. They are not. They are
imported lazily inside `create_app` at `src/module/app/__init__.py:40-44`, using relative
form. That is almost certainly the origin of the "no inbound import edge" reading in this
review's target list. See the cleared-targets section below.

**Practical consequence:** the "find an unreferenced module" avenue in `src/` is now
exhausted. Remaining dead code in `src/` is *intra*-module — dead methods, dead branches,
dead attributes — which is what F-100 through F-121 cover. Later sessions should not re-run
this analysis.

**Needs Pi:** no.

## Cleared targets — investigated and found LIVE

Four of the seven priority targets in my brief are **not dead**. Recording this explicitly so
no later session re-opens them.

| Target | Verdict | Evidence |
|---|---|---|
| `src/module/parameters.py` | **LIVE** | Imported as `from module import parameters` — `src/module/cinepi_controller.py:25`, `src/module/analog_controls.py:10`, `src/module/i2c/quad_rotary_controller.py:14`. Heavily used: `parameters.free_mode_steps(...)` at `src/module/cinepi_controller.py:416`, `:421`, `:430`, `:458`, `:464`, `:470`, `:476`, `:482`, `:761`, `:890`, `:1722` and `src/module/analog_controls.py:138`, `:140`, `:148`; `parameters.get(...)` at `src/module/cinepi_controller.py:2012`, `:2106`, `:2135`, `src/module/analog_controls.py:166`, `src/module/i2c/quad_rotary_controller.py:137`. |
| `src/module/app/raw_files.py` | **LIVE** | `from module.app import boot_config, raw_files` at `src/module/app/settings_editor.py:34`; called at `src/module/app/settings_editor.py:309`, `:314`, `:319`, `:325`, `:329`, `:352`. |
| `src/module/app/boot_config.py` | **LIVE** | Same import line; called at `src/module/app/settings_editor.py:218`, `:223`, `:226`, `:231`, `:239`, `:251`, `:259`. |
| `src/module/mediator.py` | **LIVE** (partly) | Instantiated at `src/main.py:941`; four handlers subscribed at `src/module/mediator.py:19-22`. But 6 of its 13 methods are dead — F-102. |
| `src/module/utils.py` | **LIVE** | `from module.utils import Utils` at `src/module/simple_gui.py:15` and `src/module/i2c/i2c_oled.py:7`; `Utils.cpu_load()` / `cpu_temp()` / `memory_usage()` at `src/module/simple_gui.py:659`, `:664`, `:814` and `src/module/i2c/i2c_oled.py:129`, `:131`, `:133`. |

**Why the brief said otherwise.** Three of these hide from a plain
`grep "import <modname>"`:

- `parameters.py` is imported as `from module import parameters` — the module name appears in
  the *imported-names* position, not after `import`.
- `raw_files.py` and `boot_config.py` are likewise `from module.app import boot_config,
  raw_files`, and are additionally reached only through the lazily-imported
  `settings_editor.py` (`src/module/app/__init__.py:43`), two edges from `main.py`.

The brief asked me to check Flask blueprint wiring for the last two. That turned out to be
the wrong hypothesis in an instructive way: they are not reached *by* route registration,
they are plain modules imported by the module that owns the routes. The blueprint registration
does matter one level up — `settings_editor_bp` is registered in `create_app`
(`src/module/app/__init__.py:43`) — but `raw_files` and `boot_config` themselves are ordinary
library code.

**Method note for later sessions:** any import-graph analysis of this repo must resolve
`from X import y` where `y` is a submodule, and must resolve relative imports. Missing either
produces false "dead module" reports — as it did here for six live `module.app.*` files
totalling 1,136 LOC.

### F-123 — A family of dead backward-compatibility aliases

| F-123 | low | confirmed | cinemate | redundancy | 3 self-declared compatibility aliases with zero callers, each shadowing a live function | src/module/config_loader.py:143 |

The codebase keeps thin delegating wrappers "for compatibility". None has a caller.

| Alias | Line | Delegates to | Self-description in source |
|---|---|---|---|
| `storage_preroll_enabled` | src/module/config_loader.py:143 | `auto_storage_preroll_enabled` (src/module/config_loader.py:134) via `src/module/config_loader.py:146` | `"""Backward-compatible alias for automatic storage pre-roll."""` (src/module/config_loader.py:144) |
| `start_cinepi_process` | src/module/cinepi_multi.py:713 | `start_all` (src/module/cinepi_multi.py:724) via `src/module/cinepi_multi.py:714` | — |
| `get_mount_status` | src/module/ssd_monitor.py:1249 | returns `self._is_mounted`, same as the live `is_mounted` property (src/module/ssd_monitor.py:162) | `# just in case other code uses it` / `"""Old API – …"""` |

In each case the delegate is live: `auto_storage_preroll_enabled` is imported at
`src/main.py:16` and used at `src/main.py:761`; `start_all` is called at
`src/module/cinepi_multi.py:714` (by the dead alias itself) and `src/module/cinepi_multi.py:718`
(by the live `restart`); `is_mounted` is a live
property.

Compatibility aliases are only worth their cost if something is actually depending on the old
name. Nothing in this repo is. They cost twice: a reader must determine which of two names is
canonical, and a refactor must update both.

**Action:** delete all three. **Risk:** low — but this is the class of symbol most likely to
be referenced by a user's out-of-tree script, so mention them in release notes rather than
removing silently. **Needs Pi:** no.

### F-124 — `check_hotspot_status()` in `main.py` duplicates `wifi_hotspot.hotspot_service_active()`

| F-124 | medium | confirmed | cinemate | redundancy | Two implementations of "is the hotspot up?"; the `main.py` one is dead and uses a different mechanism | src/main.py:529 |

`src/main.py:529` defines:

```python
def check_hotspot_status():
    """Return True if a Wi-Fi hotspot connection is active."""
    result = subprocess.run(
        ['nmcli', 'con', 'show', '--active'], capture_output=True, text=True
    )
    return any('wifi' in line and 'Hotspot' in line for line in result.stdout.split('\n'))
```

It has **no caller** — a whole-repo corpus grep scores it at 1 (the `def` line). The live
answer to the same question comes from the dedicated module: `hotspot_service_active` is
defined at `src/module/wifi_hotspot.py:320`, exported in that module's `__all__` at
`src/module/wifi_hotspot.py:36`, imported at `src/main.py:28` and called at `src/main.py:592`.

The two do not agree on method. The dead one shells out to `nmcli con show --active` and
string-matches on the literal `'Hotspot'`; the live one is a service-state check (its name
and its home in `wifi_hotspot.py` alongside `WiFiHotspotManager`). A connection named
anything other than `Hotspot` defeats the dead one — so this is not a redundant-but-equivalent
pair, it is a worse implementation kept next to a better one, in the file a reader opens first.

Note also that `subprocess.run` here has no `timeout`; `nmcli` blocking would hang startup.
That defect is inert only because the function is dead.

**Action:** delete `src/main.py:529-534`. **Risk:** none — no caller. **Needs Pi:** no.

### F-125 — Remaining uncalled functions (7 sites), including one no-op GPIO shim pair

| F-125 | low | confirmed | cinemate | dead-code | 7 further functions with no caller anywhere in the repo | src/module/gpio_input.py:146 |

Completing the never-called sweep. Each scores 1 in the whole-repo corpus (the `def` line
only); Flask/socketio-decorated functions and `settings.jsonc`-dispatched controller methods
were excluded first, as described in F-119.

| Function | Line | Note |
|---|---|---|
| `ComponentInitializer.get_smart_button_by_pin` | src/module/gpio_input.py:146 | Lookup helper over `self.smart_buttons_list`; nothing looks buttons up by pin |
| `ComponentInitializer._describe_actions` | src/module/gpio_input.py:182 | Builds a human-readable action description that is never logged or returned to anyone |
| `ADC.read_raw` | src/module/grove_base_hat_adc.py:61 | Sibling of the live `read` (src/module/grove_base_hat_adc.py:89) and `read_voltage` (`:75`) |
| `RedisListener._update_frames_in_sync` | src/module/redis_listener.py:753 | Private, never called |
| `SimpleGUI._validate_wav_length` | src/module/simple_gui.py:1075 | Audio/video length sanity check — see note |
| `StoragePreroll._resolve_fps_max` | src/module/storage_preroll.py:314 | Private, never called |
| `USBMonitor.filter_sound_device` | src/module/usb_monitor.py:630 | Never called |

**`_validate_wav_length` (`src/module/simple_gui.py:1075`) deserves a decision, not a
deletion.** On a camera that records audio alongside DNG frames, "is the WAV the length the
frame count implies?" is a real correctness check — the kind of thing that catches a dropped
audio buffer before the edit suite does. It was written and never wired in. Deleting it
throws away the check; leaving it dead means the check never runs. Recommend wiring it into
the end-of-take path rather than removing it.

**`SimpleGUI.set_background_color` (`src/module/simple_gui.py:286`)** is a related but
different case, so I list it separately: it is uncalled, yet the feature is live. Every real
background-colour change assigns the attribute directly —
`self.current_background_color = ...` at `src/module/simple_gui.py:1725`, `:1728`, `:1731`,
`:1737`, `:1742`, `:1747`, `:1752` — bypassing the setter. The getter twin
`get_background_color` (`src/module/simple_gui.py:290`) *is* used, at
`src/module/app/main/routes.py:37`, `src/module/app/main/events.py:45` and
`src/module/app/main/events.py:116`. So the accessor pair is half-adopted: reads go through
the method, writes do not. Either route the seven assignments through the setter or drop it.

**No-op GPIO shim — deliberate, flagging for completeness.** `GPIO.setmode`
(`src/module/rpi_gpio_wrapper.py:16`) and `GPIO.setwarnings`
(`src/module/rpi_gpio_wrapper.py:21`) are also uncalled, but they are an intentional
drop-in surface mimicking `RPi.GPIO`, and `setmode`'s body says so:
`# lgpio doesn't need this, but we keep it for compatibility`
(`src/module/rpi_gpio_wrapper.py:17`). **Do not delete these on dead-code grounds.** One real
observation though: `setwarnings` assigns `GPIO._warned = not flag`
(`src/module/rpi_gpio_wrapper.py:22`), and `_warned` (declared at
`src/module/rpi_gpio_wrapper.py:13`) is never read anywhere in the file or the repo — so the
warning-suppression the shim appears to offer does nothing.

**Action:** delete the seven above except `_validate_wav_length`, which should be wired in or
consciously dropped. Leave the GPIO shim. **Needs Pi:** no for the deadness. **Yes** to wire
up `_validate_wav_length` meaningfully — it needs a real take with audio to test against.

### F-126 — `_as_bool` implemented four times, with four different answers

| F-126 | high | confirmed | cinemate | correctness | Four divergent boolean coercions for the same settings values; `_as_bool(2)` is `True` in one and `False` in three | src/module/gpio_input.py:163 |

The same helper name is defined in four modules, all coercing settings/Redis values to bool,
none shared:

| Location | `None` | `2` (int) | Extra parameter |
|---|---|---|---|
| `src/module/cinepi_controller.py:345` | `False` (via `str(None)` = `"none"`) | **`False`** | — |
| `src/module/dynamic_resolution.py:43` | `False` (via `str(value or "")`) | **`False`** | — |
| `src/module/gpio_input.py:163` | **`default`** (caller-supplied, often `True`) | **`True`** | `default=False` |
| `src/module/mediator.py:80` | `False` (explicit) | **`False`** | — |

Three implementations stringify and test membership in `("1","true","yes","on")`; the fourth
(`src/module/gpio_input.py:167-168`) short-circuits numeric types with `bool(value)`. So for
any integer other than 0 or 1 the four disagree:

- `_as_bool(2)` → `True` under `gpio_input`, `False` under the other three, because `str(2)`
  is `"2"` which is not in the membership set.

They also disagree on `None`. Three return `False`; `gpio_input` returns its `default`
argument, and its callers pass `default=True` — for example
`self._as_bool(encoder_config.get('enabled', True), default=True)` at
`src/module/gpio_input.py:102` and `self._as_bool(encoder_config.get('pull_up'), default=True)`
at `src/module/gpio_input.py:137`. So a missing or null `enabled` key means *enabled* in the
GPIO layer and *disabled* everywhere else.

**Why this matters concretely.** These four all parse the same `settings.jsonc` document.
`gpio_input._as_bool` decides whether a rotary encoder or button is enabled
(`src/module/gpio_input.py:102`) and whether its pull-up is on (`src/module/gpio_input.py:137`);
`cinepi_controller._as_bool` and `dynamic_resolution._as_bool` decide feature flags on the
same settings tree. A user who writes `"enabled": 2` — or any truthy-looking non-1 integer —
gets a control that the GPIO layer arms and the rest of the system believes is off. The
failure is silent in both directions and would present as "the button works but the feature
it toggles doesn't".

Severity **high** on the maintenance-trap criterion: four copies of a coercion is the exact
shape that produces a bug the next time anyone touches settings parsing, and one copy has
already diverged on two axes.

**Action:** promote a single implementation to `config_loader.py` (which already owns
`_coerce_bool_setting`, defined at `src/module/config_loader.py:118` and used at
`src/module/config_loader.py:138` and `:171`) and have all four call it.
Decide deliberately what `None` and non-0/1 integers mean, and write that down.
**Risk:** medium — unifying will *change behaviour* wherever the divergent path was being
relied on, so the `gpio_input` `default=True` call sites at `src/module/gpio_input.py:102`
and `:137` need their semantics preserved explicitly.
**Needs Pi:** no to confirm the divergence (pure source comparison). **Yes** to confirm no
deployed `settings.jsonc` relies on it: `grep -n '"enabled"' /home/pi/cinemate/settings.jsonc`
and check for any value that is not `true`/`false`.

### F-127 — Hand-rolled observer `Event` class implemented four times

| F-127 | medium | confirmed | cinemate | redundancy | Four separate `class Event` definitions with divergent error handling and signatures | src/module/usb_monitor.py:17 |

Four modules each define their own `class Event`:

| Location | `emit` signature | Error handling | `unsubscribe`? |
|---|---|---|---|
| `src/module/usb_monitor.py:17` | `emit(self, *args)` | try/except → `logging.error` + `traceback.print_exc()` | no |
| `src/module/ssd_monitor.py:58` | `emit(self, *args)` | try/except → `logging.exception` | no |
| `src/module/cinepi_multi.py:113` | `emit(self, data=None)` | **none — one raising listener kills the emit loop** | no |
| `src/module/redis_controller.py:145` | `emit(self, data=None)` | **none** | **yes** (`src/module/redis_controller.py:150`) |

The divergences are behavioural, not cosmetic:

- **Two of the four have no exception isolation.** In `cinepi_multi` (`src/module/cinepi_multi.py:118-120`)
  and `redis_controller` (`src/module/redis_controller.py:155-157`), one listener raising
  aborts the loop and the remaining listeners never fire. `redis_controller.redis_parameter_changed`
  is the busiest event in the system — subscribed by the mediator
  (`src/module/mediator.py:20-22`), the GUI (`src/module/simple_gui.py:222`), the web API
  (`src/module/app/api.py:205`), socket events (`src/module/app/main/events.py:112`), the
  status broadcaster (`src/module/status_broadcast.py:77`) and the controller
  (`src/module/cinepi_controller.py:147`). Six subscribers, no isolation, and subscription
  order decides who gets dropped when one of them throws.
- **Two iterate a live list.** `usb_monitor` (`src/module/usb_monitor.py:25`) and
  `cinepi_multi` (`src/module/cinepi_multi.py:119`) iterate `self._listeners` directly, while
  `ssd_monitor` (`src/module/ssd_monitor.py:66`) and `redis_controller`
  (`src/module/redis_controller.py:156`) copy first — `ssd_monitor` even documents why
  (`# shallow copy – safe against rm`, `src/module/ssd_monitor.py:66`). A listener that unsubscribes during dispatch corrupts
  iteration in two of the four.
- **Only one supports `unsubscribe`** (`src/module/redis_controller.py:150`).

**Action:** extract one `Event` into a shared module — with copy-on-iterate, per-listener
exception isolation, and `unsubscribe` — and delete the other three. **Risk:** medium, and
it is the interesting kind: adding exception isolation to `redis_parameter_changed` will
*surface* listener exceptions that are currently silently truncating the dispatch chain. That
is a fix, but it will look like new errors appearing. Expect to find real bugs.
**Needs Pi:** no to confirm the duplication. **Yes** to assess the impact: on a Pi, add a
temporary `logging.exception` around each `redis_parameter_changed` listener and watch a full
record cycle in `journalctl -u cinemate` for listeners that currently throw.


---

## Summary table

All findings, in ID order. Same rows as above, collected for the ledger.

| ID | severity | confidence | repo | category | summary | evidence |
|---|---|---|---|---|---|---|
| F-100 | medium | confirmed | cinemate | dead-code | `rotary_encoder.py` / `SimpleRotaryEncoder` never imported; superseded by `gpio_input.RotaryEncoder` | src/module/rotary_encoder.py:4 |
| F-101 | medium | confirmed | cinemate | redundancy | 5 `.pyc` files committed to git despite `.gitignore`; one is for a deleted `adc` module | src/module/__pycache__/adc.cpython-39.pyc |
| F-102 | medium | confirmed | cinemate | dead-code | 6/13 `Mediator` methods have no subscriber and no caller | src/module/mediator.py:34 |
| F-103 | low | confirmed | cinemate | dead-code | `self.usb_monitor` and `self.redis_listener` assigned but never used | src/module/mediator.py:11 |
| F-104 | medium | confirmed | cinemate | dead-code | `hasattr(self.stream, "toggle_background_color")` can never be true; branch is unreachable | src/module/mediator.py:151 |
| F-105 | medium | confirmed | cinemate | redundancy | Four independent `StrictRedis` clients with hardcoded `localhost:6379`, bypassing `RedisController` | src/module/usb_monitor.py:141 |
| F-106 | medium | confirmed | cinemate | redundancy | `CAPTURE_GAIN_REDIS_KEY` re-declares an existing `ParameterKey`; `"is_recording"` used as a bare literal | src/module/usb_monitor.py:14 |
| F-107 | low | probable | cinemate | dead-code | Five `MIC_*` keys published/cleared with no in-repo reader | src/module/usb_monitor.py:441 |
| F-108 | high | confirmed | cinemate | dead-code | `SSDMonitor.stop()` has no caller; its body would raise `AttributeError` on `self._jthread` if it did | src/module/ssd_monitor.py:155 |
| F-109 | medium | confirmed | cinemate | dead-code | 70-line `_journal_loop` unreachable; sole reference is a commented-out thread target | src/module/ssd_monitor.py:1254 |
| F-110 | low | confirmed | cinemate | dead-code | `timekeeper` is set to `None` and never reassigned; the shutdown guard can never fire | src/main.py:658 |
| F-111 | low | confirmed | cinemate | readability | At least 8 multi-line commented-out code blocks, two of them file-tail dumps | src/module/framebuffer.py:173 |
| F-112 | high | confirmed | cinemate | correctness | Guard `if self.ssd_monitor.is_mounted:` commented out; body now runs unconditionally and the CFE-HAT branch calls a method that does not exist | src/module/cinepi_controller.py:2033 |
| F-113 | medium | confirmed | cinemate | dead-code | fsck result published to Redis but no live consumer; only reader is a commented-out GUI snippet | src/module/ssd_monitor.py:44 |
| F-114 | medium | confirmed | cinemate | redundancy | Superseded `arecord -vvv` VU path still present alongside the live Redis `audio_vu` path | src/module/usb_monitor.py:467 |
| F-115 | medium | confirmed | cinemate | dead-code | Entire `USBDriveMonitor` class unreferenced outside its own definition | src/module/usb_monitor.py:33 |
| F-116 | medium | confirmed | cinemate | redundancy | 6 wrapper accessors around `get_resolution_info` never called; `get_packing` is silently wrong on Pi 4 | src/module/sensor_detect.py:616 |
| F-117 | high | confirmed | cinemate | redundancy | `ACTION_METHODS` duplicated verbatim in Python and JS; `GET /api/actions`, the only thing that validates it, has no consumer | src/module/app/settings_editor.py:63 |
| F-118 | high | confirmed | cinemate | correctness | Catalogue entry `set_log` resolves to nothing; the real method is `set_log_encode` | src/module/app/settings_editor.py:94 |
| F-119 | medium | confirmed | cinemate | dead-code | 7 controller methods with no static caller, no `settings.jsonc` binding and no catalogue entry | src/module/cinepi_controller.py:768 |
| F-120 | low | confirmed | cinemate | dead-code | 5 properties and `get_mount_status` have no reader | src/module/ssd_monitor.py:166 |
| F-121 | low | confirmed | cinemate | dead-code | `read_dmesg_log`, `handle_file_change`, `reset_undervoltage_flag` have no caller | src/module/dmesg_monitor.py:29 |
| F-122 | medium | confirmed | cinemate | dead-code | Exactly 4 of 48 modules are unreachable from `main.py`, totalling 376 LOC; no others | src/module/rotary_encoder.py:1 |
| F-123 | low | confirmed | cinemate | redundancy | 3 self-declared compatibility aliases with zero callers, each shadowing a live function | src/module/config_loader.py:143 |
| F-124 | medium | confirmed | cinemate | redundancy | Two implementations of "is the hotspot up?"; the `main.py` one is dead and uses a different mechanism | src/main.py:529 |
| F-125 | low | confirmed | cinemate | dead-code | 7 further functions with no caller anywhere in the repo | src/module/gpio_input.py:146 |
| F-126 | high | confirmed | cinemate | correctness | Four divergent boolean coercions for the same settings values; `_as_bool(2)` is `True` in one and `False` in three | src/module/gpio_input.py:163 |
| F-127 | medium | confirmed | cinemate | redundancy | Four separate `class Event` definitions with divergent error handling and signatures | src/module/usb_monitor.py:17 |

**Counts by severity:** high 5 · medium 15 · low 8 · critical 0 · nit 0 — **28 total**

**Counts by confidence:** confirmed 27 · probable 1 · unverified 0

**Counts by category:** dead-code 15 · redundancy 9 · correctness 3 · readability 1
---

## Pi-verification queue (from this agent)

Nothing in this report *depends* on a Pi to be believed — all 28 are settled statically. These
are checks that would sharpen consequence or catch deployment-specific risk.

| Finding | Test | What it settles |
|---|---|---|
| F-105 | `redis-cli info clients` and `ss -tn state established '( dport = :6379 )' \| wc -l` sampled during a 60 s take | Confirms one new Redis connection per second while recording |
| F-108 | `systemctl stop cinemate`, then `journalctl -u cinemate` | Whether the un-stopped SSD thread delays or hangs shutdown |
| F-112 | With no SSD attached, call `CinePiController.unmount` (`src/module/cinepi_controller.py:2032`); watch `journalctl -u cinemate` | Whether the now-unguarded `unmount_drive()` errors when nothing is mounted |
| F-118 | Bind a button to `set_log` in the settings editor, press it | Confirms the silent no-op through `getattr(..., None)` |
| F-119 | `grep '"method"' ~/cinemate/settings.jsonc` on a deployed unit | Whether a *user's* settings bind any of the 7 methods I found unbound in shipped configs |
| F-121 | Load the 5 V rail to trigger undervoltage | Whether the undervoltage flag ever clears without `reset_undervoltage_flag` |
| F-126 | `grep -n '"enabled"' ~/cinemate/settings.jsonc` | Whether any deployed value is a non-`true`/`false` literal that the four `_as_bool` copies would read differently |
| F-127 | Temporarily wrap each `redis_parameter_changed` listener in `logging.exception`; run a full record cycle | Which listeners currently throw and silently truncate the dispatch chain |

## Cross-agent handoffs

- **Agent 3 (cinepi-raw, F-200..F-249)** — two greps of the sibling repo close two findings:
  - `MIC_PCM_ALIAS` → settles **F-107**. If cinepi-raw has no reader, promote F-107 from
    `probable` to `confirmed` dead-code.
  - `FSCK_STATUS` → refines **F-113**. Currently `confirmed` for cinemate only.
- **Agent 2 (services/install, F-150..F-199)** — `python3-systemd` is installed at
  `cinemate-install.sh:523`; with **F-109** actioned, nothing in `src/` imports `systemd`.
  Candidate for the unused-installer-packages list (F-032), pending a check that nothing in
  `services/` imports it.
- **F-113** proposes *adding* `FSCK_STATUS` to `ParameterKey` rather than deleting the writes.
  If Agent 2's dead-config-key sweep independently proposes removing it, reconcile — my
  reading is that the display is missing, not that the data is unwanted.

## Method notes for later sessions

1. **The import graph needs relative-import resolution.** Absolute-only resolution reports 36
   of 48 modules reachable and falsely condemns six live `module.app.*` files (1,136 LOC).
   With relative imports resolved the answer is 42 of 48. See F-122.
2. **`from module import parameters` hides from `grep "import parameters"`.** The module name
   sits in the imported-names position. This is why `parameters.py` was on the suspect list.
3. **The four dispatch surfaces** that must be checked before calling a `CinePiController`
   method dead: static callers; `"method"` strings in `settings.jsonc` and both
   `resources/settings/*.jsonc`; the two `ACTION_METHODS` catalogues; and the whole-repo text
   corpus. Control probes: `set_zoom` scores 19 in the corpus, `set_iso` 15 — if your method
   scores 1, it is the `def` line alone.
4. **Dead subgraphs need transitive analysis.** In `mediator.py`, four of six dead methods are
   referenced — but only by other dead methods (F-102). A "is this name mentioned anywhere?"
   check clears them wrongly.
5. **`hasattr` guards are where removed features go to hide.** F-104 and F-110 are both
   permanently-false `hasattr`/truthiness guards left behind when a collaborator changed type
   or disappeared. Grepping for `hasattr(` against known-`None` locals is a productive sweep.

## Coverage and limits

- All 47 `.py` files under `src/` (19,794 LOC) were included in the import graph, the
  never-called sweep and the commented-block scan.
- **Symbol counts are lower bounds.** Grep cannot see dynamically constructed names. Where I
  say "at least N" I mean it; where I say a symbol scores 1 in the corpus, that is exact for
  literal occurrences only.
- **Not covered** (out of scope or better placed elsewhere): the HTML/JS inside
  `src/module/app/templates/` beyond the `ACTION_METHODS` comparison in F-117/F-118; dead
  config keys in `settings.jsonc` (Agent 2); anything in `services/`, `_test/` or the
  installer (Agent 2).
- **One residual gap I cannot close statically:** a user's own `settings.jsonc` on a deployed
  Pi could bind a controller method I classified as dead (F-119). Shipped configs are clean —
  all 37 `"method"` strings across the three shipped files resolve.
