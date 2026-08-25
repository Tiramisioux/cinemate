# Entry points — where do I go to change X

**Session:** S11b · **Branch read:** `dev`, both repos · **Pi used:** no

`PLAN.md` calls this the highest-value artifact of the review, and the reason is the
fourth column. **"What else to update"** is where this codebase actually costs you: nearly
every change below has a second edit somewhere else that nothing will remind you about.

The fifth column is new since the plan was written. Four checks now exist that catch some
of those second edits mechanically — `tools/redis_key_diff.py`, `tools/gui_field_extract.py`,
`tools/design_token_diff.py`, `tools/docs_drift_check.py`, all wired into
`.github/workflows/checks.yml`. Where a row says **"nothing"**, you are on your own, and
that is the honest state.

---

## 1. The table

### Add or rename a Redis key

| | |
|---|---|
| **Primary edit** | `src/module/redis_controller.py:18` — add a member to `ParameterKey` |
| **What else** | If cinepi-raw also reads or writes it: `cinepi/cinepi_state.hpp` (`#define CONTROL_KEY_*`). If operators should know about it: a row in `docs/redis-keys.md` |
| **Caught by** | `redis_key_diff.py` (ratchet) for the cross-repo side · `docs_drift_check.py --only keys` for the docs side |
| **Watch for** | The enum is **convention, not enforcement** — `set_value()` accepts any string, and several live keys bypass it entirely. Adding the member does not stop anyone writing the raw string |

### Add a controller method / a new action

| | |
|---|---|
| **Primary edit** | `src/module/cinepi_controller.py` — a public method on `CinePiController` |
| **What else** | **Four places.** `cli_commands.py:38` (`self.commands` dict, for CLI + serial + `POST /api/v1/cmd`) · `app/settings_editor.py:63` (`ACTION_METHODS`) · the hand-maintained copy in `app/templates/settings_editor.html` · `docs/controller-methods.md` |
| **Caught by** | `gui_field_extract.py` (gates at zero) and `_test/test_action_catalogues_agree.py` for the two catalogues · `docs_drift_check.py --only methods` for the doc |
| **Watch for** | Everything dispatches by `getattr()`, so **a name that does not resolve is silence, not an error.** That is how `set_log` shipped as a button that did nothing. The doc copy was the only one of the four that was right |

### Add a settings key

| | |
|---|---|
| **Primary edit** | `settings.jsonc` |
| **What else** | `settings.schema.json` — **required now**, since `additionalProperties` is `false` throughout; an undescribed key is rejected by editors · `config_loader.py`'s `setdefault` chain if it needs a default · `resources/settings/settings_default.jsonc` · `docs/settings-json.md` (one `##`/`###` heading matching the key name) |
| **Caught by** | `_test/test_settings_schema_rejects_unknown_keys.py` · `docs_drift_check.py --only settings` |
| **Watch for** | Defaults are stated in **four** registries and eleven keys already disagree. Decide which one you mean to be authoritative before adding a fifth statement of it |

### Add or change a GUI field

| | |
|---|---|
| **Primary edit** | `simple_gui.py`'s `populate_values()` (`:705-1073`) — one dict, **68 fields** |
| **What else** | Usually **nothing**, and this is the good news: the web GUI consumes this dict verbatim (`app/main/events.py:57`), so a field added here reaches the browser automatically. To *display* it: `self.layout` and `self.colors` in `setup_resources()` for HDMI, and the template for the browser |
| **Caught by** | `gui_field_extract.py` reports which fields reach the template |
| **Watch for** | Deltas are emitted from inside `draw_gui()`, so the browser updates at the framebuffer's cadence and stops if that thread stops |

### Change a colour

| | |
|---|---|
| **Primary edit** | `simple_gui.py:21-48` (module constants) or `self.colors` in `setup_resources()` |
| **What else** | `app/templates/template.html`'s `:root` block — **16 CSS custom properties**, of which only 3 name their Python counterpart in a comment |
| **Caught by** | `design_token_diff.py --strict` (gates at zero; nothing has drifted yet) |
| **Watch for** | `ZOOM_HIGHLIGHT_COLOR` is a *function-local*, and the same literal is retyped 580 lines away. Grep the value, not just the name |

### Add a Python dependency

| | |
|---|---|
| **Primary edit** | `requirements.txt` if it imports anywhere; `requirements-hardware.txt` if it needs a Pi |
| **What else** | Nothing — the installer reads both files. `requirements-dev.txt` for tooling, `docs/requirements-docs.txt` for the docs build |
| **Caught by** | The `pytest` CI job, if the import is portable |
| **Watch for** | This used to be two lists that disagreed in both directions. Do not reintroduce a literal in `cinemate-install.sh` |

### Add a CLI command

| | |
|---|---|
| **Primary edit** | `cli_commands.py:38` — `self.commands`, mapping a command string to `(callable, arg_type)` |
| **What else** | `docs/cli-commands.md` and/or `docs/cli-user-guide.md`. The web API's `/commands` endpoint is generated from the same dict, so it needs nothing |
| **Caught by** | **Nothing.** A docs-vs-dispatcher check was attempted and withheld — a token diff cannot distinguish a command from its arguments |
| **Watch for** | This dict is also what `POST /api/v1/cmd` dispatches, so a CLI command is simultaneously a web API command |

### Add a systemd service

| | |
|---|---|
| **Primary edit** | `services/<name>/` with a `.service` file and a `Makefile` implementing `install`/`uninstall` |
| **What else** | `services/Makefile`'s `SUBSERVICES` list · the installer's service step · `docs/system-services.md` and the services section of `docs/installation-steps.md` |
| **Caught by** | Nothing |
| **Watch for** | The install doc's services section covers four of the five existing units — the recovery console is absent from all 1061 lines of it |

### Change the HDMI layout

| | |
|---|---|
| **Primary edit** | `setup_resources()` (`:436-599`) — `self.layout` for absolute positions, `left_section_layout`/`right_section_layout` for grouped sections |
| **What else** | Nothing for HDMI. The browser has its own CSS layout and does not read these |
| **Caught by** | Nothing |
| **Watch for** | The section tables already support a `condition` predicate for visibility — use it rather than commenting an item out, which six entries currently do. `_top_row_layout` computes justified positions from measured text, so the top row reflows; the bottom row does not |

### Add a sensor

| | |
|---|---|
| **Primary edit** | `resources/sensors.json` — a genuine single source; cinepi-raw holds no sensor data |
| **What else** | `settings.jsonc`'s `arrays.*.steps` if the UI should expose new modes · `docs/sensors.md` · a driver in the installer if it needs an out-of-tree module |
| **Caught by** | Nothing |
| **Watch for** | cinepi-raw does **not** read `sensors.json`. Hardware facts reach it as Redis keys and command-line arguments that cinemate translates |

### Change logging

| | |
|---|---|
| **Primary edit** | `src/module/logger.py` — `configure_logging()`, the formatter, the handlers |
| **What else** | `log_directory()` is the single source for the path; `main.py`'s cleanup uses it too |
| **Caught by** | `ruff` for `print()` and bare `except` |
| **Watch for** | Two idioms coexist — **615** module-level `logging.X()` calls against **112** named-logger calls. Match the file you are in rather than the repo |

---

## 2. The seams that are not in the table

Three things are not "where do I change X" but will decide whether your change works.

**Everything live goes through one cached bus.** `RedisController.get_value()` reads a local
cache kept fresh by a single listener thread, not Redis. That thread now survives a raising
subscriber, but it is still one thread, and `listener_alive()` exists so callers can ask.

**Two dispatch paths, and only one is serialised.** CLI, serial and `POST /api/v1/cmd` share
`CommandExecutor._dispatch_lock`. **Six** modules bypass it entirely by calling the
controller through `getattr` — `gpio_input`, `analog_controls`, `rotary_encoder`,
`i2c/quad_rotary_controller`, `storage_preroll` and `simple_gui`. The controller itself has
9 lock-acquisition sites across 151 methods, so there is no internal fallback. **If your
change assumes two inputs cannot arrive at once, it is wrong.**

**One process owns the display.** DRM master is exclusive and cinepi-raw holds it. Hot-plugging
HDMI makes the GUI thread restart the capture process, because the preview binds its display
at process start and cannot rebind.

---

## 3. Where the map is thin

Stated so the next person knows what they are inheriting rather than discovering it.

- **`cinepi_controller.py`** — 151 methods, 94 public, on one class. Wide, not deep; average
  method is ~16 lines. This table's "primary edit" for anything controller-shaped lands here
  and offers little more guidance than that.
- **cinepi-raw's frame lifecycle** — `dng_encoder.cpp` changed by 687 lines between `main`
  and `dev`, and the review's code map describes the `main` version. Treat it as stale.
- **`settings_editor.html`** — 3706 lines, of which 1471 are JavaScript. Scanned for
  catalogue names and never read. Anything touching the settings editor's client behaviour
  is unmapped.
- **The `wifi_hotspot` triangle** — a service, an in-app manager and a superseded test copy.
  Only the test copy has been read.

---

## 4. Confidence

Every path and line number was read on `dev` in this repository. The "caught by" column
describes checks that exist and pass today — each was run. Nothing here was observed at
runtime and no Raspberry Pi was used.

The rows most likely to age badly are the ones whose checks are **"nothing"**: CLI commands,
services, sensors and HDMI layout. Those are the seams where the next drift will appear,
for the same reason all the previous drift did.
