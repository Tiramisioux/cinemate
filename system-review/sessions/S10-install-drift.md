# S10 — Install script vs. install docs

**Plan entry:** S10 · **Findings:** F-264..F-267 (4) · **Ledger total:** 182
**Pi used:** no · **Subagents used:** none
**Deliverable:** `deliverables/INSTALL-DRIFT-REPORT.md`

---

## Verdict

**They agree on everything mechanically checkable.** Sensor-driver URLs and their `6.12.y`
ref, libcamera's `cinemate` branch, 7 shared GitHub URLs, 16 shared absolute paths, and an
**exactly matching 17-name systemd unit set** checked both directions (F-267). Every subject
the step-name matcher flagged as missing turned out to be covered in the doc's prose.

For a 1916-line installer against a 1061-line document written as an independent manual
walkthrough, that is a strong result — and consistent with S09's finding that the docs are
the healthiest boundary in this system.

**The problems are structural, not factual.**

## F-264 — the two repos that move most are the two nothing pins

The installer pins the sensor drivers to `6.12.y` and libcamera to `cinemate`. It leaves
`CINEMATE_REPO_REF` and `CINEPI_RAW_REPO_REF` **empty**. The doc's `git clone` commands pin
nothing either.

S07b measured the cost: cinepi-raw's `main` and `dev` differ by **45 files / +7164 lines**,
including four `CONTROL_KEY_` macros of the cross-repo Redis contract (F-226) and a
`--same-hdmi` implementation present on one branch only (F-227). Two programs that talk over
a key contract which differs between branches, and **no manifest records a known-good
pairing.** With F-190's zero pip pins, an install performed on two different days is not the
same system.

This is the review's thesis in its reproducibility form: the pairing is real, load-bearing,
and written down nowhere. Recommended fix is a `versions.env` the installer sources and the
docs quote.

## F-265 and F-266 — the two navigability gaps

**F-265.** The installer prints 27 numbered steps; the doc is a narrative under 18
differently-named sub-headings in a different order, and never cites a step number. An
operator whose install fails at `[18] Writing runtime loader configuration` has nothing to
look up. Not a content gap — a granularity gap, and the installer already has a `section()`
helper where the fix would go.

**F-266.** `cinemate-recovery` appears **zero times in 1061 lines**, including in the
services section that covers the other four units under `####` headings. It has its own
published page, so it is not undocumented — but a reader following the install never learns
it exists. Per F-221 that component's entire purpose is being reachable when the venv is
broken and redis is down. A recovery tool discovered only by opening a page you had no
reason to open is not there when it is needed.

## F-003 decided — and reversed

S10's assigned job was to choose between F-003's two remediation options. S01 leaned to
**option 1** (installer canonical, delete `requirements.txt`) as *"the smaller change and
the honest one"*. **S10 recommends option 2**, because three findings postdating F-003
change the arithmetic:

1. **CI is coming and needs an installable list off-Pi.** `STANDARDS-PROPOSAL.md` §6.2
   drafts a job for the 381 tests that have never run (F-222) — and under option 1 that
   workflow hand-lists its packages. The draft `checks.yml` already does. **Option 1 creates
   a third copy** in the place nobody looks, rather than deleting the second.
2. **F-264 makes pinning the priority**, and option 1 deletes the only artefact shaped like
   a place to record versions.
3. **The hardware/portable split is not clean** — F-182's `lgpio` is installed conditionally
   and imported unconditionally.

Recommended shape: `requirements.txt` (portable, pinned, used by installer *and* CI),
`requirements-hardware.txt` (Pi-only, and `lgpio` moves here unconditionally — F-182's fix
falls out for free), `docs/requirements-docs.txt`. **Where the split line goes is
`unverified` pending PI-002** — run the suite once and the import errors draw it.

## Corrections made during the session

- **The step-correspondence matcher was wrong and produced 11 false "NO MATCH" steps.**
  Keyword-matching installer step names against doc headings measures heading similarity,
  not coverage. Grepping the doc for each actual subject — `redis-plus-plus`, `libtiff`, the
  venv, `lgpio`, the loader config, `.asoundrc`, post-processing, the overclock — found all
  of them present. Had that shipped, S10 would have reported eleven documentation gaps that
  do not exist. The corrected method and the reason are both in the report.
- **`will127534/imx283-v4l2-driver` looked like a URL divergence** — it appears in the doc
  and not the installer. It is upstream attribution prose; the doc's actual `git clone`
  commands use the `Tiramisioux/` forks the installer uses. Checked before writing.
- **The doc-only absolute paths looked like drift** — they are runtime paths the installer
  constructs from `$PI_HOME`. Not divergence.
- **"The services section covers 3 of 6 services" was wrong.** My first regex matched only
  fully-qualified `*.service` filenames and missed four bare-name `####` headings. The
  section covers four of five; only `cinemate-recovery` is genuinely absent (F-266).

Four apparent findings, all dissolved by checking. The one that survived is the one that
started as the least interesting-looking.

## Method note

S10 produced fewer findings than any session in the review, and that is the result rather
than a shortfall: three of its five assigned tasks were already settled (`shellcheck` and
idempotency in S06, the package lists in F-003), and the remaining two produced four
findings and one reversed decision. **The four dissolved candidates took more work than the
four recorded ones.**

## Left undone

- **`cinepi_controller.py` (2626 LOC) is untraced** since S02 — deferred six times. **PI-007
  step 1 is a desk task**, not a Pi task. This should now take priority over extending any
  session's scope.
- **`dng_encoder.cpp` on `dev` (687 lines changed)** — largest cinepi-raw hole, from S07b.
- **The `wifi_hotspot` triangle** — two thirds unreached since S04.
- No install was performed; PI-004 and PI-012 remain the way to settle installer behaviour.
