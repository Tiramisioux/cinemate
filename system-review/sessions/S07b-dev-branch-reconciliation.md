# S07b — Branch reconciliation: both repos on `dev`

**Trigger:** operator instruction — *"Use the dev branches of both projects."*
**Not a plan entry.** A correction pass between S07 and S08.
**Findings:** F-225..F-231 (7) · **Ledger total:** 158 · **Pi used:** no

---

## What was wrong

**cinemate was already right.** `origin/dev` is `02b5a39` — unmoved since the review began,
and exactly the ledger branch's base and merge-base. Every cinemate figure in S01–S07 is a
`dev` figure. Nothing needed rebasing.

**cinepi-raw was on `main`.** D2 recorded that as a constraint of the environment. It was
also, it turns out, a real gap: `dev` @ `ea96f2d` is **45 files and +7164 lines** ahead of
`main` @ `774402c` — a near-rewrite of `dng_encoder.cpp` (687 lines), a new LOG-LUT
subsystem, a new CCMP preview stage, four new `CONTROL_KEY_` macros, and six new test
targets.

The clone is now on `dev`. D2 is rewritten.

## What changed in the findings

| Was | Is on `dev` |
|---|---|
| Cross-repo key contract 84 / 32 / **19** shared / 12 (F-027) | 84 / 36 / **23** shared / 12 (F-226) |
| cinepi-raw has **1** `meson test` target (F-030) | **7** targets, 2803 lines (F-228) |
| cinepi-raw is 24,051 C/C++ LOC (CENSUS §2) | **29,438** (F-231) |
| RAM auto-stop at `cinepi_raw.cpp:200-212` | `:225-229` (F-230) |

**The unreferenced-key count is 12 on both branches.** The four new keys are the HDR family
and cinemate already carries all four in `settings.jsonc`'s `arrays` block — so that feature
landed coherently on both `dev` branches at once. **The drift did not grow.** In a review
whose thesis is systemic drift, that is worth saying plainly.

## The one genuinely new thing, and it matters for ADR-001

**F-227.** `dev`'s `preview/drm_preview.cpp` adds a `--same-hdmi` clone path that walks
`drmModeGetPlaneResources`, selects a plane that is not the primary's and supports the same
fourcc on the second CRTC, and programs it with `drmModeSetPlane` — degrading with
*"no spare plane for the second output; clone disabled"* when none is available.

**cinepi-raw is already doing plane-level DRM composition, and already handles plane
exhaustion gracefully.** That was not visible on `main`, where the path does not exist.

It does not settle PI-009 — cloning to a second CRTC is not overlaying a GUI on the primary
— but it changes what the question is. PI-009 now has a concrete measurement attached:
count the overlay planes on the primary CRTC, with `--same-hdmi` on and off, and see how
many are free. That number is ADR-001 constraint 2 in its answerable form.

Supporting it: **both repos independently describe `--same-hdmi` as making the preview and
the GUI share one HDMI output** (F-229) — cinepi-raw's own option help and cinemate's
`docs/cli-user-guide.md:78`. Two sources saying they compose; neither saying how.

## What still holds

`dualHdmiPreviewStage.cpp`'s DRM-master comment — S03's single strongest piece of ADR-001
evidence, and the basis for likely killing options D and E — is **byte-identical on `dev`**.

## Corrections made during the pass

- **I hypothesised that cinemate `dev` passing `--same-hdmi` to a cinepi-raw `main` binary
  would fail on an unknown flag. Wrong.** The option is registered on both branches
  (`cinepi_options.cpp:174-176`); only the clone *implementation* is `dev`-only. Checked
  before writing it up. It would have been a high-severity finding and it was not real.

## What was NOT re-verified, and is now explicitly marked

`CODE-MAP-cinepi-raw.md` carries a correction banner naming what still needs re-reading on
`dev`: §4's frame lifecycle (`dng_encoder.cpp`, 687 lines changed), and the CCMP preview
stage and LOG-LUT subsystem, which the map does not mention at all because they did not
exist on `main`. `CENSUS.md` §1–2 are marked as `main` figures.

**This is a real hole, not a formality.** A 687-line change to the DNG writer is a rewrite
of the component S03's §4 describes, and the ledger's frame-lifecycle account should be
treated as `main`-only until someone re-reads it. It is the largest single item of
re-verification the review now owes.

## Method note

Reading two repositories on different branches for seven sessions was a silent hazard, and
nothing in the ledger would have surfaced it — D2 recorded the branch honestly and then
every subsequent session inherited it as a given. The check that would have caught it is one
line, and it is now in D2: **`git -C … branch --show-current` must print `dev`** before any
cinepi-raw figure is trusted.
