# CineMate Log

CineMate Log log-compands the linear sensor signal down to a smaller DNG code depth on the way to disk, and writes a DNG `LinearizationTable` (tag `0xC618`) so any DNG-aware app decodes it back to linear automatically. It exists to shrink file size — a 16-bit ClearHDR frame drops ≈ 17–37 %, a 12-bit SDR frame ≈ 17 % — with no change to how the footage grades.

## LUT: none. Use no LUT at all.

CineMate Log is **not** a viewing gamma like S-Log3 or V-Log. It is a storage format, and the DNG `LinearizationTable` undoes it **inside the raw decoder**, before the image reaches your node graph. By the time you see the clip it is already scene-linear, with BlackLevel and WhiteLevel intact.

So there is no "CineMate Log → Rec.709" LUT, and there should never be one. Applying a log-to-linear LUT or CST input gamma would decode the curve a second time.

| you want | do this |
|---|---|
| decode the log | nothing — the raw decoder already did it |
| input gamma, in a CST or RCM | **Linear** |
| a viewable image | lift exposure first, then a CST **Linear → Rec.709 Gamma 2.4** |
| settings for the log clip | whatever you'd set on a linear recording from the same camera, verbatim |

**Leave `UniqueCameraModel` as `cinepi`** (the default — see [Settings file → camera name](settings-json.md#camera-name)). Resolve picks its decode pipeline from that tag; an unknown model gets a generic decode with nothing layered on, which is exactly what a log-companded, already-linearised DNG needs. Spoofing it to a Blackmagic model unlocks a fuller Camera RAW tab but layers BMD colour science and their tone curve on top of your linear data — that confounds the curve, not helps it.

## Which sensors support it

Support is decided by the sensor's black level, not chosen — see [Camera sensors and frame rates → CineMate Log support](sensors.md#cinemate-log-support) for the full table. Short version:

| Sensor | Live mode | Target |
|--------|-----------|--------|
| IMX585 | ClearHDR 16-bit | 12 (default) or 10 |
| IMX585 | 12-bit (SDR or 12-bit ClearHDR) | 10 only |
| IMX283 | 12-bit modes | 10 only |
| everything else | any | not supported |

The flag is per-camera and launch-only; the sensor mode is live. Cinemate re-resolves the target every time `cinepi-raw` (re)starts for **any** reason — a resolution switch, a ClearHDR toggle, or a direct `set log` — against whatever bit depth is live at that moment, so the two never drift out of sync mid-session.

## Turning it on

### In `settings.jsonc`

```json
"camera": {
  "cam0": {
    "log_encode": false
  }
}
```

`false` (default, off) · `true` (on, uses the live mode's default target) · `10` / `12` (on, forces that target when the live mode supports it). See [Settings file → log_encode](settings-json.md#log_encode) for the full description. This is the boot-time value — once you run `set log` in a session, the live request takes over until the next reboot.

### Live, with `set log`

```text
set log        # toggle on/off, using the live mode's default target
set log 10     # force target 10 (e.g. 16to10 instead of ClearHDR's 16to12 default)
set log 12     # force target 12
set log off    # force off
```

Restarts the camera when idle, exactly like `set resolution`. If you run it mid-take, the request is stored and applied on the **next** restart — CineMate never splits a running recording. An explicit target that the live mode doesn't support (e.g. `set log 12` while in a 12-bit mode) is rejected and logged, never silently swapped for a different depth.

## The LOG badge

A grey `LOG10` / `LOG12` box appears in each camera's CAM section on the Simple GUI once that camera's `cinepi-raw` has actually launched with the flag. It reflects what's **running**, not what's requested — since the flag only takes effect on the next restart, the badge can lag a `set log` command by the length of that restart, on purpose. No badge means that camera is recording linear.

## Grading

The arithmetic is byte-identical to a reference Python encoder on real sensor pixels (both `16→10`/`16→12` and `12→10`), so a grading complaint should be diagnosed as a setup problem before a curve problem:

1. **Is your decoder applying the `LinearizationTable` at all?** If a log clip renders solid black, it isn't — a decoder that skips the table subtracts a linear-domain BlackLevel from data that never reaches it.
2. **BlackLevel / WhiteLevel** are tagged in the **linear (table-output) domain**, not the stored bit depth — 3200/65535 for a 16-bit source, 200/4095 for 12-bit. A decoder that assumes they match the stored depth will misread them.
3. **Exposure difference between clips you're comparing.** A log take and its linear reference shot minutes apart are different photons; match exposure and white balance before judging shape, and decode both **Using → Clip** so no project-wide setting favours one.
4. **The curve.** Last, and least likely — it's already gated byte-identical to the reference encoder.

Do not compare a log take and a linear take with a per-pixel diff tool — that's only valid between two files built from the *same* captured frame; shot noise alone will blow past any sane budget between two separate takes.
