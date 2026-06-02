# Audio recording

Cinemate can record audio alongside the image sequence. Audio is written as `.wav` files into the same folder as the `.dng` frames. Timecode is readable by Davinci Resolve, which treats the .dng sequence and wav as one clip.

## Supported paths

- **Preferred 24-bit path:** `mic_24bit` at 48 kHz stereo
- **Preferred 16-bit path:** `mic_16bit` at 48 kHz mono
- **Fallback path:** if neither alias works, Cinemate probes `arecord -l`, builds `plughw:<card>,<device>` aliases, and tries them at 16-bit/48 kHz until one records successfully

In practice this means a RODE VideoMic NTG can use the 24-bit alias, while simpler USB PnP microphones usually fall back to the 16-bit path.

If `arecord` is missing or no recording device can be probed successfully, Cinemate disables audio capture for that run.

## Capture gain from `settings.json`

You can ask Cinemate to apply a capture-side gain to the detected microphone input:

```json
"audio": {
  "capture_gain_db": 0.0
}
```

- `0.0` leaves the input at unity gain
- positive values boost the captured signal
- negative values attenuate it

Because this is applied on the capture side, it is the right place to make the idle mic monitor, the on-screen VU, and the recorded WAV agree more closely.

Cinemate also mirrors this startup value into Redis as `audio_capture_gain_db` so you can later add runtime controls around the same setting.

Not every USB mic exposes a writable ALSA capture control. When a microphone does not, Cinemate leaves the input untouched and logs that no compatible capture control was found.

## `/etc/asound.conf` setup

For `dsnoop` support, create `/etc/asound.conf`:

```bash
sudo tee /etc/asound.conf >/dev/null <<'EOF'
# RODE NTG path (24-bit stereo)
pcm.mic_dsnoop_24 {
  type dsnoop
  ipc_key 5978
  ipc_perm 0666
  ipc_key_add_uid false
  slave {
    pcm "hw:CARD=NTG,DEV=0"
    format S24_3LE
    rate 48000
    channels 2
  }
  bindings.0 0
  bindings.1 1
}

# Cheap USB path (16-bit mono)
pcm.mic_dsnoop_16 {
  type dsnoop
  ipc_key 5979
  ipc_perm 0666
  ipc_key_add_uid false
  slave {
    pcm "hw:CARD=Device,DEV=0"
    format S16_LE
    rate 48000
    channels 1
  }
  bindings.0 0
}

pcm.mic_24bit { type plug; slave.pcm "mic_dsnoop_24" }
pcm.mic_16bit { type plug; slave.pcm "mic_dsnoop_16" }
EOF
```

## ADC clock correction

Some USB audio devices run their internal ADC clock slightly off the nominal 48 000 Hz sample rate. A mic running at 47 946 Hz instead of 48 000 Hz produces a WAV that accumulates ~10 frames of audio-video drift over a 6-minute take with no xruns and no other visible symptoms.

Cinemate corrects this after each take by resampling the finished WAV with `ffmpeg`. The resampling step happens between "Stopped recording" and the next take, so capture performance is unaffected.

### Enabling correction

Set `audio.clock_correction.enabled` to `true` in `src/settings.json`:

```json
"audio": {
  "clock_correction": {
    "enabled": true,
    "database": "resources/audio_clock_correction.json"
  }
}
```

Correction is only applied when **both** conditions are met:
1. `enabled` is `true`
2. The connected mic matches an entry in the database file

### Device database

`resources/audio_clock_correction.json` maps USB mic names to their measured clock offsets. The file contains full instructions at the top — how to find a device name with `arecord -l`, how to measure ppm for a new device using a clap test, and how to add a new entry.

The first verified entry is the RØDE VideoMic NTG at +1130 ppm (ADC runs ~54 Hz slow). The 16-bit plain-arecord path is never resampled regardless of this setting, because the 16-bit capture path is already in sync.

### CLI log output

At each `cinepi-raw` launch, Cinemate logs one of:

```
Audio clock correction: 'RØDE VideoMic NTG' detected — applying +1130 ppm resampling after each take
Audio clock correction: enabled but 'Some Other Mic' has no entry in database — no correction applied
Audio clock correction: disabled in settings (audio.clock_correction.enabled=false)
```

After each take, `cinepi-raw` logs:

```
Applied ADC clock correction: +1130 ppm, declared input 47946 Hz → resampled to 48000 Hz
```

### Correcting existing recordings

**DaVinci Resolve:** right-click the clip in the Media Pool → *Clip Attributes* → *Audio* tab → change *Input Audio Sample Rate* from `48000` to `47946`. Resolve resamples on playback without altering the file.

**Final Cut Pro / other NLEs:** resample the WAV offline first, then reimport:

```bash
ffmpeg -i take.wav \
  -af "asetrate=47946,aresample=48000" \
  -c:a pcm_s24le \
  take_corrected.wav
```

The BWF timecode in the corrected file is preserved.

## GUI indicators

When a compatible microphone is connected, the Simple GUI shows:

- live VU meters on the right side
- the detected sample rate in kHz
- the detected bit depth
- a `WAV` badge once the latest take contains both DNG frames and a WAV sidecar
- the `WAV` badge dims to **light grey** while the previous take's WAV is being resampled for ADC clock correction; it returns to normal grey once the correction is complete
