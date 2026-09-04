# CineMate Log

CineMate Log log-compands the linear sensor signal down to a smaller DNG code depth on the way to disk, and writes a DNG `LinearizationTable` (tag `0xC618`) so any DNG-aware app decodes it back to linear automatically. It exists to shrink file size — a 16-bit ClearHDR frame drops ≈ 17–37 %, a 12-bit SDR frame ≈ 17 % — with no change to how the footage grades.

There is no "CineMate Log → Rec.709" LUT. CineMate Log is a storage format and not a viewing gamma like S-Log3 or V-Log. DNG `LinearizationTable` linearize automatically in DNG compatible NLEs (like DaVinci Resolve). 

If you are shooting in 16 bit formats, the log storage conversion will be 16 bit → 12 bit. If you are shooting in 12 bit with log storage active, files will be stored in 10 bit format. If you shoot in 10 bit formats, log is not used. You can also set the target bit depth explicitly, and for example shoot in 16 bit → 10 bit log storage conversion.

## Supported sensors

**IMX585 and IMX283 only.** Support is decided by the sensor's black level, not chosen: the two
shipped log DNG specs are built for BlackLevel 3200, which is what those two report and no other
sensor does.

| Sensor | Live mode | Target |
| --- | --- | --- |
| IMX585 | ClearHDR 16-bit | 12 (default) or 10 |
| IMX585 | 12-bit (SDR or 12-bit ClearHDR) | 10 only |
| IMX283 | 12-bit modes | 10 only |
| IMX283 | 10-bit modes | not supported |
| everything else | any | not supported |

!!! note "IMX477 is not a hardware limitation"
    Its 12-bit modes would compand the same way. What is missing is sensor-aware spec selection on
    the `cinepi-raw` side, which has not been built yet. Nothing about the sensor prevents it.

Full breakdown per mode: [Camera sensors › CineMate Log support](sensors.md#cinemate-log-support).

## Turning it on

### In `settings.jsonc`

```json
"sensors": {
  "cam0": {
    "log_encode": false
  }
}
```

`false` (default, off) · `true` (on, uses the live mode's default target) · `10` / `12` (on, forces that target explicitly).

Forcing a target only matters on a 16-bit ClearHDR source, where both `10` and `12` are valid — the default is `12` (16→12), and `10` trades a touch more compression for a smaller file (16→10). 

A 12-bit source has only one valid target, `10` — requesting `12` isn't an error, it just resolves to no log encoding, recording plain linear DNGs instead. The `LOG10` / `LOG12` badge on the Simple GUI shows what actually ran.

Example — force the smaller 16→10 target instead of the 16-bit default (16→12) on `cam0`:

```json
"sensors": {
  "cam0": {
    "log_encode": 10
  }
}
```

### Live, with `set log`

```text
set log        # toggle on/off, using the live mode's default target
set log 10     # force target 10 (e.g. 16to10 instead of ClearHDR's 16to12 default)
set log 12     # force target 12
set log off    # force off
```

Restarts the camera when idle, exactly like `set resolution`. If you run it mid-take, the request is stored and applied on the **next** restart — CineMate never splits a running recording. An explicit target that the live mode doesn't support (e.g. `set log 12` while in a 12-bit mode) is rejected and logged, never silently swapped for a different depth.