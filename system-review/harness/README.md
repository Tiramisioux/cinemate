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

Current output against `main` @ 774402c:

```
cinemate   ParameterKey members    : 84
cinepi-raw CONTROL_KEY_ macros    : 24
cinepi-raw direct/constexpr keys  : 8   (no macro name)
cinepi-raw total                  : 32
shared (the visible contract)     : 19
  -> 12 cinepi-raw keys unreferenced in cinemate
  ->  1 (audio_vu) referenced but outside the enum
```

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
