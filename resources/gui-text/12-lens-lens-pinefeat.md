# Lens / Pinefeat
<!-- sidebar group `lens-pinefeat` · tab: lens -->

Edit the headings and the paragraphs. Leave the `<!-- key: ... -->` lines alone —
they are what the GUI looks each string up by when CineMate starts.

---

## Pinefeat CEF168 adapter
<!-- key: pane.lens.0 -->

Canon EF lens control through the Pinefeat adapter: iris, focus position and the lens list. This page reads the adapter live and works without a camera running, but changes need one.

---

## Lens
<!-- key: pane.lens.1 -->

Which lens is mounted, which saved entry describes it, and what that entry says about it. Nothing here is written to the saved list until you save.

---

## Calibration
<!-- key: pane.lens.2 -->

Sweeps the focus motor from end to end so CineMate learns the lens's focus range. It moves the focus ring, so it is refused while recording.

---

## Saved lenses
<!-- key: pane.lens.3 -->

Every lens CineMate has been told about, kept in `resources/lenses.json`. Deleting one removes only its entry.

---

### Adapter
<!-- key: card.lens.status -->

Whether the adapter board answered, where it was found, and how. *Driver* means the cef168 kernel driver is bound; *raw I²C* means CineMate read the board directly on the camera's bus.

### Lens control
<!-- key: card.lens.control -->

Lets CineMate drive the iris and focus. It can only be switched on while the adapter is found. Off leaves the adapter alone and greys the lens controls on the shooting screens.

### Mounted lens
<!-- key: card.lens.mounted -->

The Canon lens id the adapter reads from the mounted lens, and the state CineMate has for it.

### Lens in use
<!-- key: card.lens.select -->

Picks the saved entry that describes the mounted lens. *Unknown lens* means no saved entry is selected. Choosing another entry discards unsaved changes to the current one.

### Name and save
<!-- key: card.lens.save -->

*Save as new* adds the current lens under this name. *Save over* replaces the selected saved entry, keeping its place in the list, and asks first. Calibrations and aperture edits only reach the list when you save.

### Aperture range
<!-- key: card.lens.aperture -->

The widest and narrowest f-number of this lens. The adapter cannot read them, so type them from the lens barrel. The iris steps and the iris picker stay inside this range.

### What this lens can do
<!-- key: card.lens.capabilities -->

What CineMate has found this lens to do. *Untested* means not tried yet. A lens that never reports a focus position is treated as iris only. Autofocus is reserved and not available.

### Calibrate
<!-- key: card.lens.calibrate -->

Runs a focus sweep. If it does not move the lens, check the lens's AF/MF switch and try again. Give the minimum focus distance in metres only if the lens does not report one.

### Last calibration
<!-- key: card.lens.last -->

What the most recent sweep found. It is not saved until you save the lens.
