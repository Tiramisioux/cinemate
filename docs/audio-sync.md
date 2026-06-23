# Audio sync & drift

Advanced page for fine-tuning audio/video sync. If your `.wav` plays in sync, you do not need anything here.

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

## Fine timecode offset

A USB mic can sit a fixed couple of frames early or late relative to video (constant analog/buffering latency). Correct that offset per toolchain in `src/settings.json`:

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

This shifts only the embedded BWF/iXML timecode metadata; the PCM samples are never moved.
