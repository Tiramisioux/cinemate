# Audio recording

CineMate records a `.wav` alongside the DNG frames, with timecode DaVinci Resolve reads as one clip with the image and audio combined.

## Supported microphones

Tested with the RODE VideoMic NTG (24-bit) and simple 16-bit USB microphones.

## Using the microphone

1. Plug a USB microphone into the Pi.
2. Check the mic, bit depth and sample rate indicator on the left of the GUI. VU meters appear on
   the right.
3. Record. A `.wav` is written next to the `.dng` frames in the same take folder, and a white
   `WAV` label appears next to the clip name below the preview.

## Settings

```json
"audio_capture": {
  "24bit": {
    "capture_gain_db": 6.0,
    "timecode_offset_frames": 2
  },
  "16bit": {
    "capture_gain_db": 6.0,
    "timecode_offset_frames": 2
  }
}
```

The block is split by the bit depth negotiated with the mic: `24bit` for 24-bit USB microphones,
`16bit` for generic 16-bit mono USB PnP mics. CineMate probes which path is active and applies
that block.

`capture_gain_db` is capture gain in decibels. `0.0` is unity, positive boosts, negative
attenuates. Some USB mics expose no writable ALSA control and run at fixed hardware gain; on those
the value is skipped and the log says so.

## Timecode offset

A USB mic can sit a fixed couple of frames early or late against the picture, from analogue and
buffering latency. `timecode_offset_frames` corrects that constant offset.

| Symptom | Change |
|---|---|
| Sound arrives **early**, before the visual | A positive value moves the audio timecode later |
| Sound arrives **late**, after the visual | A negative value moves it earlier |

Only the embedded BWF/iXML timecode metadata is shifted. The PCM samples are never moved, so
nothing is added or lost at the head of the file.

Use this for a fixed, repeatable offset. It does not correct an error that grows over a long take.
