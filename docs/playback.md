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

`FPS`, `Resolution`, `Depth` and `Sensor` come straight from the frame's tags. The grey boxes to the right are:

| Box | Meaning |
|---|---|
| `12b`, `16b` | Bits per sample as stored in the file |
| `SDR` | Standard-range capture |
| `HDR` | The take holds more range than a 12-bit sensor mode can carry — ClearHDR, in either its 16-bit linear or 12-bit companded form |
| `LIN` | The samples are linear |
| `CRV` | A curve is baked into the file and a reader must apply it before the levels mean anything |
| `WAV` | The take has audio; `—` means it does not |
| `CNF` | The take is playing at something other than 1.00× because of the conform rate |
| `DROP` | Playback could not hold the rate — see below |

!!! note ""

    There is no HDR flag in a CinemaDNG file. `SDR` / `HDR` is worked out from the white level, which is why it stays correct across all of CineMate's capture modes. For the same reason `CRV` cannot say *which* curve is present: ClearHDR's companding and [CineMate Log](cinemate-log.md) are written to the same DNG tag, and when both apply they are combined into one. The badge reports that a curve exists, not which one.

**Source** says where the picture came from: `Thumbnail` for a take that carries cinepi-raw's embedded DNG thumbnail (the fixed-size mono or colour plane it writes alongside the raw image, when built with the toggle on), `Raw decode` for one demosaiced from the raw image at the preview scale below. Never guess which you are looking at — a 720p thumbnail and a demosaiced quarter-res frame are different pictures of the same take, and only a raw decode is affected by the preview scale or monochrome-sensor settings. Source is a property of the take, not of any one frame: cinepi-raw's toggle cannot change mid-take, so every frame in a take answers the same way.

## Rate readouts

| Readout | Meaning |
|---|---|
| **Recorded** | The rate the take was shot at, from its DNG tags |
| **Conform** | The conform rate in force, or `off` |
| **Playing at** | The resulting speed, e.g. `0.50× SLOMO` |
| **Achieved** | The rate playback is *actually* managing, measured continuously |
| **Frames skipped** | How many frames have been skipped to hold the clock |

**Achieved is measured, not assumed.** When the camera cannot decode frames fast enough, playback holds the clock and skips frames rather than letting the take quietly run slow — so the timing you see stays honest and the cost shows up as a skip count and a `DROP` badge. If you are seeing skips, drop the preview scale.

## Preview scale

Decoding is what costs time, and cost falls with the size of the picture. Each option shows the pixel size it produces for the selected take:

| Scale | On a 3856×2180 take | On a 2028×1520 take |
|---|---|---|
| `1/2` | 1928×1090 | 1014×760 |
| `1/4` (default) | 964×545 | 507×380 |
| `1/8` | 482×272 | 253×190 |

`1/2` is as fine as it goes. Reading the card is also part of the cost, and it halves with each step — on 4K takes that is often what decides whether playback holds the rate, especially on slower storage.

## Monochrome sensors

CineMate tags every frame with a colour filter pattern, including on a monochrome sensor — nothing in the file distinguishes the two. Turn **Monochrome sensor** on for takes shot on a mono sensor; leaving it off renders them through a colour pattern and produces a convincing but wrong image.

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
