# Audio sync & drift

Advanced page for users chasing long-take audio/video drift. If your `.wav` plays in sync, you do not need anything here.

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

Cinemate corrects this after each take: `cinepi-raw` folds the resampling into the single post-take `ffmpeg` pass that writes the WAV's BWF/iXML metadata. It runs between "Stopped recording" and the next take, so capture performance is unaffected, and because it is one pass with no intermediate file, no stray WAV is ever written into the take folder.

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

### Fine timecode offset

Clock correction fixes *progressive* drift. A USB mic can also sit a fixed couple of frames early or late relative to video (constant analog/buffering latency). Correct that residual offset per toolchain in `src/settings.json`:

```json
"audio": {
  "24bit": { "timecode_offset_frames": 1 },
  "16bit": { "timecode_offset_frames": 0 }
}
```

| Symptom | Value |
|---------|-------|
| Sound arrives **early** (before the visual) | positive — e.g. `1` |
| Sound arrives **late** (after the visual) | negative — e.g. `-1` |

This shifts only the embedded BWF/iXML timecode metadata; the PCM samples are never moved. It stacks on top of ADC clock correction.

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
