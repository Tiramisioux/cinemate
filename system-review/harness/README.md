# Harness

Runnable verification scripts. **No Pi, no hardware, no running camera** — everything here
must work on a laptop from a plain checkout.

| Script | What it does | Status |
|---|---|---|
| `redis_key_diff.py` | Diffs the two Redis key registries that form the cinemate↔cinepi-raw contract. Reproduces F-027. | working |

## `redis_key_diff.py`

```
python3 redis_key_diff.py [--cinemate DIR] [--cinepi-raw DIR] [--strict]
```

Needs a cinepi-raw checkout; defaults to `/workspace/tiramisioux/cinepi-raw`:

```
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 \
  https://github.com/Tiramisioux/cinepi-raw /workspace/tiramisioux/cinepi-raw
```

**Run it against `dev`.** Both repos are on `dev` (STATE.md D2). Check first:
`git -C /workspace/tiramisioux/cinepi-raw branch --show-current` must print `dev`.

Current output against **`dev` @ ea96f2d** (the numbers to baseline a CI ratchet on):

```
cinemate   ParameterKey members    : 84
cinepi-raw CONTROL_KEY_ macros    : 28
cinepi-raw direct/constexpr keys  : 8   (no macro name)
cinepi-raw total                  : 36
shared (the visible contract)     : 23
  -> 12 cinepi-raw keys unreferenced in cinemate
  ->  1 (audio_vu) referenced but outside the enum
```

For reference, `main` @ 774402c gave 84 / 32 / **19** shared / 12. The four extra shared
keys on `dev` are the HDR family, which landed on both `dev` branches together. **The
unreferenced count is 12 on both — the drift did not grow** (F-226).

`--strict` exits 1 when any cinepi-raw key is unreferenced in cinemate. Do **not** wire
that into CI until the current 12 are triaged (PI-008) — it would fail on day one. The
useful CI form is: run it, and fail only if the count *increases*.

### It already earned its keep

Writing this script caught an arithmetic error in F-027, which had said "11 keys" where
the reproducible figure is 12 key strings (11 distinct concerns — `raw_crop` and `rawCrop`
are one feature). A hand-counted finding drifted from the truth within one session; that is
the argument for having the tool at all.

### Known limitation — the numbers are lower bounds

Both registries are extracted by pattern matching, which cannot see dynamically
constructed keys. At least one exists and is load-bearing:

```
cinepi-raw  cinepi_raw.cpp:124     "cinepi_ready_" + options->CamPort()
cinemate    cinepi_multi.py:812    redis_controller.r.keys("cinepi_ready_*")
```

Treat a clean run as "no new drift *of the kind this script can see*", never as proof the
contract is intact.

## `gui_field_extract.py` — S07

Extracts the GUI field inventory mechanically: the 68 fields `simple_gui.populate_values()`
builds, which of them reach the web template, the Socket.IO event contract in both
directions, and the settings-editor action catalogue against `CinePiController`'s real
methods.

```
python3 system-review/harness/gui_field_extract.py --repo . [--format md|text|json]
```

Standard library only. Does not import the application, does not need redis, does not need
a Raspberry Pi.

**It independently reproduces F-118** — `set_log` is offered by the action catalogue and
does not exist on the controller — which makes it the second ready-made CI check in the
ledger, alongside `redis_key_diff.py`. See `deliverables/STANDARDS-PROPOSAL.md` §3.3; that
check should gate at zero, not ratchet, because there is exactly one known instance and it
is a bug.

Current output:

```
HDMI fields (lower bound)                68
  also named in the web template         48
  HDMI-only                              20
Socket.IO events emitted / handled        9 / 9   (no drift, either direction)
CinePiController public methods          94
Settings-editor catalogue entries        46
  absent on the controller                1  <-- set_log (F-118)
```

Two of its own bugs are documented in the source as warnings, because both are the kind
this review keeps making: it once walked every nested dict and over-counted fields, and it
once scanned two of the three Socket.IO emit sites and under-counted events.

## `design_token_diff.py` — S08

Compares the HDMI GUI's colour constants against the web GUI's CSS custom properties, and
reports three distinct states rather than one: an annotation that resolves and agrees, an
annotation that names a constant which does not exist, and a token with no stated link at
all.

```
python3 system-review/harness/design_token_diff.py --repo . [--strict]
```

Standard library only. `--strict` exits 1 on a drifted pair or a dangling annotation.
**Safe to gate at zero today** — nothing has drifted yet, which is exactly when a check is
worth adding.

Current output:

```
CSS colour custom properties            16
  annotation resolves, values agree      3
  annotation dangles                     0
  value match only (no stated link)     11
  not comparable (#000, lightgreen)      2
```

**It refined F-007.** The ledger recorded the colours as "synced only by a comment"; the
measurement is that only 3 of 16 have that comment. The other 11 are undocumented parallel
definitions. The sync mechanism is weaker than the finding claimed — see F-232.

It also caught one of its own bugs before publication: an earlier version read only
module-level constants and reported `--zoom-hi`'s `ZOOM_HIGHLIGHT_COLOR` annotation as
dangling. That constant is a function-local at `simple_gui.py:1226`. The script now walks
the whole tree, and the near-miss is documented in its docstring.

This is the **third** ready-made CI check in the ledger, after `redis_key_diff.py` and
`gui_field_extract.py`. All three are stdlib-only and need no hardware. See
`decisions/ADR-001-gui-harmonization.md` §6 — no unification step should land without its
check landing on the same commit.
