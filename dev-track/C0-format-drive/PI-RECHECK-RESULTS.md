# C0 Pi re-check — results

Live-Pi regression re-check of the format-drive control, plus capture of the two facts the
2026-08-26 run left unestablished. Protocol: `PI-RECHECK-PROMPT.md` (same directory).
Filled by the executing session, phase by phase, committed and pushed after each one.

Rules: state the prediction **before** running a step, the verdict after. Every number
carries the command it came from. Never rewrite a filled row — corrections get a dated note.

Status: **NOT STARTED** — update as phases complete.

- [ ] P0 preflight (incl. operator's written go-ahead on the scratch drive)
- [ ] P1 regression spot-check
- [ ] P2 format cycle NTFS → exFAT → ext4
- [ ] P3 the two unknowns
- [ ] P4 interlocks
- [ ] P5 handoff state for C1

Session start: — · Operator go-ahead for destructive steps (quote it): —

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

| Check | Result | Notes |
|---|---|---|
| Format row present on the active card | | |
| Present **only** on the active card | | |
| Select options exFAT / ext4 / NTFS | | |
| exFAT preselected | | |
| Styled (not unstyled fallback); `card-help` line present | | |
| Desktop browser render | | |
| Phone render (tap targets, stacking) | | |
| Confirm modal names label / device / size / fs | | |
| Cancel sends nothing (no `Dispatching 'format` in log) | | |

Prediction: — · Verdict: —

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

**What held:** —

**What did not:** —

**Is C0 still good after the settings-editor churn?** —

**Defects found (recorded, not fixed):** —

### Proposed `cinemate-handbook/lessons/hardware-log.md` entry (DRAFT — do not push)

```
## <date> — <one-line subject>

**Tested:** …

**Worked:** …

**Did not work:** …

**Why:** …

**Not established:** …

**Confirmed by:** …
```
