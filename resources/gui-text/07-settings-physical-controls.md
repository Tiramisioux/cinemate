# Physical controls
<!-- sidebar group `physical-controls` · tab: settings.jsonc -->

Edit the headings and the paragraphs. Leave the `<!-- key: ... -->` lines alone —
they are what the GUI looks each string up by when CineMate starts.

---

## GPIO in
<!-- key: pane.controls -->

What's wired to each GPIO pin, translated from the raw action list into plain gestures. Every button, switch and rotary encoder in `hardware_controls` shows here — add as many as you're wired for.

### (note box)
<!-- key: note.controls.0 -->

Move a control to a different pin or encoder from the dropdown — occupied ones are greyed out and it asks before remapping. Pick the command from the list (grouped like `cli_commands.py`, legal arguments only) or hit the pencil to type it by hand. The box after the command is its argument: leave it on **Cycle through the list** and the control steps through the values in [Value steps](#steps){data-nav}, or pick one value to jump straight to it. Commands marked **Needs a value** do nothing useful until you choose one.

---

## Grove HAT potentiometers
<!-- key: pane.pots -->

Which Grove Base HAT channel drives each parameter. ISO/shutter/FPS/WB's free‑mode range and increment live with their step list in Value steps above; ClearHDR's stay here since those knobs aren't array settings.

### ISO
<!-- key: card.pots.0 -->

No effect until a channel is picked — free stepping and increment are set in Value steps above.

### Shutter angle
<!-- key: card.pots.1 -->

Same idea — free stepping and increment are set in Value steps above.

### Frame rate
<!-- key: card.pots.2 -->

Same idea — free stepping and increment are set in Value steps above.

### White balance
<!-- key: card.pots.3 -->

Same idea — free stepping and increment are set in Value steps above.

### ClearHDR threshold low
<!-- key: card.image_capture.hdr.threshold_low_free -->

Grove Base HAT channel for a physical knob on this value (range 0–4095). Free stepping sweeps continuously across that range instead of jumping by the increment below.

<!-- key: caption.image_capture.hdr.threshold_low_free · one per control, separated by ' · ' -->
*Free stepping · Increment*

### ClearHDR threshold high
<!-- key: card.image_capture.hdr.threshold_high_free -->

Same idea (range 0–4095).

<!-- key: caption.image_capture.hdr.threshold_high_free · one per control, separated by ' · ' -->
*Free stepping · Increment*

### ClearHDR blend
<!-- key: card.image_capture.hdr.blend_free -->

Same idea (range 0–8).

<!-- key: caption.image_capture.hdr.blend_free · one per control, separated by ' · ' -->
*Free stepping · Increment*

### ClearHDR gain adder
<!-- key: card.image_capture.hdr.gain_adder_free -->

Same idea (range 0–5).

<!-- key: caption.image_capture.hdr.gain_adder_free · one per control, separated by ' · ' -->
*Free stepping · Increment*

---

## Quad rotary encoder
<!-- key: pane.quadrotary -->

Adafruit's four-encoder i²c board. Its rows address the board's own encoders, not GPIO pins.

---

## GPIO out
<!-- key: pane.gpio -->

Physical signals the camera drives while recording — tally lamps, a slate tone, a relay. Add as many tally or tone pins as you're wired for.

### Mute the tone on a dropped frame
<!-- key: card.hardware_outputs.rec_tone.relay_drop_frames -->

When the camera drops a frame, cut the slate tone for about one frame, then resume. The gap is audible on the recorded scratch track, so a dropped frame is findable by ear in the edit.

---

## OLED status display
<!-- key: pane.oled -->

The small i²c screen some rigs mount near the handle.

### Enabled
<!-- key: card.output_peripherals.oled.enabled -->

No OLED detected on this build — leave off unless one is wired to the i²c bus.

### Rows shown
<!-- key: card.oled.1 -->

Which live values are printed on the screen, top to bottom.

### Font size
<!-- key: card.output_peripherals.oled.font_size -->

Text size on a 128×64 panel — larger reads from further away but fits fewer rows.
