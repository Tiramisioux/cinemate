# Audio recording (experimental)

Cinemate records audio alongside the image sequence. Audio is written as `.wav` files into the same folder as the `.dng` frames. The implementation is still experimental and audio/video synchronization needs further investigation.

## Supported microphones
 - **RØDE VideoMic NTG** – recorded in stereo at 24‑bit/48 kHz.
 - **USB PnP microphones** – recorded in mono at 16‑bit/48 kHz.



## .asoundrc Setup

For `dsnoop` support, create a `/etc/asound.conf`:

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

Exit nano editor using ctrl+x.
