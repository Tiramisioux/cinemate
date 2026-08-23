# CineMate — working reference

Packaged for a `cinemate-dev` skill's `references/`. **Self-contained**: written to be useful
with no repository open. Distilled from an eleven-session audit of both repos (193 findings)
and the remediation that followed.

Line numbers are from `dev` as of 2026-08-23 and will drift; the *shapes* are what matter.

---

## 1. What the system is

Two programs on a Raspberry Pi, one camera.

**cinepi-raw** (C++, ~29k LOC) is the capture engine — a fork of `rpicam-apps`. It drives the
sensor, writes CinemaDNG frames, owns the HDMI preview, and runs a second process for audio.

**cinemate** (Python, ~20k LOC) is everything else — the on-camera GUI, a web GUI, a settings
editor, a CLI, GPIO/rotary/I²C inputs, storage management, and an installer.

**They communicate over Redis**, publishing on a channel called `cp_controls`. That channel is
the entire contract between them: 23 shared keys, plus about a dozen cinepi-raw touches that
cinemate never mentions. There is no other interface, no RPC, no shared library.

**Neither repository pins the other's revision**, so "which cinepi-raw goes with which
cinemate" is not recorded anywhere. Their `main` and `dev` branches differ by thousands of
lines including keys in that shared contract.

---

## 2. The five things that will bite you

**1. Reads do not come from Redis.** `RedisController.get_value()` returns a local cache kept
fresh by one background thread. If that thread stops, every read keeps succeeding and every
value is frozen — silently. Nothing in the system displays an error for it.

**2. Two dispatch paths, and only one is serialised.** CLI, serial and the web API all funnel
through one lock. Six other modules — GPIO, analog pots, rotary encoders, the I²C board,
storage pre-roll and the GUI itself — call the controller directly through `getattr` and take
no lock at all. The controller has almost no internal locking to fall back on. **Do not assume
two inputs cannot arrive at once.**

**3. Actions are dispatched by name, so a typo is silence.** Button and menu actions are
strings resolved with `getattr(controller, name)`. A name that does not resolve produces no
error, no log line, nothing — just a control that does nothing when pressed. This has shipped
at least once.

**4. One process owns the display.** DRM master is exclusive and cinepi-raw holds it. The
preview binds to a display at process start and cannot rebind, which is why hot-plugging HDMI
makes the GUI thread restart the whole capture process.

**5. The web GUI has no state of its own.** It consumes the HDMI GUI's value dictionary
verbatim over Socket.IO, and those updates are emitted from inside the framebuffer draw loop.
Add a field to the HDMI GUI and the browser gets it for free; stop the GUI thread and the
browser freezes with it.

---

## 3. Where things live

| | |
|---|---|
| entry point | `src/main.py` — one ~400-line function constructs everything in order, importing 27 modules directly |
| the state bus | `src/module/redis_controller.py` — `ParameterKey` enum (84 members) is the key registry |
| the controller | `src/module/cinepi_controller.py` — 151 methods on one class, 94 public. **Wide, not deep**: average method ~16 lines |
| HDMI GUI | `src/module/simple_gui.py` — a `Thread` subclass; `populate_values()` builds a 68-field dict, `draw_gui()` rasterises it via PIL to `/dev/fb0` |
| web GUI | `src/module/app/` — Flask + Socket.IO on :5000; control goes through `POST /api/v1/cmd` |
| settings editor | `src/module/app/settings_editor.py` + a 3,700-line template |
| recovery console | `services/cinemate-recovery/` — standard-library only, port 8080, deliberately isolated |
| config | `settings.jsonc` (comments are part of the product), `settings.schema.json` |
| installer | `cinemate-install.sh` — 1,900 lines, 27 named steps, idempotent by design |

---

## 4. Adding something — what else to update

The recurring failure in this codebase is one fact stated in two places that stop agreeing.
Every row below has a second edit.

| adding | also update | checked by |
|---|---|---|
| a Redis key | cinepi-raw's `CONTROL_KEY_*` if it crosses the boundary; `docs/redis-keys.md` | `tools/redis_key_diff.py` (ratchet) |
| a controller method | the CLI command table, the settings-editor catalogue (Python **and** its JavaScript copy), `docs/controller-methods.md` | `tools/gui_field_extract.py` (gates at 0) |
| a settings key | `settings.schema.json` (**required** — unknown keys are now rejected), the loader's defaults, `docs/settings-json.md` | schema test, `tools/docs_drift_check.py` |
| a GUI field | usually nothing — the browser gets it automatically | `tools/gui_field_extract.py` |
| a colour | the CSS custom properties in the web template | `tools/design_token_diff.py` (gates at 0) |
| a dependency | `requirements.txt` or `requirements-hardware.txt` — the installer reads both | the pytest job |
| a CLI command | the docs | **nothing** |
| a service | `services/Makefile`'s list, the installer, the docs | **nothing** |
| a sensor | `resources/sensors.json`, possibly `settings.jsonc` arrays | **nothing** |

The rows that say **nothing** are where the next drift will appear.

---

## 5. How code is written here

**Naming is settled** — 853 snake_case functions with zero exceptions, CapWords classes,
`SCREAMING_SNAKE` constants, one leading underscore for private. Do not deviate.

**A long-lived component subclasses `threading.Thread` and exposes `run()` and `stop()`.** A
one-off task uses `threading.Thread(target=..., daemon=True)`. Always give `join()` a timeout.
If you start it, stop it in `cleanup()`.

**Error handling has three legitimate shapes**, and they are distinguishable on sight:

```python
with contextlib.suppress(Exception):        # best-effort cleanup on something already failing
    ser.close()

except Exception:                            # a deliberate fallback that must stay visible
    logging.debug("...", exc_info=True)

except Exception:                            # something the operator needs to know about
    logging.exception("...")
```

Never `except Exception: pass`. Never bare `except:`. On the 12 fps redraw path use `debug`,
not `warning`, or you flood the log you are trying to inform.

**Logging**: `logging.<level>()` at module scope is the majority form. Never `print()` in
library code — it bypasses the file handler and the in-app log view. `basicConfig` only inside
`if __name__ == "__main__":`.

**Config**: never round-trip `settings.jsonc` through `json.dumps` — that deletes every
comment, and the comments are part of the product. Use `module.jsonc_edit.apply_updates()`.

**Comments**: there are zero `TODO`/`FIXME` markers in 20k lines, and 47 comments that record
*why* — including experiments that were tried and failed. **Do not delete them, and do not
enable a commented-out-code lint rule.** The best comments here justify a decision that would
otherwise look wrong.

---

## 6. The principles the project actually holds

Twelve, tested against code. The four that most change how you write:

**Fail visible, never silent.** Stated in the codebase itself. Also its most-violated
principle. The sharpened form: *the operator must never be shown a plausible wrong number.*

**Degrade in ladders whose last rung still answers.** The recovery console, the Wi-Fi hotspot
credential ladder, and standby-storage promotion all work this way — numbered fallbacks where
the final one still produces something usable rather than an error.

**State the reason in place, especially for a compromise.** Where this codebase explains why
a thing looks wrong, it is trustworthy; where it skips that, the same construct is a defect.

**Duplicated truth must be deleted, or carry a named reason *and* a check. A comment is not a
check.** Three hand-maintained sync comments exist and two are already wrong. This is the
principle the project most needs and least had.

---

## 7. Verification

The test suite is **fully portable** — it runs in a couple of seconds on a laptop with nine
pip packages and no Raspberry Pi. There is no hardware-only subset. Keep it that way.

Four drift checks run in CI, all standard-library only:
`redis_key_diff.py` · `gui_field_extract.py` · `design_token_diff.py` · `docs_drift_check.py`

**Write a test that fails against the unfixed code, and check that it does.** A test that
passes on broken code is worse than none.

**Nothing static can settle runtime behaviour on this system.** DRM composition, thread
races, memory growth under load and installer behaviour all need the actual device. If you
find yourself asserting one of those from reading, stop and write down the experiment instead.

---

## 8. Known gaps in this reference

- **cinepi-raw's frame lifecycle** — the DNG writer was substantially rewritten between
  branches; the audit's account of it describes the older one.
- **The settings editor's client JavaScript** — 1,471 lines, scanned but never read.
- **The Wi-Fi hotspot triangle** — a service, an in-app manager, and a superseded copy. Only
  the copy has been read closely.
