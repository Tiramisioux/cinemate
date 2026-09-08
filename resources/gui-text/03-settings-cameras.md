# Cameras
<!-- sidebar group `cameras` · tab: settings.jsonc -->

Edit the headings and the paragraphs. Leave the `<!-- key: ... -->` lines alone —
they are what the GUI looks each string up by when CineMate starts.

---

## Camera 0
<!-- key: pane.cam0 -->

Sensor mounted on connector `cam0`. Geometry, HDMI routing, and the name it reports over USB.

### Rotate 180°
<!-- key: card.sensors.cam0.geometry.rotate_180 -->

For rigs where the sensor is mounted upside‑down.

### Flip horizontal
<!-- key: card.sensors.cam0.geometry.horizontal_flip -->

Mirrors the image left–right, e.g. for a periscope or mirror‑rig build.

### Flip vertical
<!-- key: card.sensors.cam0.geometry.vertical_flip -->

Mirrors the image top–bottom.

### HDMI output
<!-- key: card.sensors.cam0.output.hdmi_port -->

Which physical HDMI port shows this sensor's image on the monitor.

### Phase lock
<!-- key: card.sensors.cam0.phase_lock -->

Keeps the sensor's frame timing locked to the Pi's clock instead of free‑running — the fix for slow, cumulative frame‑rate drift.

### Report a different USB name
<!-- key: card.sensors.cam0.override_camera_name -->

Some NLEs and capture tools behave better when they see a known camera name over USB, instead of the raw sensor name.

### Reported name
<!-- key: card.sensors.cam0.camera_name -->

Only used while the override above is on.

### Custom tuning file
<!-- key: card.sensors.cam0.tuning_file_override.enabled -->

Overrides the auto‑detected colour tuning with a file from `resources/tuning_files/` — pick one already on the card, or upload a new one if yours isn't listed.

### CineMate Log
<!-- key: card.sensors.cam0.log_encode -->

Records log instead of linear. "On" uses this mode's own default target; force 10 or 12‑bit where the live bit depth supports it.

---

## Camera 1
<!-- key: pane.cam1 -->

Sensor mounted on connector `cam1` — same options, independent values.

### Rotate 180°
<!-- key: card.sensors.cam1.geometry.rotate_180 -->

For rigs where this sensor is mounted upside‑down.

### HDMI output
<!-- key: card.sensors.cam1.output.hdmi_port -->

Which physical HDMI port shows this sensor's image.

### Phase lock
<!-- key: card.sensors.cam1.phase_lock -->

Locks this sensor's frame timing to the Pi's clock to prevent slow frame‑rate drift.

### Custom tuning file
<!-- key: card.sensors.cam1.tuning_file_override.enabled -->

Same idea as cam0 — override with a file from `resources/tuning_files/` or upload a new one.

### CineMate Log
<!-- key: card.sensors.cam1.log_encode -->

Same idea as cam0 — records log instead of linear, target forced or auto per mode.

### Dual‑sensor record policy
<!-- key: card.sensors.record_policy -->

"Follow preview" records whatever's on screen — one camera full‑screen records alone. "Always both" ignores the preview and records both every take. A camera token on `rec` overrides either for one take.
