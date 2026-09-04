# Audio recording

## Supported microphones

CineMate has been tested with RODE VideoMic NTG 24 bit microphone and simple 16 bit USB microphones.

## Using the microphone

1. Plug a USB microphone into the Pi.
2. Check for mic, bit depth and sample rate indicator on the left side of the gui. On the right side VU meters should show.
3. When recording `.wav` is written next to the `.dng` frames in the same take folder and a white "wav" label shows up next to the clip name below the preview.

Timecode is readable by DaVinci Resolve, which treats the `.dng` sequence and `.wav` as one clip.

## `settings.jsonc` audio_capture section

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

- **`24bit`** — settings for the 24-bit USB microphones
- **`16bit`** — settings for 16-bit mono generic USB PnP mics

`capture_gain_db` is applied after CineMate probes which path is active and knows the bit depth. `0.0` = unity gain; positive values boost, negative attenuate. 

`timecode_offset_frames` enables manual offset of the embedded timecode. This can be useful if you see a constant offset in the sound. See also [Audio sync & drift](audio-sync.md).
