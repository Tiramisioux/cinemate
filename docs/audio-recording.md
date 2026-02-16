# Audio recording (experimental)

Cinemate records audio alongside the image sequence. Audio is written as `.wav` files into the same folder as the `.dng` frames. The implementation is still experimental and audio/video synchronization needs further investigation.

## Supported microphones
 - **RØDE VideoMic NTG** – recorded in stereo at 24‑bit/48 kHz.
 - **USB PnP microphones** – recorded in mono at 16‑bit/48 kHz.



## .asoundrc Setup

For `dsnoop` support, create a `~/etc/asound.conf`:

```bash

sudo tee /etc/asound.conf >/dev/null <<'EOF'
# --- Hardware handle (use stable card name; change "NTG" if your card shows a different name in `arecord -l`)
pcm.mic_hw {
  type hw
  card "NTG"
  device 0
}

# --- One shared dsnoop backend pinned to the mic's native mode (RØDE NTG: S24_3LE @ 48k, stereo)
pcm.mic_dsnoop {
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

# --- Front-ends: let plug adapt whatever the app asks for (stereo 24-bit or mono 16-bit)
pcm.mic_24bit {
  type plug
  slave.pcm "mic_dsnoop"
}

pcm.mic_16bit {
  type plug
  slave.pcm "mic_dsnoop"
}
EOF

```

Exit nano editor using ctrl+x.
