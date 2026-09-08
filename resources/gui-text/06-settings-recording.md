# Recording
<!-- sidebar group `recording` · tab: settings.jsonc -->

Edit the headings and the paragraphs. Leave the `<!-- key: ... -->` lines alone —
they are what the GUI looks each string up by when CineMate starts.

---

## Audio
<!-- key: pane.audio -->

Input gain and timecode alignment, set separately for each bit depth.

### 24‑bit capture gain
<!-- key: card.audio_capture.24bit.capture_gain_db -->

Extra gain applied to the 24‑bit audio path, in dB.

### 24‑bit timecode offset
<!-- key: card.audio_capture.24bit.timecode_offset_frames -->

Frame‑count correction applied to the 24‑bit path's embedded timecode, to cancel out a known, fixed sync bias.

### 16‑bit capture gain
<!-- key: card.audio_capture.16bit.capture_gain_db -->

Extra gain applied to the 16‑bit audio path, in dB.

### 16‑bit timecode offset
<!-- key: card.audio_capture.16bit.timecode_offset_frames -->

Same correction as above, for the 16‑bit path.

---

## HDMI & preview
<!-- key: pane.hdmi -->

What's overlaid on the monitor, and how the two feeds are framed.

### Show audio VU meter
<!-- key: card.hdmi_display.overlays.buffer_vu_meter -->

Overlays live input levels on the HDMI monitor.

### VU meter clip hatching
<!-- key: card.hdmi_display.overlays.vu_meter_hatch_lines -->

Adds diagonal hatch lines to the top of the meter as a clipping warning.

### Monitor resolution
<!-- key: card.hdmi_display.width -->

Native resolution of the attached HDMI display — match your monitor for a pixel‑accurate overlay.

### Mirror to both HDMI ports
<!-- key: card.hdmi_display.mirror_to_both_ports -->

Single‑sensor rigs only — shows the one preview (with GUI) on both connectors. No effect with two sensors; the dual‑sensor compositor already owns both feeds.

### Monitor shows
<!-- key: card.hdmi_display.preview.default_hdmi_source -->

Which feed the HDMI output opens on at boot.

### Default zoom
<!-- key: card.hdmi_display.preview.default_zoom -->

Preview magnification at boot. 2.0 punches into the centre of frame for focus checking.

### Picture‑in‑picture
<!-- key: card.hdmi_display.preview.pip.corner -->

Size, corner and edge margin for the small inset feed when a monitor shows one camera full‑screen.
