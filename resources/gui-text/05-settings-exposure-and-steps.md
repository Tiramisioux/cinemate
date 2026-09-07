# Exposure & steps
<!-- sidebar group `exposure-and-steps` · tab: settings.jsonc -->

Edit the headings and the paragraphs. Leave the `<!-- key: ... -->` lines alone —
they are what the GUI looks each string up by when CineMate starts.

---

## Value steps
<!-- key: pane.steps -->

The click‑stops each control cycles through, and — for the four with a pot channel assigned in Pots below — the free‑running range between the lowest and highest stop.

### ISO stops
<!-- key: card.arrays.iso.free -->

Values the ISO control steps through, in order. Free stepping lets an assigned pot sweep ISO continuously between the lowest and highest stop here instead of snapping to one — Increment sets how finely it quantizes while sweeping.

<!-- key: caption.arrays.iso.free · one per control, separated by ' · ' -->
*Free stepping · Increment*

### Shutter angle stops
<!-- key: card.arrays.shutter_a.free -->

Values the shutter angle control steps through, in degrees. Free stepping sweeps continuously between the lowest and highest stop here — Increment sets the degree step while sweeping.

<!-- key: caption.arrays.shutter_a.free · one per control, separated by ' · ' -->
*Free stepping · Increment*

### Frame‑rate stops
<!-- key: card.arrays.fps.free -->

Values the FPS control steps through. Free stepping sweeps continuously between the lowest and highest stop here — Increment sets the fps step while sweeping.

<!-- key: caption.arrays.fps.free · one per control, separated by ' · ' -->
*Free stepping · Increment*

### White balance stops
<!-- key: card.arrays.wb.free -->

Values the WB control steps through, in Kelvin. Free stepping (on by default) sweeps continuously between the lowest and highest stop here — Increment sets the Kelvin step while sweeping.

<!-- key: caption.arrays.wb.free · one per control, separated by ' · ' -->
*Free stepping · Increment*

### Anamorphic desqueeze stops
<!-- key: card.steps.4 -->

Preview desqueeze factors available on the anamorphic control. No pot or free stepping — this one's step‑only.

---

## Resolution & sensor
<!-- key: pane.resolution -->

Which resolutions and bit depths are offered, and the startup values for imx585 ClearHDR.

### Resolutions offered
<!-- key: card.resolution.0 -->

Which resolutions (in "K") the resolution control offers. Turning one off hides every mode at that size; a size this sensor has no mode for stays hidden either way. 5.5K is the imx283's 5568‑wide modes, off by default. Turning *every* switch off does not hide everything — it switches the filter off, so all modes are offered.

### Bit depths offered
<!-- key: card.resolution.1 -->

Which raw capture bit depths the resolution control offers. 16‑bit is imx585 ClearHDR only. As above, all off means the filter is off, not that nothing is offered.

### Dynamic resolution
<!-- key: card.image_capture.dynamic_resolution -->

When the requested frame rate is higher than the selected mode can sustain, drop to the largest mode of the same bit depth and HDR class that can. Resolution is the only thing it changes. Both GUIs show RES in green while a substitute is held. `set dynamic resolution` overrides this live, and that override outlives a reboot.

### Expose plain (SDR) modes
<!-- key: card.image_capture.hdr.sdr -->

Show the sensor's non‑HDR modes on the resolution control, alongside ClearHDR.

### Expose 12‑bit ClearHDR modes
<!-- key: card.image_capture.hdr.imx585_clear_hdr_12bit -->

Companded capture — cinepi‑raw applies the CCMP decompand.

### Expose 16‑bit ClearHDR modes
<!-- key: card.image_capture.hdr.imx585_clear_hdr_16bit -->

Delivered linear, with no compander in the path. Both off keeps the sensor SDR‑only.

### ClearHDR startup knobs
<!-- key: card.image_capture.hdr.threshold_low -->

Applied when a ClearHDR mode is selected. Adjust live afterwards with `set hdr …` or a pot/quad‑rotary channel. Leave a threshold blank to keep the sensor driver’s own pair (low 0, high 4095) — setting both to the same value flattens the image.

<!-- key: caption.image_capture.hdr.threshold_low · one per control, separated by ' · ' -->
*Threshold low · Threshold high · Blend · Gain adder*

### Sensor database
<!-- key: card.sensors.database_file -->

Source file describing every supported sensor's modes. Edit only if you're adding hardware support.

---

## Per-mode fps ceilings
<!-- key: pane.fpsceilings -->

These are what `cinepi-raw --list-cameras` reported on this board, not a fixed property of the sensor: the figure is clamped by the RP1 pixel rate, so enabling the RP1 overclock can raise it (imx585 4K 12-bit reads 43 stock, 50 overclocked), and it is rounded *down* to a whole frame — 43 can mean 43.98. It is also not a guarantee this storage/CPU can sustain it. Leave a field blank to keep using the detected value; fill one in only for a mode you've found a lower real-world ceiling for by trial. Raising above the detected value is allowed but logged as a warning — the sensor never reported it.

### (help text not attached to a card)
<!-- key: help.fpsceilings.0 -->

Loading detected modes…
