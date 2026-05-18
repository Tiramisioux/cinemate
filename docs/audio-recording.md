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

## GUI indicators

When a compatible microphone is connected, the Simple GUI shows:

- live VU meters on the right side
- the detected sample rate in kHz
- the detected bit depth
- a `WAV` badge once the latest take contains both DNG frames and a WAV sidecar
