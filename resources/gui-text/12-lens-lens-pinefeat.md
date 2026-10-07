# Lens / Pinefeat
<!-- sidebar group `lens-pinefeat` · tab: lens -->

Edit the headings and the paragraphs. Leave the `<!-- key: ... -->` lines alone —
they are what the GUI looks each string up by when CineMate starts.

---

## Pinefeat CEF168 adapter
<!-- key: pane.lens.0 -->

Canon EF lens control: iris, focus and the lens list. Changes need a running camera.

---

## Lens
<!-- key: pane.lens.1 -->

The mounted lens and its saved entry. Nothing is saved until you save.

---

## Calibration
<!-- key: pane.lens.2 -->

Sweeps the focus motor to learn the lens's focus range. Refused while recording.

---

## Saved lenses
<!-- key: pane.lens.3 -->

Lenses kept in `resources/lenses.json`. Deleting one removes only its entry.

---

### Adapter
<!-- key: card.lens.status -->

Whether the adapter answered, and how it was found: *driver* or *raw I²C*.

### Lens control
<!-- key: card.lens.control -->

Lets CineMate drive iris and focus. Only available while the adapter is found.

### Mounted lens
<!-- key: card.lens.mounted -->

The lens id read from the adapter, and its state.

### Lens in use
<!-- key: card.lens.select -->

The saved entry for this lens. Switching discards unsaved changes.

### Name and save
<!-- key: card.lens.save -->

*Save as new* adds an entry. *Save over* replaces the selected one, after asking.

### Aperture range
<!-- key: card.lens.aperture -->

The lens's widest and narrowest f-number. Type them from the barrel; the adapter cannot read them.

### What this lens can do
<!-- key: card.lens.capabilities -->

What CineMate found this lens can do. A lens with no focus position is iris only. Autofocus is reserved.

### Calibrate
<!-- key: card.lens.calibrate -->

Runs a focus sweep. If nothing moves, set the lens to AF and retry.

### Last calibration
<!-- key: card.lens.last -->

The latest sweep's result. Save the lens to keep it.
