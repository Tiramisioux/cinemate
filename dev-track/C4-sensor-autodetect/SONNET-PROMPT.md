# Kickoff prompt for the implementing session

Paste everything below the line into a fresh Sonnet thread.

Note: single repo (cinemate), five commits, no cinepi-raw or libcamera changes.
**Do not start this session until two things are true:** C3 (no-camera start) has landed
on `dev` (C4 rides its advisory gate and NO CAM fallback), and the operator has run gate
G0 (record under a runtime-applied overlay) and told you its verdict — G0 decides whether
the probe continues the same boot (pass) or persists-and-reboots-once (fail). Gates
G1–G5 belong to the operator's hardware session, not this thread.

---

Implement C4 — sensor autodetect: on a boot where the configured overlay produces no
camera and autodetect is on, a probe step tries each candidate sensor overlay at runtime,
identifies the attached sensor and its port by which driver binds, persists the result
into config.txt's camera section, and lets CineMate start the same boot. Autodetect is an
on/off toggle; off means today's explicit per-port selection. imx585 mono is a checkbox
in both modes — it is electrically undetectable.

The full spec is at:
`/Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C4-sensor-autodetect/SENSOR-AUTODETECT-PLAN.md`
on branch `feature/dev-track` — ledger entry C4 in `PLAN.md` beside it.

Read the spec in full before touching anything, and read
`/Users/patrikeriksson/Documents/cinemate/cinemate-handbook/README.md` plus
`orientation/the-traps.md` and `working/changing-the-installer.md` first. Every design
decision in the spec came out of a hardware-proven investigation and operator review:
implement them, don't relitigate.

Ground rules:

- One repo, one branch: `cinemate` (`/Users/patrikeriksson/Documents/cinemate/cinemate`),
  branch `feature/sensor-autodetect` off up-to-date `dev` (which must already contain
  C3), commits C4.1–C4.5 in order. `cd` does not persist between shell calls — use
  `git -C` and absolute paths.
- **Never `git add -A`** (LFS pointer trap) — stage named files only.
- Do not merge to `dev`, do not push without asking, and **do not touch the Pi**. You
  are producing the desk-verifiable half; gates G1–G5 run later on hardware.
- The settings-editor template's JS is ES5 (`var`, `function(){}`) — match it. The
  template embeds base64 font data: filter greps with `awk 'length($0) < 250'`.
- Commit messages: `c4.<n>: <scope> — <one-line outcome>`.

Order matters — C4.1 (boot_config), C4.2 (pane), C4.3 (probe + service), C4.4
(installer), C4.5 (docs). Five places will bite you, all called out in the spec; re-read
those sections before writing them:

1. **The probe must be harmless on a miss.** It never clears or rewrites the camera
   section unless a driver actually bound; a full-sweep miss exits 0 with config.txt
   byte-identical and falls through to C3's NO CAM. Write the fake-binaries dry-run test
   that asserts this.
2. **Never remove a bound overlay.** `dtoverlay -r` only after a candidate failed to
   bind; the winning overlay stays loaded. This is a crash-avoidance rule from Pi
   history, not a style preference.
3. **Mono is operator state.** The `,mono` token is preserved when the probe persists an
   imx585 line for a port whose previous line had it. The pane's Mono checkbox stays
   editable even when the toggle is on and the model rows are read-only.
4. **Two copies of the pane catalogue.** `boot_config.py`'s `SENSOR_MODELS` and the
   template's `CFG_SENSOR_LABELS` / `cfgOverlayLine()` / `currentConfigText()` must
   change together — `imx585_mono` leaves the model list (legacy lines still parse) and
   the mono checkbox arrives in both. Add the parity test the spec asks for.
5. **The service change must survive deployment.** The second
   `ExecStartPre=-/usr/local/bin/sensor-autodetect.sh` goes in the repo unit file, and
   the script must be carried by the root `Makefile` `install` target alongside
   `camera-ready.sh` — confirm it, and say in the commit message that existing Pis need
   `sudo make install` + `daemon-reload`.

Also honor the platform guard: the probe exits 0 (skip, with a log line) on non-BCM2712
platforms — Pi 4 stays explicit-mode only in v1.

Done means:

1. The five commits match the spec (deviate only where the spec contradicts current
   source, and say exactly where and why).
2. New Pi-free tests: `boot_config.py` round-trips (marker on/off/absent, mono token,
   legacy `imx585_mono`, byte-preservation outside the camera sub-region,
   never-synthesize still raises), the probe dry-run against faked `dtoverlay` +
   `cinepi-raw` binaries (hit persists correctly, miss touches nothing), and the
   Python/JS catalogue parity check.
3. Shellcheck clean on `sensor-autodetect.sh`; full existing `_test/` suite green.
4. A closing summary that lists: files touched per commit, which G0 verdict the probe's
   step-4 behavior was built against (continue vs reboot-once), and the exact manual Pi
   commands for the operator's G2–G5 session (`git fetch`/`switch`/`pull --ff-only`,
   `sudo make install`, `daemon-reload`, and how to set the marker + break config.txt
   for G2).

Stop after that summary. Do not start a Pi session, do not run hardware gates, do not
merge.
