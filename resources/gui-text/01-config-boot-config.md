# Boot config
<!-- sidebar group `boot-config` · tab: config.txt -->

Edit the headings and the paragraphs. Leave the `<!-- key: ... -->` lines alone —
they are what the GUI looks each string up by when CineMate starts.

---

## Boot config
<!-- key: pane.bootconfig -->

What loads at power‑on — sensor overlays, hardware buses, the RP1 overclock. Lives in `/boot/firmware/config.txt`, a different file from Cinemate's own settings.

### (note box)
<!-- key: note.bootconfig.0 -->

Every change here needs a full **reboot** to take effect — restarting Cinemate alone won't pick it up. Cinemate only manages the block fenced between its install markers; anything you add outside it survives updates.

### Camera 0 sensor
<!-- key: card.bootconfig.0 -->

Which driver loads on the cam0 connector. Only one overlay per port — Cinemate comments out the others for you.

### Camera 1 sensor
<!-- key: card.bootconfig.1 -->

Same idea for cam1, if you're running dual sensors.

### RP1 overclock
<!-- key: card.bootconfig.2 -->

Raises the RP1 I/O die clock so higher sensor frame rates are reachable. Needs the overlay built first and a stable supply. The clock is set by the device tree at boot, so this only takes effect after a reboot — and it's what unlocks the link-frequency picks below.

### Camera 0 link frequency
<!-- key: card.bootconfig.3 -->

CSI-2 lane rate for the IMX585 on cam0 — this is what sets the frame-rate ceiling.

#### (inline warning, shown only when it applies)
<!-- key: warn.bootconfig.0 -->

Anything above the default needs the RP1 overclock; without it the RP1 caps out near 43.8 fps at 4K whatever the sensor sends.

### Camera 1 link frequency
<!-- key: card.bootconfig.4 -->

Same for the IMX585 on cam1. Each port carries its own rate.

#### (inline warning, shown only when it applies)
<!-- key: warn.bootconfig.1 -->

Anything above the default needs the RP1 overclock; without it the RP1 caps out near 43.8 fps at 4K whatever the sensor sends.

### Detected modes
<!-- key: card.bootconfig.5 -->

What `cinepi-raw --list-cameras` reports for the sensor that is actually attached right now — not what the selections above will produce after a reboot. Frame rates are the ceiling for each mode.

### I²C bus
<!-- key: card.bootconfig.6 -->

Needed by the quad rotary controller and the OLED status display.

### I²S bus
<!-- key: card.bootconfig.7 -->

Some audio HATs need this instead of USB.

### SPI bus
<!-- key: card.bootconfig.8 -->

For SPI accessories — displays, some sensors.

### Onboard audio codec
<!-- key: card.bootconfig.9 -->

The Pi's own audio output. Leave off if you're only ever using USB mic input.

### (help text not attached to a card)
<!-- key: help.bootconfig.0 -->

Writes these choices into the managed block of `config.txt` and reboots — about 25 seconds, camera included.

### (note box)
<!-- key: note.bootconfig.1 -->

Need something not covered here? SSH in and edit `config.txt` directly — Cinemate's block stays fenced between install markers, so hand edits outside it survive updates. [View the reconstructed file](#){data-open-config}
