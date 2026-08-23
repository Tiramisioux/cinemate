# CineMate style — how code is written here

**Session:** S11b · **Derived from the code**, with citations, not from general practice
**Companion:** `CINEMATE-PHILOSOPHY.md` (why), `ENTRY-POINTS.md` (where) · **Pi used:** no

Everything below was measured or read on `dev`. Where a rule is already near-universal the
count says so; where the codebase disagrees with itself, that is stated rather than
smoothed over. **Rules with no evidence behind them are not in this document.**

Some of this landed as part of the review's own remediation (PR #131) and is marked ✱.

---

## 1. Naming — settled, leave it alone

| | |
|---|---|
| functions and methods | **853 snake_case, 0 exceptions** |
| classes | 52 CapWords · 6 lowercase, of which 5 are `_`-prefixed private helpers |
| module-level constants | `SCREAMING_SNAKE` — `DROP_WARNING_COLOR`, `RAM_LIMIT_PERCENT`, `MAX_ATTEMPTS` |
| private | a single leading underscore, used consistently for both methods and helper classes |

**There is exactly one genuine outlier in the whole tree**: `i2cOledSettings`
(`i2c/i2c_oled.py:9`). That is a settled convention by any reasonable standard — do not
spend review time here.

The one thing worth *adding*: `_`-prefixed classes (`_ToneOutput`, `_RateLimiter`,
`_SoftwarePWMToneOutput`) mark "internal to this module", and it reads well. Keep doing it.

---

## 2. Module shape

A module is one concern, exporting one class named after it. `ssd_monitor.py` →
`SSDMonitor`, `usb_monitor.py` → `USBMonitor`, `redis_controller.py` → `RedisController`.
48 modules, no packages beyond `app/` and `i2c/`, and `main.py` imports 27 of them directly
with no composition layer in between.

**That flatness is a real property, not an accident**, and it is why the boot sequence is
legible: one 400-line function constructs everything in order. It is also why `main.py` is
long. Do not add an intermediate layer without deciding that trade deliberately.

**The exception worth copying** is `cinemate-recovery.py`, which is standard-library-only by
a rule stated at the top of the file, with the reason given:

> *"'The venv is broken' and 'redis is down' are supported failure modes that this console
> exists to survive; every import it makes is another way for it to die exactly when it is
> needed."*

When a module has a constraint that is not obvious, say it at the top like that.

---

## 3. Threading — one shape, follow it

Two patterns, and they are not interchangeable:

**A long-lived component subclasses `threading.Thread`** and exposes `run()` and `stop()`.
Eight do; **seven have both**. `analog_controls.py` has `run()` and no `stop()` and is the
outlier, not the precedent. `simple_gui` has the fullest form — `request_stop()` to signal,
`stop()` to signal and join.

**A one-off task uses `threading.Thread(target=..., daemon=True)`.** All six ad-hoc threads
in `main.py` pass `daemon=True`; none omits it.

Three rules the code earned the hard way:

1. **Give every `join()` a timeout.** Shutdown must not hang on a thread wedged in a
   blocking poll. `main.py`'s `join_thread()` helper does this; `SSDMonitor.stop()` did not,
   and also joined a thread whose creation is commented out ✱.
2. **If you start it, stop it in `cleanup()`.** Four components were never stopped there ✱.
3. **A `daemon=True` thread that dies takes its function with it and nothing notices.**
   That is how the redis listener could freeze all live state silently ✱. If a thread is
   load-bearing, expose a liveness check — `RedisController.listener_alive()` ✱.

---

## 4. Error handling — the project's own principle, mechanised

The rule is stated in the code, at `storage_profiles.py:41-49`: **fail visible, never
silent.** 337 handlers across ~19,800 lines; the ones that broke the rule are now fixed ✱,
and `ruff` enforces it going forward via `E722`, `S110`, `S112`.

**Three legitimate shapes, and they are distinguishable:**

```python
# 1. Best-effort cleanup on something that has already failed.
#    Say it is deliberate, syntactically.
with contextlib.suppress(Exception):
    ser.close()

# 2. A deliberate fallback. Keep the fallback; do not keep the silence.
try:
    cpu_load = Utils.cpu_load()
except Exception:
    logging.debug("cpu_load unavailable; keeping the last value", exc_info=True)

# 3. Something the operator needs to know about.
except Exception:
    logging.exception("Redis subscriber %s failed; continuing with the rest", name)
```

**Never `except Exception: pass`.** If the silence is intentional, shape 1 says so. If it is
not, it is a defect.

**Never bare `except:`** — it swallows `KeyboardInterrupt` and `SystemExit`, which is how
Ctrl-C during an RTC read did nothing ✱.

**Debug, not warning, on a hot path.** Four of the fallbacks above sit on the 12 fps redraw
loop; at `warning` they would flood the log they exist to inform.

**And the pattern to copy when dispatching to callbacks** — guard each one and continue,
as `CinePiController._notify_resolution_change` has always done:

```python
for fn in list(self._handlers):
    try:
        fn(data)
    except Exception:
        logging.exception("...")
```

---

## 5. Logging

`logging.<level>()` at module scope is the majority form — **615 calls against 112** using a
named logger. Both work; **match the file you are in** rather than the repo, and do not
convert a file wholesale as a side effect of another change.

- **Never `print()` in library code.** It bypasses the file handler, the colour formatter and
  the in-app log queue, so it does not reach the log the operator actually reads. A
  `__main__` block is the exception ✱.
- **`basicConfig` only inside `if __name__ == "__main__":`.** `wifi_hotspot.py:749` is the
  only module that gets this right; importing anything that calls it at module scope
  hijacks the root logger.
- **`exc_info=True` when you are logging inside an `except`.** A message without the
  traceback moves the silence rather than removing it.
- Interpolation is mixed — 233 f-string against 161 lazy-`%`. Prefer lazy `%` in
  `logging.debug` on hot paths, where f-strings format even when the level is off.

---

## 6. Configuration

`settings.jsonc` is the contract with the operator, **and its comments are part of the
product** — 74 of its 386 lines. Two consequences that are easy to get wrong:

- **Never round-trip it through `json.dumps`.** That drops every comment. Use
  `module.jsonc_edit.apply_updates()`, which rewrites only the spans whose values changed ✱.
- **Add the key to `settings.schema.json` too.** `additionalProperties` is `false`
  throughout ✱, so an undescribed key is now rejected by editors — which is the point, but
  it means the schema is no longer optional.

Read config through `config_loader`. Defaults live in its `setdefault` chain **or** in the
schema — pick one deliberately, because four registries already exist and eleven keys
disagree between them.

Use `ParameterKey` for redis keys rather than raw strings. It is convention, not enforcement
— `set_value()` accepts anything — so the convention is all there is.

---

## 7. Comments — the best thing about this codebase

**Zero `TODO`/`FIXME`/`XXX`/`HACK` in ~19,800 lines.** The comments that exist are
load-bearing prose, and 47 of them explain *why* something is the way it is, including two
experiments that were tried and failed:

> `ssd_monitor.py:1122-1125` — records that 1 MB exFAT clusters break the macOS driver, so
> nobody re-tries it.

**This is the house style and it should be defended.** `ruff.toml` forbids `ERA001`
(commented-out code) in a written-out comment rather than by omission, so nobody adds the
rule later without reading why: it would delete the most valuable prose here and the diff
would look like housekeeping.

Three rules that follow from what the good comments do:

1. **State the reason in place, especially for a compromise.** `cinemate-install.sh`
   duplicates `strip_jsonc` and says why in the same breath — *"this heredoc runs under the
   system python3, outside the venv."* Where the codebase does this, the code is
   trustworthy; where it skips it, the same construct is a defect.
2. **A comment is not a check.** Three hand-maintained comments that index a duplicate
   elsewhere have drifted, and two of them are now wrong. If two things must agree, write a
   check — there are four in `tools/`.
3. **Comments rot where `docs/` does not.** The published site scored zero broken links and
   zero bad citations; a dead setting name survives in a docstring and a comment. If a
   comment is worth keeping accurate, consider whether it belongs in `docs/`.

---

## 8. Tests

381 tests across 27 files, **all portable** — the suite runs in about two seconds with nine
pip packages and no Raspberry Pi. Keep it that way: a test that needs hardware cannot run in
CI, and CI is the only thing that runs these at all.

The house pattern is `unittest`, with hardware modules stubbed via `sys.modules.setdefault`
before the import under test. **Be careful with that** — `sys.modules` is process-wide and
nothing cleans up, so a stub installed by one test decides what that module means for the
whole run.

**Write the test so it fails against the unfixed code, and check that it does.** Every fix
in the review's remediation was verified in both directions. A test that passes on broken
code is worse than none.

---

## 9. What this document does not cover

- **cinepi-raw's C++.** It has `.clang-format` and seven `meson test` targets. Its
  conventions are its own; the seam that matters is the redis key contract.
- **Shell.** Already the best-maintained code here — `shellcheck` clean across all 11
  scripts ✱, and `cinemate-install.sh`'s idempotency is designed and documented. Read it
  rather than a style guide.
- **Type hints.** Deliberately not adopted wholesale; the argument and the two boundaries
  worth annotating are in `STANDARDS-PROPOSAL.md` §5.
- **Formatting.** `ruff format` is not adopted. `.editorconfig` ✱ is, and `E501` is off on
  purpose.

## 10. Confidence

Every count is reproducible: naming and threading figures from `grep`/AST over `src/`,
handler counts from `ruff`, comment counts from the readability pass. Items marked ✱ are in
PR #131 or #130 and **have not run on a Raspberry Pi**.
