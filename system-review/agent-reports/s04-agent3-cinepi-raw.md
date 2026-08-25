# S04 agent 3 scope — cinepi-raw dead code & build artifacts

**Run by the coordinator inline**, not a subagent (the S04 retry launched only agents 1
and 4; this scope was covered directly to avoid idle time). ID block F-200..F-249.

**Snapshot:** `/workspace/tiramisioux/cinepi-raw`, `main` @ 774402c, shallow read-only.
All citations from `grep -n` / direct file reads.

| id | severity | confidence | summary | evidence |
|---|---|---|---|---|
| F-200 | low | confirmed | `cinepi_manager.cpp` is a **0-byte file**; `cinepi_manager.hpp` is 37 LOC; nothing references either | `cinepi/cinepi_manager.cpp`, `cinepi/cinepi_manager.hpp` |
| F-201 | medium | confirmed | `add-redis-timecode.patch` and `add-tc.patch` are **byte-identical in their hunks** and only **partially applied** (15 of 41 substantial added lines present in tree) | repo root, `cinepi/cinepi_controller.cpp`, `cinepi/dng_encoder.{cpp,hpp}` |
| F-202 | high | confirmed | **`tc_cam0`/`tc_cam1` have two independent writers** computing the same timecode in two languages, last-write-wins | `cinepi_controller.cpp:334`, `redis_listener.py:909,914` |

---

## F-200 — `cinepi_manager` is an empty stub nobody references

```
cinepi/cinepi_manager.cpp    0 lines  (empty file)
cinepi/cinepi_manager.hpp   37 lines
```

Neither is in `cinepi/meson.build`'s source list, and grep across every `.cpp`/`.hpp`/
`meson.build` in the repo finds no reference to `cinepi_manager` outside the two files
themselves.

The name suggests an intended manager/supervisor abstraction that was never written. The
header declares an interface with no implementation and no consumer.

**Action:** delete both, or write the implementation. An empty `.cpp` beside a populated
`.hpp` is the most misleading of the three states.

**Note for the code map:** `CODE-MAP-cinepi-raw.md` §9 listed `cinepi_manager.*` as
"unread — is it live?". It is not live. That gap is now closed.

## F-201 — Two identically-named-different-filename patches, half applied

```
add-redis-timecode.patch   354 lines
add-tc.patch               357 lines
```

Both touch exactly the same three files (`cinepi/cinepi_controller.cpp`,
`cinepi/dng_encoder.cpp`, `cinepi/dng_encoder.hpp`).

Diffing the two files' hunk bodies against each other returns **zero differing lines** —
they are the same patch saved twice under different names, differing only in header
metadata.

Testing whether their content has landed: of 41 substantial (>25 char) added lines,
**15 are present in the tree and 26 are not.** The present ones include the timecode
formatting and the `tc_key` write (see F-202). The absent ones include a BCD-decode block:

```
/* use the last time-code produced by the encoder */
int hour  = ((tc_bcd[3] >> 4) & 0xF) * 10 + (tc_bcd[3] & 0xF);
int minute= ((tc_bcd[2] >> 4) & 0xF) * 10 + (tc_bcd[2] & 0xF);
...
```

So this is neither "applied" nor "pending" — it is a **partially-landed change with a
stale duplicate artifact left in the repo root**, which is the worst of the three states:
anyone who tries `git apply` will get a conflict and have no way to tell which hunks are
wanted.

**Confidence note:** "partially applied" is `confirmed` as a statement about line presence.
Whether the 26 absent lines were *deliberately dropped* or *never finished* cannot be
determined here — the clone is shallow with no history (STATE.md D2). PI-003 covers this
and should be re-scoped: it needs a full clone, not a Pi.

**Action:** delete one of the two files outright (they are identical). For the other, use
full history to determine whether the unlanded hunks are wanted, then apply or delete.

## F-202 — `tc_cam0`/`tc_cam1` are written by BOTH repos, in two languages

This is the most consequential thing in this scope, and it is a **fourth instance of the
duplicated-truth pattern** behind F-007, F-016 and F-027/F-028.

**cinepi-raw** (`cinepi/cinepi_controller.cpp:328-335`) formats and writes it:

```cpp
std::ostringstream tc;
tc << std::setw(2) << std::setfill('0') << hh << ':'
   << std::setw(2) << mm << ':' << std::setw(2) << ss << ':' << std::setw(2) << ff;

const char *tc_key = (options_->CamPort() == "cam1") ? "tc_cam1" : "tc_cam0";
redis_->set(tc_key, tc.str());
```

**cinemate** (`src/module/redis_listener.py:907-915`) computes it independently and writes
the same keys:

```python
tc1 = self.redis_controller.nanoseconds_to_timecode(int(timestamp), fps_user)
self.redis_controller.set_value(ParameterKey.TC_CAM1.value, tc1)
...
tc0 = self.redis_controller.nanoseconds_to_timecode(int(timestamp), fps_user)
self.redis_controller.set_value(ParameterKey.TC_CAM0.value, tc0)
```

(`nanoseconds_to_timecode` is `redis_controller.py:303`.)

### Why this matters

1. **Two writers, no coordination, last write wins** — on a value the operator reads during
   a take. Which one the GUI displays depends on ordering this review cannot determine.
2. **The two computations do not share inputs.** C++ formats from its own `hh/mm/ss/ff`
   derived in the frame path; Python derives from the `timestamp` stats field plus
   `fps_user`. Two algorithms, two clocks, one key. They can disagree.
3. **The docs pick a side and get it half wrong.** `docs/redis-keys.md:59` lists the source
   as "Cinemate (RedisListener)". cinepi-raw also writes it. → docs-drift, feed to S09.

### It also invalidates a method assumption — twice over

`tc_key` is held in a **variable**, so `redis_->set(tc_key, ...)` is invisible to the
literal-matching extraction used in S03 *and* to `harness/redis_key_diff.py`. This is the
second confirmed dynamic key after `cinepi_ready_<port>`.

**Consequence:** the harness's "19 shared" figure is a further undercount, and its README's
lower-bound caveat is not theoretical — it has now been demonstrated twice. The harness
should grow a check for `redis_->set(<identifier>, …)` call sites that reports them as
"dynamic, needs manual review" rather than silently skipping them.

**Action:** decide which side owns timecode and delete the other writer. Given cinepi-raw
owns frame timing and the sensor clock, it is the more defensible owner — but that is a
design call for the operator, not the review. Then fix `docs/redis-keys.md:59`.

**Overlap note for merge:** this finding sits in agent 4's category (duplicated truth
across the boundary). It is recorded here under F-202 because this scope found it. If
agent 4 reports the same duplication, **merge into F-202; do not double-count.**

---

## Scope covered / not covered

**Covered:** patch files · `cinepi_manager.*` · every `cinepi/*.cpp` against the meson
source list · the tc duplication.

**NOT covered — carry to a later pass:**
- Large commented-out blocks beyond the known one at `cinepi_controller.cpp:~380-405`
- The six inherited `rpicam-*` binaries in `apps/meson.build` — used by the install or not
- `utils.cpp`, `yuv2rgb.hpp`, `ifd_builder.hpp`, `raw_options.hpp`, `cinepi_frameinfo.hpp`,
  `cinepi_recorder.hpp` — liveness unchecked
- `cinepi_state.cpp` — still unread
