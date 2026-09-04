# Audio sync & drift

## Fine timecode offset

A USB mic can sit a fixed couple of frames early or late relative to video (constant analog/buffering latency). This can be correct by adding an offset `settings.jsonc`:

```json
"audio_capture": {
  "24bit": { "timecode_offset_frames": 1 },
  "16bit": { "timecode_offset_frames": 0 }
}
```

If sound arrives **early** (before the visual), try adding a *positive* value to nudge the timecode. If sound arrives **late** (after the visual), try adding a *negative* value.

Note that this shifts only the embedded BWF/iXML timecode metadata; PCM samples are not moved.
