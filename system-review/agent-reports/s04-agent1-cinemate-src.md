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
