# Audio recording (experimental)

Cinemate records audio alongside the image sequence. Support is currently limited to a few USB microphones with hard coded configurations:
 - **RØDE VideoMic NTG** – recorded in stereo at 24‑bit/48 kHz.
 - **USB PnP microphones** – recorded in mono at 16‑bit/48 kHz.

Audio is written as `.wav` files into the same folder as the `.dng` frames. The implementation is still experimental and audio/video synchronization needs further investigation.

### .asoundrc Setup

For `dsnoop` support, create a `~/.asoundrc` in home directory:

```bash
nano ~/.asoundrc
```

Paste this into the file:

```bash

    pcm.dsnoop_24bit {
        type dsnoop
        ipc_key 2048
        slave {
            pcm "hw:Device,0"
            channels 2
            rate 48000
            format S24_3LE
            period_size 1024
            buffer_size 4096
        }
    }

    pcm.dsnoop_16bit {
        type dsnoop
        ipc_key 2049
        slave {
            pcm "hw:Device,0"
            channels 1
            rate 48000
            format S16_LE
            period_size 1024
            buffer_size 4096
        }
    }

    pcm.mic_24bit {
        type plug
        slave.pcm "dsnoop_24bit"
    }

    pcm.mic_16bit {
        type plug
        slave.pcm "dsnoop_16bit"
    }

```

Exit nano editor using ctrl+x.
