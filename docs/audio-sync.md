# Audio sync & drift

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
