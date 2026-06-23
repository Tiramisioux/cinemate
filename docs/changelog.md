# Changelog

Release notes for Cinemate. For downloads, see the [releases page](https://github.com/Tiramisioux/cinemate/releases).

## Version 3.3.1

**CinePi-RAW recorder:**

- New Cinemate fork, reducing CPU load and temperature dramatically and reducing dropped frames.
- Resolution can now be changed without restarting the recorder process, enabling faster mode changes and dynamic resolution switching.
- Better USB microphone sync.

**Cinemate workflow:**

- exFAT support and filesystem-aware storage profiles for efficient media writes, including IMX585 25 fps at 4K to SSD without frame drops.
- Dynamic resolution switching to match the observed sustainable frame rate for the attached sensor and storage media — for example, IMX585 automatically switches to HD above 25 fps when an SSD is used.
- Hot-swapping between 16-bit and 24-bit USB microphones.
- 4K-class recording modes are visible by default.
- Automatic storage pre-roll can be disabled in `settings.json`.
