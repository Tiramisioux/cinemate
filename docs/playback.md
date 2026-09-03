# Playback

Play a recorded take back in the browser, without taking the card out. Frames are decoded from the CinemaDNG files on the card as you play — nothing is transcoded, and nothing is written back to the take.

Playback runs at the **conform frame rate**, so a take shot faster than the conform rate plays as slow motion, at the speed it will run on the timeline.

## Reaching it

The pane is a tab in the settings editor:

```
http://cinepi.local:5000/settings-editor/
```

Choose **Playback · review takes**. Over the camera's own hotspot the settings editor is at `http://10.42.0.1:5000/settings-editor/` (see [Configuring the Wi-Fi hotspot](hotspot-logic.md)).

## Choosing a take

**Takes on card** lists every take across mounted storage, newest first, with a thumbnail from its first frame. Each card shows the take name, its frame count and its recorded frame rate, plus badges:

| Badge | Meaning |
|---|---|
| `RAW`, `RAW1`, `RAW2` | Which mounted drive the take is on — `RAW` is the active one |
| `HDR` | The take holds HDR-range data (see [Take metadata](#take-metadata)) |
| `WAV` | The take has an audio sidecar |
| `0.50× SLOMO`, `2.00× FAST` | The take's playback speed against the conform rate. Absent when the take plays at 1.00× |

## Playing

Transport controls sit under the picture: first frame, previous frame, **PLAY**, next frame, last frame, and a loop toggle. Drag anywhere on the filmstrip to scrub — it holds sixteen frames sampled evenly across the take, with the playhead marking the current position. The take's name and the elapsed position show over the top of the picture.

Playing again from the last frame restarts from the beginning unless loop is on.

## Playback speed and the conform frame rate

Playback is paced by `settings.conform_frame_rate` (see [Settings file](settings-json.md)), not by the rate the take was shot at. That is the point: what you see is what the take will do once it is conformed in post.

- A take shot **above** the conform rate plays as slow motion. 50 fps on a 25 fps conform plays at 0.50×.
- A take shot **below** it plays fast.
- A take shot **at** it plays at 1.00×.

Turn **Use conform frame rate** off to play each take at the rate it was shot instead.

!!! note ""

    Speed ramps replay correctly with no extra setting. Every DNG carries its own frame rate, and in conform mode playback simply steps one frame per conform tick — so a take whose frame rate changed mid-shot plays back with the ramp intact.

## Take metadata

Everything in this row is read from the take's own DNG files, not from what the camera is set to now — so an old take reads correctly even if the camera has been reconfigured since.

`FPS`, `Resolution`, `Depth` and `Sensor` come straight from the frame's tags. `Depth` is the take's *original/source* depth, not necessarily the literal `BitsPerSample` stored in the file — a log-encoded take compresses to 10-bit for storage, and showing that number instead of what the take was actually shot at (12-bit SDR or 16-bit ClearHDR) was more confusing than useful. Look for `LOG10` if you want to know whether that compression happened. The grey boxes to the right are:

| Box | Meaning |
|---|---|
| `12b`, `16b` | Bits per sample the take was shot at |
| `SDR` | Standard-range capture |
| `HDR` | The take holds more range than a 12-bit sensor mode can carry — ClearHDR, in either its 16-bit linear or 12-bit companded form |
| `LIN` | The samples are linear |
| `CRV` | A curve is baked into the file and a reader must apply it before the levels mean anything |
| `LOG10` | The take was log-encoded and stored as 10-bit — `Depth` already shows the original depth it was shot at, this just says the compression happened |
| `WAV` | The take has audio; `—` means it does not |
| `CNF` | The take is playing at something other than 1.00× because of the conform rate |
| `DROP N` | The *recording* is missing `N` frames — a gap in cinepi-raw's own frame-numbering, read from the filenames on disk. Nothing to do with this playback session's own speed; no badge means either zero drops or the frame numbering couldn't be read, not necessarily a clean take |

!!! note ""

    There is no HDR flag in a CinemaDNG file. `SDR` / `HDR` is worked out from the white level, which is why it stays correct across all of CineMate's capture modes. For the same reason `CRV` cannot say *which* curve is present: ClearHDR's companding and [CineMate Log](cinemate-log.md) are written to the same DNG tag, and when both apply they are combined into one. The badge reports that a curve exists, not which one. `LOG10` is the one exception: `BitsPerSample` 10 with a table is unambiguous, since nothing else ever produces that combination (no native 10-bit sensor mode or ClearHDR companding carries a table at 10 bits), so this one badge can say more than "a curve exists."

**Source** says where the picture came from: `Thumbnail` for a take that carries cinepi-raw's embedded DNG thumbnail (the fixed-size mono or colour plane it writes alongside the raw image), `No thumbnail` for one that doesn't. A take with no thumbnail — recorded with the toggle off, or before a rebuilt cinepi-raw supported it — currently cannot be played back at all: raw decode is far more demanding on the Pi and is not used as a fallback. Source is a property of the take, not of any one frame: cinepi-raw's toggle cannot change mid-take, so every frame in a take answers the same way.

## Rate readouts

| Readout | Meaning |
|---|---|
| **Recorded** | The rate the take was shot at, from its DNG tags |
| **Conform** | The conform rate in force, or `off` |
| **Playing at** | The resulting speed, e.g. `0.50× SLOMO` |
| **Achieved** | The rate playback is *actually* managing, measured continuously |
| **Frames skipped** | How many frames have been skipped to hold the clock |

**Achieved is measured, not assumed.** When the camera cannot decode frames fast enough, playback holds the clock and skips frames rather than letting the take quietly run slow — so the timing you see stays honest and the cost shows up as a skip count.

## While recording

Playback is refused while a take is recording, and the picture greys out with the reason. Reading gigabytes off the card while another take is being written to it risks dropped frames and audio glitches, and a take in progress always wins. Playback becomes available again as soon as recording stops.

## What it does not do

- **It is not a grading reference.** The preview is decoded quickly and simply — one pixel per sensor colour cell, with a plain gamma and no colour management. It is for judging framing, focus and motion, not colour.
- **It does not play audio.** A take's WAV is served at `/settings-editor/api/playback/clips/<take>/audio` if you want to fetch it, but the pane itself has no audio playback.
- **It does not alter the take.** Nothing is written to the card. Frames are decoded on demand and discarded.

## If playback stalls

| Symptom | Cause |
|---|---|
| `DROP` badge and a rising skip count | The camera cannot decode at this size. Lower the preview scale |
| Playback stops on its own | The browser tab was moved to the background. Browsers throttle background tabs to about one tick a second, so playback stops rather than reporting a skip count that means nothing |
| Picture greys out mid-playback | A recording started |
| A take listed with no metadata | Its first frame could not be read — the take is still listed rather than hidden |
