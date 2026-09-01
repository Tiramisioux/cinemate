# C0 Pi re-check — results

Live-Pi regression re-check of the format-drive control, plus capture of the two facts the
2026-08-26 run left unestablished. Protocol: `PI-RECHECK-PROMPT.md` (same directory).
Filled by the executing session, phase by phase, committed and pushed after each one.

Rules: state the prediction **before** running a step, the verdict after. Every number
carries the command it came from. Never rewrite a filled row — corrections get a dated note.

Status: **PARTIAL — desk-only pass done, Pi unreachable this session.**

- [ ] P0 preflight — **blocked**, no Pi connectivity this session
- [x] P1 regression spot-check — **desk-level only** (source read against `origin/dev`
      HEAD `4e11b426`), not a live browser/phone render. See caveat in P1.
- [ ] P2 format cycle NTFS → exFAT → ext4 — **blocked**, requires the Pi
- [ ] P3 the two unknowns — **blocked**, requires the Pi
- [ ] P4 interlocks — **blocked**, requires the Pi
- [ ] P5 handoff state for C1 — **blocked**, requires the Pi

Session start: 2026-09-01 · Operator go-ahead for destructive steps: not sought — no
destructive step was attempted this session (Pi unreachable; see below).

**Why blocked:** `cinepi.local` did not resolve on this workstation this session
(`ssh`/`ping` both failed to resolve the hostname; the prepared `pi_ssh.sh` helper hung
and was killed). No SSH, no `curl` to the settings editor, no destructive step was
possible or attempted. Per the operator's explicit instruction this session, the Pi was
not chased further (no alternate hostname/IP tried, no retry loop). P0/P2–P5 remain
exactly as prepared, untouched, for a session that has Pi network access.

---

## P0 — Preflight

| Item | Value | Source |
|---|---|---|
| Pi reachable / host | | |
| `uname -r` | | |
| `MemTotal` | | `free -b` |
| Pi cinemate branch @ commit | | `git -C /home/pi/cinemate log --oneline -1` |
| Contains `e54e691b`? | | `merge-base --is-ancestor e54e691b HEAD` |
| cinemate running as | | |
| `/media/RAW` device / fstype / size | | `findmnt -no SOURCE,FSTYPE,SIZE /media/RAW` |
| Takes present before we start | | `ls /media/RAW` |
| Liveness probe (invalid fs → 400) | | `curl … -d '{"filesystem":"vfat"}'` |

Prediction: — · Verdict: —

---

## P1 — Regression spot-check

The reason this session exists: `settings_editor.{py,html}` changed repeatedly after C0 was
verified. Does the control still render and behave?

**Caveat: this pass is desk-only** — a source read of `origin/dev` HEAD `4e11b426`
(`git show origin/dev:src/module/app/templates/settings_editor.html` /
`settings_editor.py`), not a live browser session. It proves the *code* still does what
P1 expects; it cannot prove actual on-device rendering, CSS cascade, or touch behavior.
Rows marked "desk (source)" below are downgraded from what a live check would give —
treat as **probable**, not confirmed-on-hardware, until re-run live.

Prediction (before reading source): the ledger's changelog (control-row layout, phone
stacking, "free mode"→"free stepping" rename, `format_drive` `no_arg: required`
hardening) touched surrounding code, not this control directly, so the control should
still be structurally intact.

| Check | Result | Notes |
|---|---|---|
| Format row present on the active card | ✅ desk (source) | `renderStorageCards()`, `settings_editor.html:3914` — `s.active ? '<div class="storage-format">'…` |
| Present **only** on the active card | ✅ desk (source) | Same ternary; empty string for standby cards |
| Select options exFAT / ext4 / NTFS | ✅ desk (source) | `settings_editor.html:3916-3920` — `<option value="exfat" selected>`, `ext4`, `ntfs` |
| exFAT preselected | ✅ desk (source) | `selected` attribute on the `exfat` `<option>` |
| Styled (not unstyled fallback); `card-help` line present | ✅ desk (source) | `.storage-format{ display:flex; … }` at `settings_editor.html:763`; `<p class="card-help">Erases the whole drive…</p>` follows the control |
| Desktop browser render | ⬜ not verified | requires a live Pi session |
| Phone render (tap targets, stacking) | ⬜ not verified | requires a live Pi session |
| Confirm modal names label / device / size / fs | ✅ desk (source) | `wireStorageFormat()`, `settings_editor.html:3939-3941` — `'Format ' + s.label + ' (' + (s.device…) + ', ' + formatBytes(s.total_bytes) + ') as ' + fs + '? Every take on it is permanently erased.'` — matches spec verbatim |
| Cancel sends nothing (no `Dispatching 'format` in log) | ✅ desk (source) | `showConfirm()`/`closeConfirm()`, `settings_editor.html:4206-4227` — the `fetch()` call lives only inside the `onYes` callback passed to `showConfirm`; Cancel/scrim-click/Escape all route through `closeConfirm(true)`, which only ever invokes `pendingConfirmCancel` (`null` here) — no code path reaches `fetch` without the OK click |

Verdict: the four "desk (source)" structural claims and the confirm-modal/cancel-safety
logic all check out unchanged against the spec — **no regression found at the source
level**. This does **not** discharge the two rows requiring a live render, and does not
touch P2–P5 (format cycle, the two unknowns, interlocks, handoff state) — those still
need the Pi.

---

## P2 — Format cycle (NTFS → exFAT → ext4)

| # | Requested fs | `findmnt` FSTYPE after | Pane `filesystem` after | Label | Capacity | Takes | Wall-clock | Toast text correct? |
|---|---|---|---|---|---|---|---|---|
| 1 | ntfs | | | | | | | |
| 2 | exfat | | | | | | | |
| 3 | ext4 | | | | | | | |

Prediction: — · Verdict: —

Anything unexpected (card flicker, stale render, error toast, retry needed): —

---

## P3 — The two unknowns

**Unknown 1 — which fstype string does NTFS report?**

- `findmnt -no FSTYPE /media/RAW` → —
- Pane / `storage_summary()` `filesystem` value → —
- Therefore the endpoint matched on: `ntfs` / `ntfs3` / `fuseblk` (circle one): —
- Do the two sources agree? If not, say which is which and why it matters: —

**Unknown 2 — how long does a format hold the dispatch lock?**

| Requested fs | Lock held (s) | Measured how |
|---|---|---|
| ntfs | | |
| exfat | | |
| ext4 | | |

- Command sent during an in-flight format: — · reported `busy`? —
- Approx. when normal dispatch resumed: —
- Is the observed duration consistent with the plan's "worst case ≈ 2.5 min" estimate? —

Prediction: — · Verdict: —

---

## P4 — Interlocks

| Check | Result | Evidence |
|---|---|---|
| Format attempted while recording → 409 | | |
| Recording undisturbed (kept writing, stopped cleanly, frame count intact) | | |
| Normal dispatch recovers after the busy period | | |
| `storage-automount.service` mount fight after format? | | `journalctl -u storage-automount --since '-5 min'` |
| `findmnt` still stable a minute later | | |

Prediction: — · Verdict: —

---

## P5 — Handoff state for C1

| Item | Value |
|---|---|
| Filesystem | (expect `ext4`) |
| Mounted at `/media/RAW`, label `RAW` | |
| Capacity / free bytes | |
| Takes on drive | (expect 0) |

**Ready for C1 Phase 0?** — · If not, what is in the way: —

---

## Close-out

**What held:** The desk-only portion — a source read of `settings_editor.py`/`.html` at
`origin/dev` HEAD `4e11b426` against the P1 checklist. The format endpoint logic
(`_FSTYPE_ALIASES`, the 400/409/503/500 paths, the post-dispatch remount check) and the
control's markup, wiring, confirm-modal message, and cancel-safety are all structurally
unchanged from what was verified at `e54e691b`. No regression found in source.

**What did not:** The Pi (`cinepi.local`) did not resolve on this workstation this
session — `ssh`/`ping` failed to resolve the hostname, and the prepared `pi_ssh.sh`
helper hung and was killed. **P0, P2, P3, P4, and P5 were not attempted** — no live
render, no format cycle, neither unknown captured (NTFS fstype string, dispatch-lock
duration), no interlock check, no handoff-state confirmation for C1. Nothing destructive
was run; the operator's written go-ahead was never sought because no destructive step
was reachable.

**Is C0 still good after the settings-editor churn?** Probably, at the source level —
but this is **not** a substitute for the live regression spot-check the ledger asked
for, and none of the hardware-only facts (P2–P5) are established. Re-run this session
with real Pi connectivity to close it out.

**Defects found (recorded, not fixed):** None found in the desk-only pass.

### Proposed `cinemate-handbook/lessons/hardware-log.md` entry (DRAFT — do not push)

Not written — no hardware result to record. A desk-only source read is not a hardware
finding and doesn't belong in the hardware log per that file's own entry contract.
