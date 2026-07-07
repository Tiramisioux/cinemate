# Changelog

Release notes for Cinemate. For downloads, see the [releases page](https://github.com/Tiramisioux/cinemate/releases).

## Version 3.3.2

### libcamera

- Cinemate now uses its own fork of libcamera.

### imx283 driver

- Cinemate now uses its own fork of imx283 driver.
- 2 additional modes: 3840 x 2160 (4K UHD, native crop) and 2736 x 1538 (2.7K 16:9, binned) 

### imx585 driver

- Cinemate now uses its own fork of imx283 driver.

### CinePi-RAW recorder

- **Frame-rate phase lock** — DNG timecode and frame capture is locked to the Pi's wall clock, making audio sync more accurate.
- **More reliable audio sync on 4K / exFAT** — the capture path was reworked (protected helper, dedicated writer thread, wall-clock reconciliation, real-time scheduling) for more reliable WAV sync on demanding modes.
- **Correct Pi 4 RAW** — CSI2-packed frames decode correctly on Pi 4-family boards; raw packing (P/U) is chosen per Pi model automatically.
- **Camera model** — set the camera model manually for each attached sensor.

### Cinemate

- **Storage / media** — multi-drive RAW hot-swap with a standby drive and automatic promotion. Default format is exFAT.
- **Dual-sensor HDMI preview** — with two sensors, both previews show together on the on-camera monitor, side-by-side with a white frame and centre divider. `set preview cam0 | cam1 | cam0+cam1` switches the source live (no restart).

### Raspberry Pi / Bookworm**
- **Boot / install** — faster boot-to-preview on Pi 4/5 (about 10-15 seconds)

## Version 3.3.1

### CinePi-RAW recorder

- New Cinemate fork, reducing CPU load and temperature dramatically and reducing dropped frames.
- Resolution can now be changed without restarting the recorder process, enabling faster mode changes and dynamic resolution switching.
- Better USB microphone sync.

### Cinemate workflow

- exFAT support and filesystem-aware storage profiles for efficient media writes, including IMX585 25 fps at 4K to SSD without frame drops.
- Dynamic resolution switching to match the observed sustainable frame rate for the attached sensor and storage media — for example, IMX585 automatically switches to HD above 25 fps when an SSD is used.
- Hot-swapping between 16-bit and 24-bit USB microphones.
- 4K-class recording modes are visible by default.
- Automatic storage pre-roll can be disabled in `settings.json`.
