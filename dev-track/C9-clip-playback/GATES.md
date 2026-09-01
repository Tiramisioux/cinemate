# C9 · Hardware gates

Method per `cinemate-handbook/working/hardware-session.md`: state the prediction **before**
running, then record the verdict in `cinemate-handbook/lessons/hardware-log.md` (Tested / Worked /
Did not work / Why / Confirmed by) once the operator confirms the interpretation. A command
exiting cleanly is not a finding.

Ten gates, grouped into four sessions rather than listed as peers, because four of them need
hardware the dev Pi does not currently have plugged in. **G1 and G2 gate everything after them** —
together they decide which modes get real-time playback and therefore the default preview scale.
G0 is cheap and validates the desk analysis before any number is trusted; G9 decides whether the
pane is honest at all on the modes it most exists for.

| Session | Gates | Needs |
|---|---|---|
| **A** — no hardware change | G0, G1 (isolated + loaded), G3, G5, G6 | takes already on the card, a phone on the hotspot |
| **B** — imx585 attached, shooting | G7, G9, G8, then G1 re-run on fresh UHD/ClearHDR takes | a sensor swap and a shooting session |
| **C** — destructive | G4, then G2's three-filesystem loop **last** | consent to spoil a take and to reformat `/media/RAW` |
| **D** — optional, blocked | G5 on 2 GB | a 2 GB CM5, which the operator does not currently have |

`G1`–`G8` keep the numbers they were filed under on 2026-08-27. `G0` (baseline) and `G9`
(rendered-pixel correctness) are new, added 2026-09-01 when the plan was re-grounded; nothing was
renumbered.

Every gate is driven from the Mac with `scripts/pi_ssh.sh '<command>'` (`pi@cinepi.local`,
`PI_PASSWORD` from the environment only, never on a command line), and files move with
`scripts/pi_expect.exp "$PI_PASSWORD" scp …`. Both run under `expect` on a PTY, so their stdout
carries an injected `spawn ssh` line, a password line and CRLF on every line — strip those before
pasting any output into a ledger. Driving cinemate itself (mode selection, takes, settings) goes
through `scripts/pi_cinemate_cli.sh`; its `start` kills any running `main.py` and `cinepi-raw`, so
re-issue `set fps free 1` and `set dynamic resolution 0` after every session start or a requested
mode is silently substituted and the take is invalid data.

**Recording the outcome.** One row per gate, appended to this file under the gate as it runs:
verdict from the fixed vocabulary **CONFIRMED / CONTRADICTED / NOT-RUN-because**, the source
command that produced each number, and the Pi-side and Mac-side commits. Never rewrite a filled
row. A cell with no number says why rather than looking unfilled.

---

## Baseline of record (to be re-verified by G0)

| | |
|---|---|
| Board | CM5 Lite, `bcm2712`, **4048 MB** — not 2 GB (PI-016; `ADR-001:14-21` records the premise error) |
| Kernel | `6.12.93+rpt-rpi-2712` |
| `pll_sys` / `clk_sys` | **200 MHz** — RP1 overclock installed but off |
| Attached sensor | **imx477** on cam0. No 3856×2180 mode, no ClearHDR, no log support |
| `/media/RAW` | One NVMe volume, `LABEL=RAW` written directly to `/dev/nvme0n1` — **no partition table**, no second RAW device |
| Measured write bandwidth | ~110 MB/s at 2028×1520 10-bit; **170–190 MB/s sustained** at 4056×3040 12-bit, `drop_frame=0` (PI-016) |
| Measured read bandwidth | **None. Nothing in this stack has ever measured it** — C1's phase 0.4 is write-only and has not run |

The sensor row is why G1's UHD figures, G7, G8 and G9 are all *unrunnable as filed* on the current
rig: they need the imx585. Session B begins with the swap.

---

## G0 — the baseline is what we think it is, and the branch is current

**Belief being tested.** That the numbers every other gate is measured against still describe this
Pi, and that the code under test is the code that will land. Both halves have already failed once:
the plan reasoned from a 2 GB board that is 4 GB, and its branch is 1381 commits behind `dev`.

**Why hardware.** Half of it is not — the rebase is desk work. But the board, RAM, kernel, sensor,
filesystem and PCIe link state can only be read on the Pi, and reading them costs a minute against
gates that cost a session.

**Procedure.** Desk first: rebase `feature/clip-playback` onto current `dev`, run the six checks
(`ruff check src/`; `python -m pytest _test/ -q -p no:randomly`; the three `tools/` checks with
their CI thresholds), push it. Then on the Pi, after `git fetch && git switch feature/clip-playback
&& git pull --ff-only`:

```bash
uname -r; free -m; grep Revision /proc/cpuinfo
findmnt -no SOURCE,FSTYPE,OPTIONS /media/RAW
grep -n pciex1 /boot/firmware/config.txt; sudo lspci -vv | grep -A2 LnkSta
redis-cli GET sensor
python3 -c "import numpy, PIL, werkzeug; print(numpy.__version__, PIL.__version__, werkzeug.__version__)"
git -C ~/cinemate rev-parse --short HEAD
```

Then run the plan's own metadata reader against one real take on the card and print the tag dump —
`StripOffsets`, `RowsPerStrip`, `BitsPerSample`, `WhiteLevel`, `BlackLevel`, presence of
`LinearizationTable`, `CFAPattern`, `FrameRate`.

**Prediction.** Kernel ≥ 6.12.93, 4048 MB, `/dev/nvme0n1 ext4`, `dtparam=pciex1_gen=3` present and
the link negotiated Gen3 x1, `sensor` reads `imx477`, numpy 2.x. The tag dump confirms
`StripOffsets == 8` and `RowsPerStrip ==` height — which is the cheapest empirical check of the
cinepi-raw layout claims this plan has been asserting from an external workspace.

**If it disagrees:** a Gen2 link (~380 MB/s practical) makes G2's 160 MB/s read alongside a
190 MB/s write already near the bus ceiling, and G4's prediction changes with it. A kernel below
6.12.93 does **not** block G1 or G2 — that floor is a *capture* requirement for 16-bit CSI-2
(`docs/clear-hdr.md:9`), and decoding an existing 16-bit DNG in userspace is unaffected. It blocks
G7 only.

---

## G1 — decode throughput

**Belief being tested.** That the Pi is no more than ~6× slower per core than the Apple Silicon
Mac the plan's numbers came from — precisely, ≤ 5.97× at a 25 fps conform. Everything downstream
depends on this number.

**Why hardware.** It is the one quantity no amount of source reading settles, and the Mac
measurement is on a different ISA, memory system and compiler.

**Procedure.** `tools/playback_bench.py` (C9.5) on the Pi, from the repo checkout — numpy and
Pillow are already installed on every camera, so nothing needs copying. 15-iteration median at 1/2,
1/4 and 1/8 with 1, 2 and 4 workers, against a UHD take and a 2K take, recording
`numpy.__version__` alongside. Then **run it a second time with CineMate running and a live
preview up** — `scripts/pi_cinemate_cli.sh start`, browser on `:5000`.

**Prediction.** Isolated: UHD at 1/4 with 2 workers lands at or under `1000 / conform_frame_rate`
ms — 40 ms at a 25 fps conform, 41.7 at 24, 33.3 at 30. 2K at 1/2 comes in comfortably under it.
Loaded: 15–35% worse, since cinemate alone is measured at 31.8–33.5% CPU during a take and its
HDMI GUI redraw shares the process.

**If it disagrees:** the isolated figure is a ceiling and the loaded figure is the one Phase 3's
default-scale rule consumes. If UHD at 1/4 misses under load but 1/8 holds, UHD defaults to 1/8;
if neither holds, UHD is scrub-only and 2K keeps a real-time default. Do not "fix" a miss by
raising the worker count past 2 — cores 0–2 are shared with the GUI and the camera, and core 3 is
isolated.

---

## G2 — storage read bandwidth, and what the drive actually transfers

**Belief being tested.** Two claims, one of which has never been tested anywhere in this stack.
First, that `/media/RAW` reads at ≥ 160 MB/s (UHD at 1/4) and ≥ 80 MB/s (2K at 1/2) — the plan's
requirements are 158 and 79, so state the bar as **≥ 1.15× the required rate** rather than two
inconsistent roundings. Second, and more important: that a row-selective read *transfers* less than
a whole frame. Nothing in this stack tunes `read_ahead_kb`, so at a ~5.8 kB row stride under the
128 kB default the block layer may move the entire 12.6 MB regardless.

**Why hardware.** No read bandwidth has ever been measured on this Pi, and the readahead question
is a property of this kernel, this filesystem and this drive.

**Procedure.** Two measurements per filesystem, not one.

*(a) Sequential ceiling.* Cold cache, direct I/O, differenced — `dd`'s `status=progress` prints a
cumulative average that can never show a cache step, so use C1's awk differencer:

```bash
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
cat /media/RAW/<take>/*.dng > /tmp/c9_seq.bin      # ~30 frames, long enough to leave any cache
dd if=/tmp/c9_seq.bin of=/dev/null bs=4M iflag=direct status=progress 2> /tmp/c9_dd.txt
tr '\r' '\n' < /tmp/c9_dd.txt | awk '/copied/{b=$1+0; t=$(NF-1)+0; if (pt) printf "%.1f MB/s\n", (b-pb)/1048576/(t-pt); pb=b; pt=t}'
```

*(b) Decoder-realistic.* Cold cache, then `tools/playback_bench.py --io`, which samples
`/proc/diskstats` around N decoded frames at each scale and reports **bytes read from the device
per frame** alongside wall clock.

Repeat both for ext4, exFAT and NTFS. Each pass reformats the only RAW volume — use the RAW pane's
Format control (C0, proven on this drive on 2026-08-26 and again 2026-09-01) or `format
ext4|exfat|ntfs` through the CLI session — so **G2 runs last in its session**, after every gate that
needs takes on disk. A format ends in a remount, and storage pre-roll subscribes to mount events:
wait for `Storage pre-roll complete` in the log before starting any measurement, and do not disable
`auto_preroll` to dodge it — C1's precedent is that changing it confounds cross-run comparison.
Record `findmnt -no SOURCE,FSTYPE /media/RAW` in each result row, and time a full
`raw_files.list_takes()` per filesystem while you are there: the clip index is dominated by `stat()`
calls, and that cost is filesystem-dependent.

**Prediction.** (a) A drive measured *writing* 170–190 MB/s reads at or above that on ext4, so the
UHD bar passes with room; if the sequential read comes in under 160 MB/s the surprise is the drive,
not the decoder. exFAT is close behind; NTFS is slower and is already documented as unsuitable for
sustained recording, so a poor NTFS result is consistent with what the code believes and is not a
finding. (b) Device bytes at 1/4 land **well above** the 6.3 MB the plan credits — plausibly the
full 12.6 MB — because readahead does not know which rows will be discarded.

**If it disagrees:** if (b) shows no reduction with scale, the plan's central storage claim is
wrong and UHD at 1/4 needs 315 MB/s, not 158 — which moves "marginal on a USB SATA SSD" to "out of
reach" and makes the honest default scale the one (b) supports, not the one (a) does. Before
concluding, try one `blockdev --setra` pass at a smaller readahead: if that recovers the reduction,
the finding is tunable rather than fatal, and Phase 3 gains a tuning item.

---

## G3 — serving frames without starving the rest of the process

**Belief being tested.** That the **Werkzeug development server in threading mode** — which is what
ships, `allow_unsafe_werkzeug=True` at `main.py:937`, no eventlet or gevent anywhere — can serve
frames at the conform rate without starving the Socket.IO push or the HDMI GUI that live in the
same process.

**Why hardware.** It is a three-way contention question between a GIL-releasing decode pool, a
push channel and a framebuffer redraw loop, over real Wi-Fi.

**Procedure.** Play a take through the real route from a browser on the hotspot. Record three
things at once, not one: client-side achieved fps and skip count from the pane's own HUD; the
round-trip latency of a parameter change while playback runs (`redis-cli SET iso 800; redis-cli
PUBLISH cp_controls iso`, timed to the browser's update); and the HDMI GUI's redraw cadence.
Capture `python3 -c "from importlib.metadata import version; print(version('werkzeug'))"` in the
result row.

**Prediction.** Client fps holds the conform rate with the decode cap in place; the parameter
round-trip stays under ~500 ms; the HDMI GUI's cadence stays near its measured ~7.5 Hz (its target
is 12 fps and it already misses it on this board — the question is whether playback makes it
worse).

**If it disagrees:** a gate that only measured fps would pass while the shooting UI froze, which is
the failure that actually matters — so a fps pass with a cadence collapse is a **fail**, and the
fix is a lower decode cap, not a faster decoder. On werkzeug < 2.1 there is no HTTP/1.1
auto-upgrade and every frame becomes a fresh TCP connection over Wi-Fi; that shows up as a
throughput collapse no decoder tuning fixes, which is why the version is recorded.

---

## G4 — playback during recording

**Belief being tested.** That refusing playback mid-take is necessary rather than merely cautious.
Two mechanisms could make it necessary and the gate must tell them apart: **storage** (every
non-fallback media profile sets the I/O scheduler to `none`, so there is no kernel arbitration
between the read and write streams) and **CPU** (no core is free during a take; the decode pool is
unpinned and may land on the isolated audio core).

**Why hardware.** Contention on a real drive and a real scheduler, with a real microphone attached.

**Procedure.** Record a control take, then an identical take with playback attempted throughout. For
each, capture: `write_speed_to_drive` and the frames-written count; `ps -eLo pid,comm,rtprio,psr`
during the take, so the decode threads' core placement is on record; and the session log grepped
for the **silence-fill line**, not for xruns:

```bash
grep -nE 'Inserted [0-9]+ silent frame|capture shortfall|Capture read failed' /tmp/cinemate_cli.log
```

**A recovered ALSA xrun logs nothing at all.** The two lines that contain the word "xrun" both mean
the opposite of one — a failed SCHED_FIFO grant, and the helper being absent — and a hit on either
voids the take's audio verdict as a rig fault rather than counting as evidence. The WAV is padded
back to wall clock when silence is inserted, so duration alone looks perfect while samples were
lost: always check both.

**Prediction.** On this NVMe rig, **no** silence-fill lines and no dropped frames — the drive has
170–190 MB/s of proven write headroom on a PCIe bus the USB microphone does not share, unlike the
Pi 4 case the code caps workers for. The interesting result is the negative one: silence-fills
anyway would point at CPU/core contention, visible as a decode thread sharing `psr 3` with the
capture thread.

**If it disagrees:** if losses appear only with a decode thread on core 3, the fix is affinity on
the decode pool (within cores 0–2, honouring `storage_profiles.py:41-49`), not refusing playback —
a materially different Phase 3 outcome, and this is the only gate that can distinguish them. Either
way, note that an in-progress take's WAV is unfinalised by construction, so "degrade" can never
include audio.

---

## G5 — memory headroom, and what the ring leaves behind

**Belief being tested.** Not the one originally filed. The 80% auto-stop the plan named
(`RAM_LIMIT_PERCENT`, `cinepi_controller.py:255`) lives inside `_recording_worker`, a thread armed
only by `start_recording()` — so it is **not running during playback at all**, and a gate that asks
whether playback approaches it cannot fail. The real exposure is residual: what the decode cache
leaves resident for the *next* take.

**Why hardware.** Page-cache behaviour under a 158 MB/s read stream on a 4 GB board.

**Procedure.** Sample the number the guard actually uses — `psutil.virtual_memory().percent`, which
is derived from `MemAvailable` and therefore excludes reclaimable page cache — at 1 s cadence
during playback at each scale, alongside the cinemate process RSS (`ps -o rss=,pcpu= -p $(pgrep -f
main.py)`). Then start a take immediately after a playback session and watch the same numbers
through it.

**Prediction.** `free -m`'s *free* column collapses (PI-016 already saw 2583 → 1093 MB during a
take) while *available* stays high — that is page cache and is not pressure. Available never drops
below ~2500 MB of 4048 at any scale, RSS grows by tens of MB not hundreds, and a take started
straight after playback behaves like any other.

**If it disagrees:** report absolute MB, not percentages, so the 2 GB verdict can be derived
arithmetically and **stated as derived, not measured** — ADR-001 records that the dev unit is 4 GB
and that 2 GB remains an unmeasured target the project does not have hardware for. Do not sample
`free -m`'s *free* column as the pass criterion; it measures something the guard cannot see.

---

## G6 — hotspot throughput, with the live stream running

**Belief being tested.** That the AP sustains the delivery rate. The requirement is small — ~32 kB
per 964×545 q80 frame, 6.4 Mbit/s at 25 fps — so the realistic failure is not raw throughput but
the **second stream**: the settings editor's Live tab embeds `<iframe src="/">` and nothing ever
clears it, so once visited, the shooting screen's MJPEG stream and its Socket.IO connection stay
live behind the playback tab on the same link.

**Why hardware.** Wi-Fi, at range, with the real client.

**Procedure.** `sudo apt-get install -y iperf3` on the Pi (it is in neither the installer nor any
requirements file), `iperf3 -s -1`, then from a phone joined to SSID `CinePi` run a 60 s client
against `10.42.0.1` in the **download** direction (`-R`) — frames flow Pi→phone. Run it twice: with
the Live tab never visited, and with the MJPEG stream running behind the playback tab. Record the
sustained figure, not the peak.

**Prediction.** ≥ 10 Mbit/s sustained with no MJPEG stream, comfortably clearing the 6.4 needed at
1/4. With MJPEG running, materially less — enough that clearing the iframe's `src` on tab-leave
(Phase 1 defect 5) is what makes the margin real rather than nominal.

**If it disagrees:** if G1/G2 licence scale 1/2 rather than 1/4, the delivery requirement is ~4×
and this gate's bar is wrong — re-derive it from the licensed scale before reading the verdict.

---

## G7 — mode inference on fresh takes

**Belief being tested.** That `describe_mode()` classifies every mode this stack emits from the
level tags alone, and that the log/CCMP case is genuinely ambiguous rather than merely unhandled.
The plan's original claim — verified across every mode the encoder emits — was overstated: the
three non-log modes were checked, the **10-bit log target was not**, and 10 is the only log target
available on every 12-bit mode.

**Why hardware.** It needs takes that do not exist: ClearHDR and log require the imx585, and the
composed-table case only occurs on a real log-over-ClearHDR take.

**Procedure.** imx585 attached, kernel ≥ 6.12.93 (the 16-bit capture floor applies *here*, not to
G1). Four takes on a **named** dev commit, not "current dev": SDR 12-bit; ClearHDR 12-bit; ClearHDR
16-bit; and a log take over 12-bit ClearHDR. ClearHDR is selected by picking an HDR sensor mode
(`set resolution <n>`, which sets the `hdr` key and relaunches cinepi-raw with `--hdr sensor`); log
by `set log`, resolved at the next camera restart. `rec f 25` each, camera restart between. Then
`describe_mode()` on one DNG from each.

**Prediction.** 12-bit no table → SDR; 16-bit no table → ClearHDR 16-bit linear; 12-bit with a table
at WhiteLevel 62704/63265 → ClearHDR 12-bit companded; log over 12-bit ClearHDR → **indistinguishable
from the previous row**, badged `CRV`. That fourth row passes by confirming an ambiguity, which is
unusual enough to state plainly so a later reader does not score it as a failure.

**If it disagrees** — that is, if the log take *is* separable from the companded one — then a `LOG`
badge has a signal on disk to justify it and open decision 6 in the plan reopens. Capture
`redis-cli GET sensor` in the result row: it carries the `_mono` suffix, which is what the pane's
mono toggle defaults from.

---

## G8 — CFA orientation under flips

**Belief being tested.** That the DNG's `CFAPattern` tracks the sensor flips, so a decoder that
honours the tag gets colour right on flipped footage.

**Why hardware.** Flips reach the sensor only as `--hflip`/`--vflip` on the cinepi-raw command line
at launch (`cinepi_multi.py:438-473`); there is no live toggle and no way to simulate it.

**Procedure.** For each of (off,off), (on,off), (off,on), (on,on) under `sensors.cam0.geometry` in
settings.jsonc — and, if time allows, `rotate_180`, which the gate as filed did not mention —
restart the camera, `rec f 10`, and read tag 0x828E out of one DNG. Four restarts, four short takes.

**Prediction.** `CFAPattern` changes with the flips, and a decoder that reads the tag per take is
correct with no further work.

**If it disagrees** — the tag stays `RGGB` while the pixels move — colour is wrong on flipped
footage and `dng_preview.py` needs its own correction derived from the take's geometry, which it
cannot read from the DNG. That would be a new Phase 3 item and a new honesty problem, since nothing
on disk records the flip.

---

## G9 — the decoder renders a real image, not a black one

**Belief being tested.** That `dng_preview.py` applies the `LinearizationTable` and subtracts
`BlackLevel` in the **table's output domain**. This is not established. `docs/cinemate-log.md:63`
names it as the first diagnostic for a grading complaint and states the failure exactly: a decoder
that skips the table renders a log clip **solid black**, because it subtracts a linear-domain
BlackLevel from data that never reaches it. Every other C9 gate measures speed or classification;
none looks at a pixel.

**Why hardware.** It needs the four real takes G7 shoots. (The *code* question can and should be
answered at the desk first, by reading the decode path — do that before the session, and if the
table is not applied, fix it before shooting rather than confirming a known bug on the Pi.)

**Procedure.** With G7's four takes, decode one frame from each at 1/4 and record mean luma, the
5th and 95th percentiles, and the fraction of pixels at zero. Compare each against the SDR take as
a linear reference at matched exposure. Keep one PNG per mode with the result row.

**Prediction.** All four render as recognisable images. Mean luma sits within a factor of ~2 of the
SDR reference and the zero-pixel fraction stays under a few percent on every mode. Colour is
uncorrected on the ClearHDR takes — AWB cannot run at 16-bit — so a blue-green cast is expected and
is **not** a failure of this gate.

**If it disagrees:** a black or near-black frame on the companded or log takes means the table is
not being applied, and the pane is dishonest on exactly the modes it most exists for. That blocks
Phase 3 outright — before any default-scale decision, because a fast black frame is worse than a
slow correct one.
