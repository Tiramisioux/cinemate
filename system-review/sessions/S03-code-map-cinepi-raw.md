# S03 — Architecture map, cinepi-raw (C++)

**Date:** 2026-08-18
**Phase:** A — Understanding (now complete for both repos)
**Outcome:** complete. 7 findings (F-027..F-033), 2 queue entries, one S02 error corrected.
**Deliverable:** `deliverables/CODE-MAP-cinepi-raw.md`

---

## 1. The cross-repo key diff — S03's headline

HANDOFF called this the highest-value thing S03 could produce. It was.

cinepi-raw keeps its own registry: 24 `#define CONTROL_KEY_*` macros in
`cinepi_state.hpp:23-52`, dispatched through a handler map (`cinepi_controller.cpp:353`)
on the **same `cp_controls` channel** cinemate publishes to. The published message *is*
the key name; the handler reads that key. So the contract is exactly the set of keys both
sides agree on.

**19 keys shared. 11 C++ keys with zero references anywhere in cinemate** (F-027):

| Group | Keys | Nature |
|---|---|---|
| A — handlers that can never fire | `awb`, `shutter_s`, `compress`, `thumbnail`, `thumbnail_size`, `raw_crop`/`rawCrop` | wired, correct-looking, unreachable |
| B — tuning knobs never set | `pll_kp`, `pll_ki`, `pll_deadband_us` | phase lock always runs at compiled defaults |
| C — telemetry nobody reads | `pll_phase_err_us`, `pll_req_dur_us` | written every PLL update |

**`awb` is the sharp one.** It reads like *the* white-balance control. cinemate sends
`wb`/`wb_user` and drives colour through `cg_rb` plus `--awb`/`--awbgains` launch flags, so
the handler at `cinepi_controller.cpp:409` is a vestigial second path to a job already
done elsewhere. The near-miss with `wb` is what makes it dangerous rather than merely
dead.

### I qualified this deliberately

"Unreferenced by cinemate" is **not** "dead". These keys are reachable with `redis-cli`,
and groups B and C read like an intentional manual tuning surface — set `pll_kp`, watch
`pll_phase_err_us`. That is a legitimate design, just an undocumented one. The finding is
precisely: *these keys are not part of the contract and nothing says so.* PI-008
discriminates, and its fastest step is asking the operator, not running anything.

### The counts are lower bounds — a caveat I had to add

Both registries were extracted by pattern matching, which cannot see dynamically built
keys. At least one exists and is load-bearing:

```
cinepi_raw.cpp:124    std::string key = "cinepi_ready_" + options->CamPort();
cinepi_multi.py:812   self.redis_controller.r.keys("cinepi_ready_*")
```

`cinepi_ready_<port>` is a live cross-repo handshake — cinemate glob-scans for it to learn
when each camera is up. It is in neither registry, neither set of docs, and is reached on
the Python side through the raw client. It is also a **fifth** Redis access pattern beyond
the four S02 catalogued.

So the honest statement is "at least 19 shared, at least 11 orphaned", and I wrote it that
way in the deliverable rather than presenting a clean census I cannot support.

---

## 2. Display ownership — the ADR-001 answer, from the code's own comment

`dualHdmiPreviewStage.cpp:5-18` states the constraint outright:

> *"DRM master is exclusive per GPU. Two independent cinepi-raw processes (one per sensor)
> therefore cannot both draw to the display — the second is forced to `--nopreview`. […]
> The SECONDARY instance publishes its lores YUV420 frame into a small System-V
> shared-memory segment. It never touches DRM. The PRIMARY instance owns the DRM preview
> directly […] composites […] and shows that canvas via DRM."*

Backed by `drm_preview.cpp:337` (`drmOpen("vc4")`) and `:350` (`drmIsMaster`).

**This settles KICKOFF §7 constraint 1 from source**, and it does something better than
settle it: it shows the project has *already hit this wall once* and engineered around it
with SysV shared memory rather than by sharing the display. Options D (kiosk browser) and
E (HTML→raster) must explain why they would not hit the same wall the second sensor hit.
That is a much stronger argument than "DRM is probably exclusive".

### What I could not settle, and made sure not to overclaim

cinepi-raw draws via DRM/KMS; cinemate's GUI writes the **legacy fbdev node** directly
(`framebuffer.py:84,136`). Two different kernel interfaces to one display, which is why
they coexist at all. But **z-order, whether the GUI is a real overlay plane or is racing
the same scanout, and mode-change behaviour are not inferable from source.** I queued that
as PI-009 and marked it as blocking S08 — KICKOFF §7 constraint 2 asks exactly this, and
answering it from reasoning would be the precise failure mode §2.4 warns about.

PI-009 step 5 is the decisive experiment: stop one renderer, see whether the other still
paints, then reverse.

---

## 3. Build graph — the loose end S01 left, plus a large dead file

S01 flagged that `cinepi_audio_capture.cpp` and `lj92.c` were absent from
`cinepi/meson.build`'s source list. Two different answers:

- **`cinepi_audio_capture.cpp` builds its own executable** (`meson.build:56-59`). S01 saw
  only the first source list. So **audio capture is a separate process**, supervised by
  `CinePISound` via `popen`/`fork`/`execl` and torn down with `pkill -f` on a cmdline
  pattern (F-033). That is a materially different architecture from what the census
  implied.
- **`lj92.c` + `lj92.h` are entirely dead** (F-029) — in no source list, included only by
  itself, `lj92_encode`/`open`/`decode` with zero callers. **1218 LOC, the largest dead
  file in either repo.**

Also found: cinepi-raw wires `phase_lock_core_test` into `meson test`
(`meson.build:62-67`). So a working test-runner pattern already exists in the repo pair;
cinemate simply has no runner for its 27 files. F-030 records this so S06 can point at a
local precedent instead of making a generic recommendation.

---

## 4. I corrected an error in the S02 deliverable

S02's `CODE-MAP-cinemate.md` listed **keyboard** as one of four live direct-call control
surfaces. It is dead: class `Keyboard` is never instantiated and `module.keyboard` is
never imported anywhere in the repo (F-031). Path B has **three** live surfaces, not four.

Fixed in the S02 map (both the diagram and the prose, with a note that the earlier
revision was wrong) and F-025's evidence list updated. I found it only because the
dependency audit in §5 turned up `keyboard` as an installer package with zero importers,
which prompted a check of the local module of the same name.

---

## 5. A dependency finding that sharpens F-003 considerably

Chasing `sysv_ipc` — which the dual-HDMI comment explains is a *C++* mechanism — I checked
whether Python uses it at all. It does not: `sysv_ipc` appears only in
`cinemate-install.sh:927` and in the docs that mirror it.

Widening the check across the installer-only packages: **7 of 11 have zero Python
importers** (F-032):

| Package | Reality |
|---|---|
| `sysv_ipc` | SysV IPC is used by the C++ dual-HDMI stage, not Python |
| `keyboard` | shadows the dead local `module/keyboard.py`; nothing imports either |
| `luma.oled` | OLED actually uses `adafruit_ssd1306` (`i2c_oled.py:5`) |
| `rpi_hardware_pwm` | PWM actually uses `lgpio` via `rpi_gpio_wrapper` (`gpio_output.py:25`) |
| `watchdog`, `inotify_simple`, `pigpio-encoder` | no importers found |

So F-003 is not just "two lists diverged" — **the installer installs packages nothing
uses**, and in two cases installs a library for a feature that is implemented with a
different library. S10 should treat this as the more interesting half of F-003.

---

## 6. Judgement calls and what I left undone

**Did not trace `dng_save()` or the metadata path.** The metadata path (timing → DNG tags)
was explicitly in S03's brief and I did not do it — `dng_encoder.cpp` is 1521 LOC and I
reached the budget line with the key diff, display ownership and the build graph done.
Those three were the higher-value items and two of them unblock other sessions. The
metadata path blocks nothing yet. Recorded in the deliverable §9 and carried to HANDOFF.

**Did not build the key-diff harness script.** F-027's real fix is a script that parses
both registries and fails when they drift — it would turn this finding into a check that
cannot silently regress. It belongs in `harness/` and needs no hardware. I left it for
S07 (which owns `harness/`) rather than starting it here; it is now the first item in the
handoff's "cheap and high-value" list.

**No subagents again.** Same reason as S02: each finding came from chasing the previous
one's loose end. S04 is the fan-out session and is genuinely suited to it — the redundancy
sweep is embarrassingly parallel in a way these traces were not.

---

## 7. Citation discipline

The handoff warned about deriving line numbers from `sed` window arithmetic. I did it
anyway in the first draft of the deliverable and had to fix four citations
(`AnalogueGain` :414→:405, `AwbEnable` :411→:413, `ColourGains` :427→:430,
`meson.build` :9,17→:8,16). Caught by re-grepping every derived citation before commit,
which is now a step I would recommend making routine rather than a warning to remember.
