# STATE

**Read this first, every session.** Then read the last `sessions/S##-*.md`, then do what
`PLAN.md` says is next.

- **Last session:** S07 (2026-08-23) — GUI inventory **delivered**:
  `deliverables/GUI-INVENTORY.md`, `deliverables/GUI-STATE-MODEL.md`,
  `harness/gui_field_extract.py`, 22 findings, 2 PI items. See
  `sessions/S07-gui-inventory.md`.
- **Then S07b (2026-08-23), on operator instruction — both repos are now on `dev`.**
  cinemate already was; cinepi-raw was on `main` and was 45 files / +7164 lines behind.
  7 findings, D2 rewritten, correction banners on `CODE-MAP-cinepi-raw.md` and `CENSUS.md`.
  See `sessions/S07b-dev-branch-reconciliation.md`. **Check the branch before trusting any
  cinepi-raw figure.**
- **Then S08 (2026-08-23) — ADR-001 **proposed**: `decisions/ADR-001-gui-harmonization.md`,
  `harness/design_token_diff.py`, 8 findings, PI-016. See `sessions/S08-adr-001.md`.
- **Then S09 (2026-08-23) — docs drift **delivered**: `deliverables/DOCS-DRIFT-REPORT.md`,
  `harness/docs_drift_check.py`, 12 findings. See `sessions/S09-docs-drift.md`.
- **Then S10 (2026-08-23) — install drift **delivered**:
  `deliverables/INSTALL-DRIFT-REPORT.md`, 4 findings, **F-003 decided (option 2, reversing
  S01's lean)**. See `sessions/S10-install-drift.md`.
- **Then S11a (2026-08-23) — `cinepi_controller.py` **traced** (the six-times-deferred item)
  and `deliverables/CINEMATE-PHILOSOPHY.md` **delivered**. 4 findings, **PI-007 step 1
  discharged with no hardware**. See `sessions/S11a-controller-and-philosophy.md`.
- **Then S12 (2026-08-23) — `deliverables/REMEDIATION-PLAN.md` **delivered**, on operator
  request, ahead of S11b. 8 batches ordered by risk, **6 ready-to-paste handoff prompts**.
  The analysis phase is closed.
- **Then: REMEDIATION IS UNDER WAY.** On operator instruction, batches B2/B3/B4/B6 are
  implemented on feature branches off `dev` in both repos — **five draft PRs**, four of
  them with green CI. See "Remediation status" below.
- **Then S11b — complete.** `ENTRY-POINTS.md`, `CINEMATE-STYLE.md`, `SKILL-PAYLOAD.md`.
- **THE REVIEW IS COMPLETE.** All twelve plan entries delivered, 193 findings, 15
  deliverables. Every remediation batch that can be executed without hardware is merged into
  five draft PRs.
- ~~**The only remaining work is B5 — the Pi session.**~~ **B5 is DONE (2026-08-24).** All
  16 queued items closed across two sessions (2026-08-23, 2026-08-24). Digest:
  `PI-RESULTS-2026-08-24.md`.
- **Then: RECONCILIATION (2026-08-25).** The ledger and 15 deliverables were written entirely
  pre-hardware. This session reconciled `FINDINGS.md`, the citing deliverables, and
  `ADR-001-gui-harmonization.md` against the Pi results — see "Ground truth from the Pi
  session" below for what actually changed, and the git log on this branch from
  `25615d8` onward for the full diff. **Read that section before trusting any pre-2026-08-24
  claim about F-001, F-016, F-025, F-027, F-172, F-182, F-204, F-253, F-259, or ADR-001's RAM
  argument** — each has a stated correction now.
- **After that:** B7 (ADR-001 steps 1–3), which should follow B3 landing. ADR-001's
  conclusion (reject D/E, adopt C) is unchanged by the reconciliation, so B7 can proceed on
  the existing plan.
- **Then: THE FIX ROUND + THE LAST REMEDIATION PR (2026-08-25).** All five originally-cleared
  PRs merged (#131, #130, #132, #134, cinepi-raw #59). F-283/F-284/F-286 (core) fixed and
  merged (#135, #136, #137); F-286's tie-break follow-up and F-285's full fix are open PRs
  (#139, #140). **The venv was removed** — an operator architecture decision, not a
  remediation fix — landing as #138 (F-279..F-282) then #133, the **last remediation PR**,
  rebased onto the new mechanism and merged. **B2, B3, B4, B5, B6 are now all complete.**
  Full detail, including three desk diagnoses that needed correction on hardware (a good
  outcome, not a bad one) and the venv decision's two follow-up checks: `PI-RESULTS-2026-08-25.md`.
  Remaining planned work: B1 (docs, zero risk, no hardware), B7 (preconditions now all met),
  the F-285 design decision (now implemented, #140 pending merge), and B9/B10 (added below).
- **Then: B1, B9 desk work, and B11 (2026-08-25).** B1 merged (#141). B9's five desk commits
  merged (#143, `work/b9-desk-work`). **B11** — eleven field-reported defects, the first batch
  that didn't come from reading — landed as five branches/PRs, all merged: #142 (B11.1/B11.2),
  #144 (B11.3/B11.4/B11.6), #145 (B11.5), #146 (B11.8), #148 (B11.7). The ledger branch itself
  (B11/B13/B14 plans + 19 findings, then a second commit with 7 more, F-307..F-313, documenting
  what B11 implementation corrected) merged via **PR #149**. **`origin/dev` is now `7c8b84e7`,**
  21 commits ahead of where this ledger branch's own history stops — **fast-forward before
  trusting `dev`'s tip from this branch's git log alone.**
- **The ledger branch is now fully merged into `dev` (twice — #129, then #149) and has no
  content `dev` doesn't already have.** Continuing to commit ledger updates directly onto it
  would just be committing onto `dev` under another name. New ledger/batch work now cuts a
  fresh branch off `origin/dev` per batch, same as every code batch — see "the failure mode to
  avoid" note from the operator: six branches with no PR is nothing checked, nothing mergeable.
- **Open PR #147** (`merge-b11-into-dev`, base `13ab022` — the *pre-B11* `dev` tip) **appears
  superseded**: every commit it carries landed individually via #142/#144/#145/#146/#148
  already. Its `ruff` check is failing. Not closed by this session — flag for the operator
  rather than closing PRs unasked.
- **Findings:** 228 rows (F-001..F-313, with gaps — see free ID blocks below). F-307..F-313
  (7 rows) were missing from `REMEDIATION-PLAN.md`'s batch section — restored in this session's
  branch (`review/b0-coverage-invariant`): F-307/309/310/311/312 were fixed during B11
  implementation (verified against `dev`, not just the finding text — F-311 in particular:
  `applyActionToSlot()` really does default to `''` on `dev` now, comment cites the exact bug);
  F-308 refutes F-289's mechanism (avahi was already present on the test device) without itself
  needing a fix; F-313 is a citation correction with nothing downstream to correct. **F-289 is
  reopened, not closed** — B11.2's hardening shipped but isn't a confirmed fix for the original
  field report; root cause needs operator input, queued as **PI-017**.
- **Then: B13 extended, B10.3/4/5, B7 step 1, and B10.1/7/8 (2026-08-26), four PRs, all
  green CI at last check:**
  - **#151 — B13, extended past its original scope** to cover B11.4/.5/.7/.8 drift the
    batch predates: GPIO/rotary docs, the new per-mode fps-ceiling settings, web GUI
    scaling, the restart mechanism (no doc drift found there — already accurate), plus
    the original B13.1–B13.7. Also closed F-265/F-266 with a real installer-step
    correspondence table and found + fixed real gaps a manual install would have hit
    (`run_cinemate.sh`/the config.txt apply helper never created, avahi never installed —
    same gap as F-289/F-308, `cinemate-recovery` missing from the services section).
    cinepi-raw's own README fix (`python-pip`→`python3-pip`, F-304) is a separate PR,
    **cinepi-raw #61**, open.
  - **#153 — B10.3/B10.4/B10.5.** F-175/F-176 were already fixed on `dev` when checked;
    F-177/F-195/F-021/F-111/F-167/F-014/F-229/F-248 were genuinely open and fixed here
    (F-167 in particular: `rotary_encoders`/`quad_rotary_controller.encoders` had zero
    schema validation, now do, verified against all three shipped settings files plus two
    hand-built typo-rejection tests). F-033 and F-168/F-170 deliberately left open — no
    hardware to verify a `pkill` pattern change, and a ~1000-call-site logging-idiom
    unification is more than one pass can review carefully.
  - **#155 — B7 step 1 only** (design tokens, F-007/F-232/F-233). `src/module/
    design_tokens.py` is now the one place the 14 shared HDMI/web colours live;
    `design_token_diff.py` checks the CSS against it by exact match instead of guessing
    by value. **B7.2–B7.4 (lift the section spec into data, web backend reads it, unify
    the layout primitives) are NOT done** — real rendering-architecture changes with no
    way to visually verify them in this environment (no Pi, no browser against a live
    camera). Left for a session that has one or the other.
  - **#156 — B10.1/B10.7/B10.8.** All 228 findings dispositioned (`fixed`/`guarded`/
    `accepted`/`superseded`/`strength`), verified against the tree rather than the plan —
    a real block had drifted in both directions since REMEDIATION-PLAN.md was written
    (see the commit message for the specific corrections). `tools/
    findings_disposition_check.py` gates it in CI now.
  - **All four PRs (#151, #153, #155, #156) were open, CI-green, not yet merged** at the
    end of this session. Several `fixed` dispositions in #156 depend on the other three
    landing as authored — re-triage those rows if any of the three change materially
    before merge. **#147** (`merge-b11-into-dev`) still looks superseded by the
    individually-merged B11 PRs and was flagged, not closed, for the operator.
- **Open decisions:** **ADR-001 is written and `proposed`** —
  `decisions/ADR-001-gui-harmonization.md`. Reject D and E; adopt C reached through B; fix
  F-204 first. Surface 4 excluded permanently. **Reconciled 2026-08-25**: constraint 2
  (PI-009) and constraint 4 (PI-015) are now answered; the RAM argument the ADR used against
  D and E is CONTRADICTED on the actual (4 GB, not 2 GB) hardware. **The decision does not
  change** — D still fails on C1 (DRM exclusivity) alone, E still fails on C4 (refresh rate)
  alone — but read the ADR's own correction banner before citing its RAM reasoning anywhere
  else; it no longer holds as originally argued.
- **Blockers:** none remaining from the original review. ~~PI-009 blocks S08~~ — resolved,
  see above.

## Ground truth from the Pi session (2026-08-24) — read before trusting anything pre-hardware

**Five predictions were CONTRADICTED**, not just refined. Each killed an *inference*, not
the underlying static observation — see `FINDINGS.md` for the corrected rows and each
deliverable's correction banner for downstream effects. Do not re-derive any of these:

| what was believed | what PI found | finding | still true? |
|---|---|---|---|
| The dev unit is a 2 GB CM5 Lite; ADR-001 rejects options D/E partly on that basis | **4048 MB total, confirmed by the operator as the genuine current unit** (not a fluke) — but 2 GB stays a real install/compile target | ADR-001 §3 C3 | Board size: no. RAM-based rejection of D/E: contradicted at peak load too (~2970MB free). D/E rejection itself: unchanged — each rests on an independent, unaffected leg |
| F-027's 12 unreferenced key strings are dead code, safe to remove | **All 11 concerns are live** — 8 form an undocumented cinepi-raw launch-config contract read from Redis at every process start, 2 are per-frame telemetry (~1401 SETs/60s each) with no reader | F-027 (reclassified `redundancy`→`correctness`, not downgraded) | The static claim (zero cinemate references) still holds exactly |
| F-253's timecode rounding divergence would show the DNG side wrapping at base 25 (C++ half-up) | It wraps at **base 24** (Python's convention) at 24.5fps | F-253 | The divergence itself is real; the specific predicted direction was wrong |
| F-182: `INSTALL_ALT_GPIO_BACKEND=0` produces an install that cannot boot (`ModuleNotFoundError`) | `python3-lgpio` ships via apt as a `python3-gpiozero` dependency regardless of the flag — **no crash** | F-182 (downgraded `high`→`low`) | The installer-conditional-vs-unconditional-import structure still holds; just doesn't crash |
| PI-005: the meson `/path/to/...` fallback is a live landmine masked by `pkg-config` happening to succeed | `pkg-config --exists hiredis`/`redis++` both exit 0 — the fallback branch is never taken | CENSUS.md §11 | Dead defensive code, confirmed safe to delete |

**What CONFIRMED, some more sharply than expected:**
- **F-204** (worst finding in the ledger) — decisively confirmed: a forced subscriber
  exception froze the cache-backed HTTP API and SSE stream permanently and silently on the
  first PUBLISH after the fault, for both a previously-seen key and a brand-new one.
- **F-025/F-268/F-269** (unserialised control paths) — confirmed as a **100% starve**, not
  an occasional race: a live Grove Base HAT pot on `iso` out-polled 20/20 explicit CLI
  commands over 14s. F-025 upgraded `probable`→`confirmed`, `medium`→`high` (see F-285).
- **F-172** (undrained log queue) — confirmed ~70x faster growth while recording than idle.
- **F-006/F-002** (test suite) — confirmed 381 passed + 241 subtests, zero skips, on real
  hardware, matching the off-hardware baseline exactly. The portable/hardware test split
  this item was written to discover **appears not to exist**.
- **F-003/F-186/F-276** (dependency drift) — a clean install succeeds end to end (after
  fixing two real installer bugs, F-279/F-280); flask and pyserial both confirmed
  transitive-only.
- **F-016** (audio_vu duplication) — VU meter works end to end, but the DEL-mid-take
  degradation this finding implied does **not** reproduce — `audio_vu` is republished
  unconditionally on nearly every cycle. Downgraded `high`→`medium`.
- **F-207** (web GUI liveness) — headless path confirmed real on a genuine cable pull;
  cadence measured at **~7.5 Hz**, not the ~12fps assumed everywhere it was cited — this
  number now appears in ADR-001 constraint 4 and GUI-INVENTORY.md.
- **F-259** (ISO cold-start fallback) — confirmed real (~5.6x silent overexposure via a
  standalone cinepi-raw launch) but likely unreachable through normal `cinemate-autostart`
  operation, since cinemate's Python layer re-seeds `iso` first.

**Nine new findings, F-279..F-287**, from the Pi sessions (not predicted by any queue item):
**F-279..F-282 fixed and merged** (#138, `6a15ed8`: `sudo -v` hang, `raspi-firmware` 404,
`settings.jsonc` comment destruction on every install not just via the web editor, a relative
tuning-file path). **F-283, F-284, F-286 (core) fixed and merged** (#135 `4f765c4`, #136
`2c73b22`, #137 `d35dfef`) **2026-08-25** — all three were desk diagnoses that needed
correction once verified on hardware; see `PI-RESULTS-2026-08-25.md` for exactly what each
diagnosis got right and wrong. **F-286's tie-break follow-up and F-285's full fix are open
PRs** (#139, #140) — F-285 is the hardware proof for F-025 above, now with a proposed and
implemented (pending merge) fix combining a dispatch lock, a movement gate, and read-back
confirmation. **F-283 has an unfixed residual**: a second, narrower `Conflicts=getty@tty1`
race can still land the unit `inactive` instead of `active` after some restarts (never hangs,
never `failed`, self-recovers) — four mitigations tried and rejected, open. **F-287** (added
2026-08-25, see `deliverables/REMEDIATION-PLAN.md`'s B9/B10 addition): cinepi-raw's seven
`meson test` targets had no CI to run them until this session ran them by hand.

**Operator decision (2026-08-25): keep F-027's 11 Redis-key concerns.** They are candidates
for future cinemate-side implementation, not dead surface — do not propose deleting any of
the 12 key strings in F-027. Documenting them in `docs/redis-keys.md` and the ADR-001
structural fix (a shared key registry) both remain live recommendations; only the "remove
it" branch closed.

**Open gap, not yet resolved — flag for a future Pi session:** the 2026-08-24 blank-card
session (`feature/no-venv-install`, PI-004/PI-011 second follow-up/PI-012/PI-016 second
follow-up) never recorded which `cinepi-raw` commit the fresh install actually built. The
2026-08-23 session pinned `cinepi-raw` at `dev` @ `ea96f2d` explicitly; F-264 notes
`CINEPI_RAW_REPO_REF` is unpinned in the installer, so a fresh clone on a different day could
have picked up a newer `dev` tip. This mostly doesn't matter (PI-004/PI-012 are
cinemate/apt-side; PI-016's second follow-up touches cinemate's `cinepi_controller.py`, not
cinepi-raw) **except for PI-011's second follow-up**, which exercises cinepi-raw's own
`cinepi_controller.cpp:76-77` cold-start fallback directly in a freshly-built binary — that
result is not provably against `ea96f2d` specifically. Next Pi session: `git -C
/home/pi/cinepi-raw log --oneline -1` and compare.

---

## Remediation status — added 2026-08-23

**KICKOFF §2.2's "analysis only, zero source edits" no longer applies.** The operator
directed implementation to begin, on new feature branches off `dev` in both repos. The
review ledger stays on `claude/cinemate-system-review-kickoff-cilicc` and is still the only
thing committed there.

| PR | repo | batch | state |
|---|---|---|---|
| #131 | cinemate | B4 style + **the CI itself**, 6 commits | **MERGED** `b9cd1f6` |
| #130 | cinemate | B3 correctness, 8 commits | **MERGED** `47ef0da` (rebased onto post-#131 `dev`; resolved a real conflict where its own shutdown-stop fix collided with #132's dead-code deletion at the same lines) |
| #132 | cinemate | B2 dead code, −1,398 lines | **MERGED** `7e05bb5` (rebased) |
| #134 | cinemate | contract-drift ratchet re-tightened (`--max-unresolved` 1→0) after #132's deletions | **MERGED** `fcf3c23` |
| #59 | cinepi-raw | B2 dead code, −1,565 lines | **MERGED** `bc63598` — hardware-verified first (dev vs branch, side-by-side build+run+record), per KICKOFF's one unverified merge gate |
| #135 | cinemate | F-283 (hang/`failed` fix) | **MERGED** `4f765c4` |
| #136 | cinemate | F-284 (`_blkid_value` empty-result fix) | **MERGED** `2c73b22` |
| #137 | cinemate | F-286 core (explicit-request guard + toggle) | **MERGED** `d35dfef` |
| #138 | cinemate | `feature/no-venv-install`: F-279..F-282 + the venv-removal architecture decision | **MERGED** `6a15ed8` |
| #133 | cinemate | B6 dependencies + `versions.env` | **MERGED** `7e7515f` — rebased onto post-#138 `dev`, install mechanism rewritten to match (`"${pip_cmd[@]}" -r ...` in place of `$VENV_DIR/bin/pip`); requirements-file content and `versions.env` unchanged. **The last remediation PR** |
| #139 | cinemate | F-286 tie-break follow-up (bit depth ranked above `fps_max` on a genuine downgrade) | open, CI green |
| #140 | cinemate | F-285 full fix (lock + movement gate + read-back confirmation) | open, CI pending at last check |
| #129 | cinemate | this ledger | open, intentionally — see the closeout instructions this session is running under |

**B2, B3, B4, B5, B6 are all complete.** #133 was the last remediation PR from the original
eight-batch plan. Full detail on the fix round and the venv decision: `PI-RESULTS-2026-08-25.md`.

**The venv decision (2026-08-25) is an operator architecture call, not a fixed finding** —
record it that way in any future summary so it doesn't read as remediation. Cinemate's Python
packages install to the system interpreter (`pip install --user --break-system-packages`)
instead of a dedicated virtualenv, matching the pattern `cinemate-recovery.service` already
used deliberately. Two follow-up checks run for the record (neither gates anything): the
apt/pip overlap is non-empty (`gpiozero`, `lgpio`, `pyudev`, `smbus2`) but not currently active
on the dev Pi, which predates the fresh no-venv install path; and root's `sys.path` contains
nothing under `/home/pi`, so `cinemate-recovery.service`'s isolation from
`cinemate-autostart.service` (F-221) survives via directory separation. Both in
`PI-RESULTS-2026-08-25.md`.

**B7** (ADR-001 steps 1–3) remains, and should follow B3 landing — done, above. ADR-001's
conclusion didn't change, so B7's plan doesn't need re-deriving, just the corrected ADR text
(already reconciled) as its input.

**Verified on hardware, 2026-08-24:** #130, #131, #132, cinepi-raw #59 — see the SAFE/
NEEDS-CHANGE column above and `PI-RESULTS-2026-08-24.md`'s "Merge verdict" section for the
full reasoning per PR.

**Verified on hardware, 2026-08-25:** merged `dev` running in both repos together (Phase C,
the first time this combination has run); F-204's fix re-verified with the same fault
injection PI-014 used; F-283's fix (5 consecutive restarts, none hung/`failed`); F-284's fix
(10/10 mount cycles, was 0/10 before); F-286's fix (a real recording at the forced 12-bit
mode, DNG TIFF tags parsed directly); F-285's fix (Grove Base HAT, both the starve and
isolated cases). Full detail: `PI-RESULTS-2026-08-25.md`.

### B9 and B10 — added 2026-08-25, on operator instruction

The plan originally batched 76 of the findings. The operator asked for coverage of **all** of
them, so `REMEDIATION-PLAN.md` §3 now carries two more batches:

- **B9 · One fact, one home** — 7 commits, 28 findings. The duplication backlog, grouped by
  *which fact* is duplicated rather than by file: storage facts, boolean decoding, the redis
  client and `ParameterKey` enforcement, the cross-repo formulas, config defaults, the four
  `class Event` definitions, and the GUI's derived labels. Nine of these have already drifted.
  B9.4 depends on PI-010/PI-011 having measured which implementation wins at runtime — both
  are done, so unification has a target rather than a guess.
- **B10 · Close the ledger** — 8 commits. A second deletion pass, shell-script correctness,
  logging hygiene, docs round two, a CI for cinepi-raw (**F-287**, new), and — the point of
  the batch — a `disposition` column on every finding plus
  `tools/findings_disposition_check.py` in the drift job to enforce it. Five dispositions are
  allowed: `fixed`, `guarded`, `accepted`, `superseded`, `strength`.

**Coverage is now checkable, not asserted:** every one of the 202 findings is named in a
batch, and every finding cited by a batch exists. Verify with:

```
grep -o 'F-[0-9]\{3\}' FINDINGS.md | sort -u > /tmp/a
sed -n '60,/^## 4\. What is NOT/p' deliverables/REMEDIATION-PLAN.md | grep -o 'F-[0-9]\{3\}' | sort -u > /tmp/b
comm -3 /tmp/a /tmp/b        # must print nothing
```

**"Named in a batch" is not "fixed".** Most of B10 records an accepted risk rather than
changing code — that is a legitimate outcome, and B10.7's check exists so an accepted risk
cannot quietly become a forgotten one.

---

## Deviations from KICKOFF — read before touching git

KICKOFF is immutable (§10). These corrections live here instead.

### D1 · Branch name differs

KICKOFF §3 says `review/system-analysis`. **The actual ledger branch is
`claude/cinemate-system-review-kickoff-cilicc`**, mandated by the session harness, which
forbids pushing elsewhere without permission. Cut from `origin/dev` @ `02b5a39`.

Use this branch. Do not create `review/system-analysis` without asking the operator.

### D2 · cinepi-raw — **now on `dev`** (revised 2026-08-23 on operator instruction)

**Operator instruction: use the `dev` branches of both projects.** Both are now on `dev`.

**cinemate** was already correct: `origin/dev` is `02b5a39`, unmoved, and that is exactly
the ledger branch's base and merge-base. Nothing needed rebasing. The ledger branch stays
`claude/cinemate-system-review-kickoff-cilicc` — **never commit or push to `dev`** (§6.1).

**cinepi-raw** was on `main` @ `774402c` for S01–S07 and is now on **`dev` @ `ea96f2d`** at
`/workspace/tiramisioux/cinepi-raw`. That gap was **45 files / +7164 lines** (F-225).

- **KICKOFF §6.2's C++ table is now the applicable one.** It described `dev` @ `ea96f2d` all
  along. The old "do not mix the two tables" warning is void. `CENSUS.md` §2 holds `main`
  figures (24,051 LOC); `dev` is **29,438** (F-231).
- **Every cinepi-raw figure in S01–S07 is a `main` figure.** Re-verified so far: the key
  contract (F-226), the test targets (F-228), the RAM auto-stop citation (F-230), the LOC
  (F-231), and the `dualHdmiPreviewStage.cpp` DRM comment (**unchanged — S03's ADR-001
  evidence holds**). Not yet re-verified: `dng_encoder.cpp` (687 lines changed, a near
  rewrite), the CCMP preview stage and LOG-LUT subsystem (both new), `cinepi_controller.cpp`
  (+151), `cinepi_recorder.hpp` (+60).
- **Still read-only and shallow.** No push target, no history, no blame, no `-S`. PI-003
  remains blocked on a full clone.
- `libcamera/` and `imx585-v4l2-driver/` are still absent.

**If a fresh session finds no cinepi-raw, clone `dev`:**
```
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --branch dev \
  https://github.com/Tiramisioux/cinepi-raw /workspace/tiramisioux/cinepi-raw
```
**Check the branch before trusting any cinepi-raw figure:**
`git -C /workspace/tiramisioux/cinepi-raw branch --show-current` must print `dev`.

### D3 · The dirty tree in KICKOFF §6.1 does not exist

Working tree is clean; `origin/dev == 02b5a39 ==` branch base. KICKOFF §11 step 3 ("ask
the operator about the 8 uncommitted files") is **satisfied with nothing to ask.** See
`findings/F-011.md`. Do not go looking for those edits.

### D4 · The LFS pointer trap did not reproduce

`docs/images/*.png` are real files (53–75 KB), tree clean. `.gitattributes` does route
`*.png`/`*.jpg`/`*.ipynb` through LFS, so the trap is real in principle.
**Keep staging narrowly regardless:** `git add system-review/`, never `git add -A`.
Run `git status --short` before every commit.

### D5 · Ledger lives inside the repo, intentionally

KICKOFF §3 notes this overrides the operator's normal convention (scratch workspaces
outside the repo tree). Sessions run on clients that only see the repo, so git is the only
cross-session persistence layer. **This is deliberate. Do not "fix" it.**

---

## Ground truth established so far

### From S05 (readability) — detail in `deliverables/READABILITY-REPORT.md`
- **The best comment in the codebase guards an invariant that no running test protects.**
  `storage_profiles.py:41-49` (AUDIO-CORE INVARIANT) names its own guarding test, and that
  test is one of the 27 that never run. Sharpest argument in the review for CI first.
- **47 load-bearing why-comments exist and are a deletion hazard** (F-133), including two
  falsified experiments. Promote to `docs/` before refactoring those files.
- **Zero TODO/FIXME/XXX/HACK** in ~19,800 LOC (F-134) — a genuine positive.
- **337 except handlers, 15 silently swallowing** (F-130) — violates the project's own
  "fail visible" principle.
- **The codebase explains decisions well and interfaces poorly** — 27% docstring coverage,
  40 public classes with none including `CinePiController`.
- **A second duplication cluster exists around storage** (F-155..F-165), and **F-164 is its
  root cause**: the service↔app coupling is a dead journalctl tail, so the app polls
  instead. Fixing that one link collapses five findings.

### From S04 (redundancy sweep) — detail in `deliverables/REDUNDANCY-REPORT.md`
- **Duplicated truth is systemic: 16 instances, 9 already drifted.** This is the review's
  central structural finding and it constrains ADR-001 — see the deliverable §6.
- **F-118 is the proof it costs something:** a Python↔JS duplicated action catalogue offers
  `set_log` where the method is `set_log_encode`, so a settings-editor button silently
  no-ops **today**.
- **≈3,250 LOC of confirmed-dead source** is deletable with no hardware (deliverable §2).
- **Module reachability in `src/` is exhausted** — exactly 4 of 48 unreachable (F-122).
- **No triple sensor table.** `resources/sensors.json` is a genuine single source; cinepi-raw
  holds no sensor data. Hypothesis disproved — do not re-hunt.
- **`settings.schema.json` agrees with `config_loader.py` on all 41 comparable defaults** —
  the viable origin for defaults unification (F-251).

### From S06 (standards) — detail in `deliverables/STANDARDS-PROPOSAL.md`
- **The review's organising claim, now stated outright: CineMate has a drift problem, not a
  style problem.** Every serious finding is two copies of one truth that stopped agreeing.
  The standard is built around drift *checks*, with lint second and formatting last. Carry
  this framing into S11 and S12 — it is the spine of the remediation plan.
- **The rule worth writing down:** *duplicated truth must either be deleted, or carry a
  named reason **and** an automated check. A comment is not a check.* Three hand-sync
  comments exist; two are already wrong.
- **The shell is the best-maintained code in the repo** (F-174, F-192, F-194). 15 shellcheck
  findings across 11 scripts, one of them in the 1916-line installer, whose idempotency is
  *designed and documented*. The standards proposal generalises from it rather than
  importing conventions from outside. Do not propose shell cleanup as a priority.
- **`settings.schema.json` cannot reject an unknown key** — `"additionalProperties": true`
  25×, `false` 0× (F-166). A typo'd setting validates clean and is silently ignored.
- **The in-app log queue is never drained** (F-172) — unbounded growth for the process
  lifetime. Structurally confirmed; rate is PI-013.
- **`INSTALL_ALT_GPIO_BACKEND` is advertised as optional but is load-bearing for boot**
  (F-182) → PI-012. The only S06 finding that touches the install path.

### From S07 (GUI) — detail in `deliverables/GUI-INVENTORY.md` + `GUI-STATE-MODEL.md`
- **THE headline for ADR-001: the web GUI has no state model of its own — it consumes
  `simple_gui.populate_values()` verbatim** (F-203). The operator's hypothesis is half
  right and the true half is the expensive half. A shared state model does not need
  building; it exists, 68 fields wide, one owner.
- **Option C's widget spec also already exists** (F-215): `left_section_layout` /
  `right_section_layout` in `setup_resources` — label, ordered items, per-item formatters,
  optional visibility `condition`. Encoded as Python lambdas, so not serialisable, but the
  shape is right. **The residual hard problem is layout and only layout** (F-008).
- **Surface 4 (recovery console) must be excluded from any unification** (F-221). Its value
  is its isolation, and it is the best-engineered component in the review.
- **F-204 is the most severe finding in the ledger.** One raising redis subscriber kills the
  live-state bus permanently and silently; `get_value()` then serves a stale cache, so every
  surface shows plausible frozen values instead of an error. That is the baseline for
  KICKOFF §7 constraint 5. → PI-014. **F-208: the guarded version of the same loop already
  exists 900 lines away** (`cinepi_controller.py:1082-1087`).
- **HDMI hot-plug restarts `cinepi-raw`** (F-223) — so the preview binds to the display at
  process start and cannot rebind. Strongest static evidence for PI-009; narrows ADR-001
  constraint 2 without settling it.
- **The settings-editor action catalogue is the thesis in miniature**: 3 copies, the two
  hand-maintained ones agreeing perfectly *including on the same bug*, a hand-correction
  that was itself incomplete, and the mechanical check written and unwired (F-218..F-220).
- **381 tests across 27 files have never run** (F-222). F-006 undercounted the loss.
- **The extractor over-counted once and under-counted once, in one session.** Both were
  caught by re-checking output against source. Numbers not produced by a committed script
  should be treated as provisional.

### From S07b (dev-branch reconciliation) — detail in `sessions/S07b-dev-branch-reconciliation.md`
- **Both repos are on `dev`. Verify it before trusting a cinepi-raw figure:**
  `git -C /workspace/tiramisioux/cinepi-raw branch --show-current` → must print `dev`.
- **The cross-repo drift did not grow between branches** — 12 unreferenced keys on both.
  The 4 new `dev` keys are the HDR family and cinemate already has all four. Worth stating
  in S12: this boundary is being maintained.
- **F-227 is new ADR-001 material.** `dev`'s `drm_preview.cpp` enumerates DRM planes and
  programs a spare overlay plane for `--same-hdmi`, degrading gracefully when none is free.
  cinepi-raw already does plane-level composition. PI-009 now has a concrete measurement
  attached: count free overlay planes on the primary CRTC, `--same-hdmi` on and off.
- **`dualHdmiPreviewStage.cpp`'s DRM-master comment is byte-identical on `dev`** — S03's
  strongest ADR-001 evidence survives the branch change.
- **The largest outstanding re-verification: `dng_encoder.cpp` changed by 687 lines.**
  `CODE-MAP-cinepi-raw.md` §4's frame lifecycle is a `main` account of a component that has
  since been rewritten, and the new CCMP preview stage and LOG-LUT subsystem are not in the
  map at all. Banner is on the file.

### From S08 (ADR-001) — detail in `decisions/ADR-001-gui-harmonization.md`
- **F-238 decided the ADR, and it corrects F-008.** The HDMI GUI is *not* uniformly
  absolute-positioned: `_top_row_layout` is a justified flex row computed from measured text
  widths, and `draw_left_sections` is a conditional vertical stack. It is **a fixed grid of
  regions with content-driven flow inside the two busiest ones.** KICKOFF §7's
  immediate-vs-retained framing overstates the gap (F-239). **Do not cite F-008 unqualified
  again.**
- **Correction to KICKOFF §7 constraint 1:** DRM exclusivity is fatal to option **D only**,
  not to E. E writes `/dev/fb0` like `simple_gui` does and adds no second DRM client; it
  dies on refresh rate and RAM instead.
- **`design_token_diff.py` refined F-007 in the harsh direction:** only **3 of 16** colour
  tokens name their Python counterpart; 11 have no stated link at all (F-232). Zero drift
  today — which is exactly when the check is worth adding.
- **Three stdlib-only CI checks now exist** — `redis_key_diff.py`, `gui_field_extract.py`,
  `design_token_diff.py`. None needs hardware. ADR-001 §6: no unification step lands without
  its check landing on the same commit.
- **C7 has a number:** `SimpleGUI` is 1913 lines — 925 draw/layout (rewritten), **636 state
  (preserved)**, 241 display/fb. A renderer swap is ~43% of the file, contiguous and
  flag-gateable.

### From S09 (docs drift) — detail in `deliverables/DOCS-DRIFT-REPORT.md`
- **The docs are the best-maintained boundary in the system, and this inverts the review's
  prior.** 103 links / 0 broken · 64 code citations / 0 bad · 11 of 11 settings sections ·
  71 of 71 key rows real · 43 of 43 method names real (F-240).
- **The prose copy of the controller catalogue is the correct one** (F-242). Both
  machine-readable copies carry `set_log`, which does not exist. Use this in S11 and S12.
- **Drift lives in code prose, not in `docs/`** — 3 hand-sync comments drifted, a fourth in
  CSS, and F-246's `lock_dual_recording` survives in a **docstring** and a **comment** as
  well as the changelog while existing nowhere. **Second argument for promoting F-133's 47
  why-comments into `docs/`.**
- **Thin ≠ drifted, and `PLAN.md` conflated them.** The 15-line `compiling-cinepi-raw.md` is
  completely correct (F-262). Line count predicted nothing in all three test cases.
- **The published site is missing its best method reference** — `controller-methods.md` and
  `image-circle.md` (232 LOC of correct content) are unreachable from the nav (F-244). One
  line of YAML each; highest value-per-effort docs fix.
- **Four stdlib-only checkers now exist.** `redis_key_diff.py`, `gui_field_extract.py`,
  `design_token_diff.py`, `docs_drift_check.py`. None needs hardware.
- **Write the checker before the prose that cites it.** Three of S09's six checks were wrong
  on the first attempt; one would have appeared to contradict F-014. Four of five
  corrections came from reading script output back against source.

### From S10 (install drift) — detail in `deliverables/INSTALL-DRIFT-REPORT.md`
- **The installer and its docs agree on everything mechanically checkable** (F-267) — repo
  URLs, refs, 16 shared paths, an exactly matching 17-name unit set. The problems are
  structural.
- **F-264: the two repos that move most are the two nothing pins.** Drivers pinned to
  `6.12.y`, libcamera to `cinemate`; `CINEMATE_REPO_REF` and `CINEPI_RAW_REPO_REF` empty in
  both installer and doc. With S07b's 45-file/+7164-line `main`↔`dev` gap and F-190's zero
  pip pins, **an install is not reproducible across two days.** Fix: a `versions.env`
  pairing manifest.
- **F-266: the recovery console appears zero times in the 1061-line install doc** — the
  component whose whole purpose is being reachable when everything else is broken.
- **F-003 is DECIDED, reversing S01's lean: option 2** (`requirements.txt` canonical,
  three-file split). Reason: option 1 would push the dependency list into the CI workflow as
  a *third* copy — `checks.yml` already hand-lists it. F-182's `lgpio` fix falls out for
  free. **The split line is `unverified` pending PI-002.**
- **Four apparent findings dissolved on checking** — a keyword matcher's 11 false "missing
  steps", an upstream-attribution URL, `$PI_HOME`-derived paths, and a regex that missed
  bare-name headings. The dissolved candidates took more work than the recorded ones.

### From S11a (controller + philosophy) — detail in `deliverables/CINEMATE-PHILOSOPHY.md`
- **`cinepi_controller.py` is TRACED. Stop deferring it.** F-270: 2626 lines is **151 methods
  on one class** (94 public, 57 private, no `@property`), averaging ~16 lines. Only
  `__init__` (239) is oversized. **Wide, not deep** — S12 should split it by concern into
  modules, not by extracting long methods.
- **F-025 is SETTLED (F-268), PI-007 step 1 discharged, no hardware.** `_dispatch_lock` is
  `CommandExecutor`'s (`cli_commands.py:21`, 2 s timeout) and serialises **3** paths
  (CLI, serial, HTTP). **6** modules bypass it via `getattr` — including `storage_preroll.py`
  and `simple_gui.py`, which F-025 did not name. F-269: the controller has **9 lock sites
  across 151 methods**, so there is no internal fallback.
- **F-271 — the settings editor destroys all 74 comment lines in `settings.jsonc`** (19% of
  the file), no warning, no backup. The correct implementation is ~1000 lines away in
  `cinemate-recovery.py`'s `write_config_file`.
- **The philosophy document's spine, and the review's thesis restated:** *this project knows
  what it believes, states it in prose, and enforces it nowhere — and where a principle is
  violated, the correct implementation usually exists a few hundred lines away.* Three
  instances: F-204/F-208, F-271/`write_config_file`, F-118/F-219.
- **Twelve principles now:** 8 from KICKOFF (2 refined, 3 confirmed, 1 bounded, **2 stated
  and violated by the product**) plus 4 new — degrade in ladders · state the reason in place
  · duplicated truth needs a check not a comment · route don't replicate.

### From S12 (remediation) — `deliverables/REMEDIATION-PLAN.md`
- **The batches are split by risk and verifiability, NOT by repo.** The operator proposed a
  per-repo split; the distribution kills it — cinepi-raw has **8** findings and **17 are
  cross-repo by nature**. §1 has the argument.
- **B3 goes first**: F-204 and F-271, ~10 lines each, both with a correct sibling
  implementation already in-repo. Then B1 docs / B2 delete / B4 checks in any order, then
  B5 the Pi session, then B6 dependencies, then B7 ADR-001 steps 1–3.
- **§6 has six ready-to-paste handoff prompts**, self-contained, one per supervised thread.
- **§4 lists the 24 strengths that must survive the work** — F-133's comments are the main
  thing B2 could damage.
- **Incremental agent writes are mandatory, not advice.** Two agent runs died mid-flight
  to usage limits; the one told to write incrementally preserved 16 findings, the four that
  weren't preserved nothing.
- **Pattern matching has under-reported three times now** (`cinepi_ready_<port>`, `tc_key`,
  `from module import X`). Treat "no grep hit" as a hypothesis, never a result.
- **And it has OVER-reported once** (S06): a naive schema walk claimed 88 settings keys were
  unvalidated; most were covered by `additionalProperties` subschemas and `$ref`s. The real
  finding was different and stronger (F-166). Probe the structure before counting it.
- **Read `STATE.md` before the first grep — including in a resumed session.** S06 skipped it
  and re-derived F-002/F-003 as five new findings before catching itself. The "Do not redo"
  list below only works if it is actually read.

### Tooling now in the ledger
- **`harness/redis_key_diff.py` works** and reproduces F-027: 84 / 32 / 19 shared / 12
  unreferenced. Run it before trusting any hand-counted key figure — it already caught one
  arithmetic error in F-027 (11 → 12 key strings).

### From S03 (cinepi-raw architecture) — detail in `deliverables/CODE-MAP-cinepi-raw.md`
- **cinepi-raw is a fork of `rpicam-apps`.** `cinepi/` is the product; `core/`, `preview/`,
  `encoder/`, `apps/` are upstream.
- **Three executables**, not one: `cinepi-raw`, `cinepi-audio-capture` (separate process,
  supervised via fork/popen), and `phase_lock_core_test` (wired into `meson test`).
- **The cross-repo contract is the `cp_controls` channel.** cinepi-raw's registry is 24
  `CONTROL_KEY_*` macros (`cinepi_state.hpp:23-52`) against cinemate's 84-member enum.
  ≥19 shared, ≥11 orphaned (F-027). Counts are lower bounds — dynamic keys exist.
- **`cinepi_ready_<port>` is a live handshake in neither registry** and is a fifth Redis
  access pattern (glob scan through the raw client).
- **DRM master is exclusive and cinepi-raw holds it.** The project already worked around
  this once for dual-sensor, using SysV shared memory rather than sharing the display.
- **The GUI and the preview use two different kernel interfaces** — DRM/KMS vs legacy
  fbdev. How they compose is unknown (PI-009).
- **The RAM auto-stop is `cinepi_raw.cpp:200-212`** — a hard stop on the record path.

### From S02 (cinemate architecture) — detail in `deliverables/CODE-MAP-cinemate.md`
- **`ParameterKey` (`redis_controller.py:18`) is the canonical Redis registry** — 84
  members. It is convention, not enforcement: `set_value` accepts any string (F-015).
- **Redis docs are a strict subset of code** — 18 undocumented keys, 0 orphan docs (F-014).
  The gap clusters around dual-sensor and dynamic-resolution work.
- **`RedisController` caches locally.** `get_value()` reads the cache, not Redis; a pub/sub
  listener thread keeps it fresh. Four distinct access patterns exist across the codebase.
- **Two paths into `CinePiController`, one serialised.** CLI/serial/HTTP share
  `_dispatch_lock`; GPIO, pots, quad rotary and keyboard bypass it entirely (F-025).
- **`settings.jsonc` contains controller method names**, resolved by `getattr`. Those 94
  method names are a user-facing API — renaming one is a breaking change (F-026).
- **Boot is one 400-line straight-line function**; `cleanup()` sits 300 lines away in the
  same function and misses four components (F-022, F-023, F-024).
- **`timekeeper.py` (243 LOC) is entirely dead** — `Timekeeper(` appears nowhere (F-017).

- **Scale.** cinemate: 47 Python files / 19,794 LOC in `src/`, plus a 1,916-LOC installer,
  50 docs, 34 files in `_test/`, 5 systemd service subsystems (one of which,
  `storage-automount.py`, is ~1,123 LOC and was invisible to KICKOFF's `src/`-only table).
  cinepi-raw: 24,051 LOC C/C++. → `deliverables/CENSUS.md` §1–2
- **`redis_controller` is the hub** — imported by 10 modules, the widest fan-in in the
  repo. Early support for KICKOFF §9 principle 1, not yet proof. → CENSUS.md §4
- **`main.py` imports 27 modules directly.** No intermediate composition layer. → CENSUS.md §4
- **Ports:** 5000 (Flask GUI/API/settings-editor), 8888 (status broadcast), 8080 (recovery
  console), 8000/8001 (MJPEG preview, consumed not bound), 6379 + 8423 outbound.
  → CENSUS.md §6
- **The GUI colour duplication (F-007) is self-documenting** — `template.html`'s CSS
  custom properties carry comments naming the Python constants they mirror. Strongest
  available argument for ADR-001 option B.
- **The HDMI GUI scales, it does not reflow.** `simple_gui.py:1657-1658` applies
  `shrink_x` to the 1920-reference constants. F-008's real obstacle is the absence of
  content-driven layout, not the absence of scaling. Matters for S08.
- **A working off-hardware `simple_gui` test already exists** —
  `_test/test_simple_gui_preview_guide.py`. This is the precedent for the S07 render harness.
- **Dependency management is broken in a specific, documented way** — `requirements.txt`
  is read by nothing; `flask` is never installed directly. → `findings/F-003.md`

## Do not redo

- **Do not re-verify F-001..F-013.** Each was checked against source in S01. Read
  `FINDINGS.md` and the `findings/*.md` detail files.
- **Do not re-derive the requirements.txt / installer divergence.** Fully computed in
  `findings/F-003.md`, including the exact package lists both ways. S10 chooses between
  the two remediation options; it does not recount.
- **Do not recount the docs.** `CENSUS.md` §9 has the complete 50-file inventory, the
  empty files, and the mkdocs nav gaps. S09 starts from there.
- **Do not re-audit logging, `print()`, shellcheck, or the settings schema.** S06 did all
  four; figures are in `sessions/S06-standards.md` and F-166..F-181.
- **Do not re-derive installer idempotency.** F-192 settles it: idempotent by construction.
- **Do not re-inventory the GUI surfaces or re-count their fields.** S07 did it and the
  counts are reproducible: `python3 system-review/harness/gui_field_extract.py --repo .`
- **Do not re-check the docs mechanically.** S09 did all six:
  `python3 system-review/harness/docs_drift_check.py --repo .`
- **Do not re-diff the installer against `installation-steps.md`.** S10 did it; they agree
  (F-267). And **do not re-open F-003** — S10 chose option 2 with reasons.
- **The Redis key census is DONE** (S02). `ParameterKey` at `redis_controller.py:18` is the
  registry; the docs diff is F-014. Do not re-derive it. `CENSUS.md` §7 is superseded.
- **Do not re-trace `main.py` boot or shutdown** — `deliverables/CODE-MAP-cinemate.md` §3–4
  has the 28-step construction order and the full thread table with verified citations.
- **Do not re-map the control surfaces** — CODE-MAP §5 has both dispatch paths. Note the
  keyboard surface is **dead** (F-031); an early revision of that map said otherwise.
- **Do not redo the cross-repo Redis key diff** — S03 did it, `findings/F-027.md`.
- **Do not re-run module reachability in `src/`** — F-122 is the corrected, exhaustive result.
- **Do not re-hunt a duplicated sensor table** — disproved in S04.
- **Do not re-verify F-100..F-127, F-200..F-202, F-250..F-261** — all merged with citations.
- **Do not re-derive the cinepi-raw build graph** — CODE-MAP-cinepi-raw §2. `lj92.c` is
  dead (F-029); `cinepi_audio_capture.cpp` is a separate executable, not a missing source.
- **Do not look for the 8 uncommitted files** (D3) or the LFS pointer corruption (D4).
- **Do not re-read `KICKOFF.md` §6.2's C++ table as current.** It describes a different
  branch than the one available. (D2)
- **Do not re-run any of the 16 `PI-VERIFICATION-QUEUE.md` items.** All done, digest in
  `PI-RESULTS-2026-08-24.md`. Two narrower sub-cases were not reached (PI-009's `--same-hdmi`
  toggle, PI-015 step 3 — killing the `SimpleGUI` thread specifically) — those are still
  open, everything else is not.
- **Do not re-derive the five contradictions** (board RAM/size, F-027's dead-vs-live status,
  F-253's rounding base, F-182's crash claim, PI-005's landmine claim) — see "Ground truth
  from the Pi session" above. Each has a stated correction with a citation; re-deriving them
  from source alone will reproduce the pre-hardware belief, not the measured one.
- **Do not re-open F-003's option-2 decision on the strength of F-182 alone.** F-182 is
  downgraded (PI-012), but F-003's option-2 reasoning never actually depended on F-182's
  severity — it rested on F-264 (pinning) and the CI-duplication argument. Both untouched.
- **Do not propose deleting any of F-027's 12 Redis key strings.** Operator decision,
  2026-08-25: keep them, they're candidates for future implementation. Documenting them and
  the structural (shared-registry) fix remain live; deletion does not.
- **Do not re-argue ADR-001's D/E rejection from the RAM constraint.** It's gone (PI-016
  contradicted it) and is not what D/E are rejected on anymore — see the ADR's own
  correction banner. D rests on C1 alone, E on C4 alone, both untouched by the RAM finding.

## Watch items

- **PI-007 step 1 is a desk task, not a Pi task.** Reading `cinepi_controller.py` for
  internal locking may settle F-025 for free. Do it before booking hardware time.
- **The DNG metadata path (timing → DNG tags) was in S03's brief and was not done.**
  `dng_save()` and `dng_encoder.cpp` (1521 LOC) remain untraced. Blocks nothing yet.
- ~~The F-027 key-diff harness script is unwritten.~~ **Done** — `harness/redis_key_diff.py`.
  S07 added a second: `harness/gui_field_extract.py`, which independently reproduces F-118.
  Both are wired into `STANDARDS-PROPOSAL.md` §3 as CI checks and neither needs hardware.
- ~~`cinepi_controller.py` (2626 LOC) internals are still untraced... it gates F-025's
  severity.~~ **Done.** S11a traced it (F-268/F-269), PI-007/F-285 confirmed the consequence
  on hardware (100% starve). See `CINEMATE-PHILOSOPHY.md`.
- **Which `cinepi-raw` commit the 2026-08-24 blank-card session actually built is
  unrecorded.** The Aug 23 session pinned `dev` @ `ea96f2d` explicitly; the Aug 24 session
  cloned `feature/no-venv-install` (a **cinemate** branch) onto a blank card, and
  `cinemate-install.sh` pulls cinepi-raw at whatever `dev` currently is (`CINEPI_RAW_REPO_REF`
  is unpinned, F-264) — not necessarily still `ea96f2d`. Mostly harmless (PI-004/PI-012 are
  cinemate/apt-side), but **PI-011's second follow-up exercises cinepi-raw's own
  `cinepi_controller.cpp:76-77` cold-start fallback directly** in that freshly-built binary,
  so that specific result isn't provably against `ea96f2d`. Next Pi session:
  `git -C /home/pi/cinepi-raw log --oneline -1`, compare, record it in the queue header the
  way the Aug 23 session did.
- **The install/compile path must keep working on 2 GB CM5 hardware, not just the 4 GB dev
  unit** (operator instruction, 2026-08-25). No 2 GB-specific measurement exists anywhere in
  this ledger — PI-016's RAM headroom numbers are 4 GB-only. This doesn't block anything
  currently planned (ADR-001's D/E rejection no longer depends on RAM at all — see above),
  but any future RAM-sensitive decision should not assume the 4 GB numbers generalize down.

- `CENSUS.md` §12 lists everything S01 deliberately left unestablished. Check it before
  assuming coverage.
- `PI-VERIFICATION-QUEUE.md` has **15** open entries. **PI-002 (run the test suite) gates
  S06's CI proposal** — it should be among the first things done once hardware is
  available, and F-222 raises its value: **381 tests**, not 27 files.
- PI-003 is mislabelled as Pi-bound; it only needs a full cinepi-raw clone. Reclassify
  when one is attached.
