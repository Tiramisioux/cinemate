# takes/ — the measurement data

147 DNGs, 1.4 GB. **Never commit this directory** (see `.gitignore` beside this file).
`innomaker585/` is currently untracked; if that ever changes, this is what would go in.

| Directory | Mode | Frames | Use |
|---|---|---|---|
| `ccmp-greycard/` | **all six**, ColorChecker Video, 5600 K studio | 82 | **the measurement set** — mode map in the handoff §1 |
| `ccmp-c0/` | 1928×1090 12-bit ClearHDR, **lens cap** | 14 | black level + read noise, binned |
| `ccmp-c0_UHD/` | 3856×2180 12-bit ClearHDR, **lens cap** | 13 | black level + read noise, full res |
| `ccmp-c0_UHD_normal_shutter/` | 3856×2180 12-bit ClearHDR | 12 | ⛔ **VOID** |
| `ccmp-c0_UHD_half_shutter_angle/` | 3856×2180 12-bit ClearHDR | 13 | ⛔ **VOID** |

`ccmp-greycard/system.log` is a cinemate log from a **later** session — it does not cover the
take window (cinemate wipes `*.log` on startup). It is kept only for the cinepi-raw launch
parameters, which the later session reproduced by cycling the same modes.

## The two void takes

A 1-stop shutter pair shot 43 s apart on a daylight window scene. The relation between them
is **not a function** — A-code spread within a narrow B bin was 10–114 codes against ~1 code
of measurement precision, with a 30-code left/right asymmetry. Scene drift, not sensor
behaviour.

**No fit on this pair is legitimate.** They are retained because the handoff cites their
numbers as evidence that the *method* failed, and because deleting them invites someone to
repeat the experiment. Handoff §4, first bullet.

## Conditions, grey-card set

Studio 5600 K, ISO 400, shutter 180° at 25 fps, aperture ≈ f/3.2. Calibrite ColorChecker
Video filling the frame, registration crosses at all four corners.

`AsShotNeutral` is **identical** (`0.625 1 0.5263`) across all six takes — verified — so white
balance cannot explain any colour difference between modes.
