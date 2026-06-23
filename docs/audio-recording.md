# Audio recording

## Quick start

1. Plug a USB microphone into the Pi.
2. Record as normal.
3. A `.wav` is written next to the `.dng` frames in the same take folder.

Timecode is readable by DaVinci Resolve, which treats the `.dng` sequence and `.wav` as one clip.

## Supported paths

- **Preferred 24-bit path:** `mic_24bit` at 48 kHz stereo
- **Preferred 16-bit path:** `mic_16bit` at 48 kHz mono
- **Fallback path:** if neither alias works, Cinemate probes `arecord -l`, builds `plughw:<card>,<device>` aliases, and tries them at 16-bit/48 kHz until one records successfully

In practice this means a RODE VideoMic NTG can use the 24-bit alias, while simpler USB PnP microphones usually fall back to the 16-bit path.

If `arecord` is missing or no recording device can be probed successfully, Cinemate disables audio capture for that run.

!!! info "asound.conf and timecode offset"
    The 24-bit `dsnoop` path needs a one-time `/etc/asound.conf` setup. See [Audio sync & drift](audio-sync.md) for the asound.conf blob and the fixed timecode offset.

## `settings.json` audio section

```json
"audio": {
  "24bit": {
    "capture_gain_db": 0.0,
    "timecode_offset_frames": 0
  },
  "16bit": {
    "capture_gain_db": 0.0,
    "timecode_offset_frames": 0
  }
}
```

- **`24bit`** — settings for the 24-bit USB dsnoop path (`mic_24bit` alias, e.g. RØDE VideoMic NTG).
- **`16bit`** — settings for the 16-bit plain-`arecord` fallback path (generic USB PnP mics).

`capture_gain_db` is applied after Cinemate probes which path is active and knows the bit depth. `0.0` = unity gain; positive values boost, negative attenuate. Not every USB mic exposes a writable ALSA capture control; when a microphone does not, Cinemate leaves the input untouched and logs accordingly.

`timecode_offset_frames` shifts the embedded timecode to fix a constant audio/video offset — see [Audio sync & drift](audio-sync.md).

Pi-local `settings.json` files that still use the old flat keys (`capture_gain_db`, `timecode_offset_frames`, `plain_arecord_timecode_offset_frames`) are migrated automatically on first load.

## GUI indicators

When a compatible microphone is connected, the Simple GUI shows:

- live VU meters on the right side
- the detected sample rate in kHz
- the detected bit depth
- a `WAV` badge once the latest take contains both DNG frames and a WAV sidecar
