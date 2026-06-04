## FPS correction factors and audio sync

Some sensors report different effective frame rates than the requested FPS. This is typically caused by sensor timing details such as vertical blanking (vblank). Vblank changes the total line time the sensor needs per frame, which in turn shifts the *true* FPS even when the target FPS stays constant. Cinemate compensates for this by applying an FPS correction factor so the captured frame timing lines up with your intended rate.

### IMX585, IMX294, IMX492 — correction factor is 1.0

The Cinemate libcamera fork (will127534/libcamera, `ea5abb8b`) includes a `getBlanking()` override for the IMX585, IMX294, and IMX492 sensors. Instead of accepting the ~one-line VMAX/HMAX quantisation error from the standard blanking calculation, the override searches the integer register-pair lattice against the sensor's reference clock to find the combination that delivers the exact requested period.

Effect: standard rates (24, 25, 30 fps, etc.) achieve sub-ppm accuracy on these sensors. The software correction factor for these rates is therefore `1.0` — no compensation is needed.

Sensors without this patch (IMX283, IMX477, IMX296, IMX519) retain their empirical correction factors as before.

With the properly fine-tuned correction factor we can achieve pretty good sync to both onboard and external audio recording

### Why the correction factor is per sensor, mode, and FPS

Each sensor model exposes its own timing characteristics. On top of that, every sensor mode (resolution/bit depth) has different blanking and pixel-clock constraints. The requested FPS also changes how the sensor clocks out frames. Because of these combined dependencies, Cinemate stores a correction factor for every **sensor type + resolution/mode + FPS** triplet in the file `src/module/sensor_correction_factors.py`.


### Running a fixed‑frame calibration clip

To validate or tune the correction factor, you can record a clip with a fixed frame count:

```
rec f 1000
```

This records exactly 1000 frames (based on the current FPS) and stops automatically. 
Cinemate knows exactly how many frames *should* have landed over the elapsed duration and when recording stops it performs an analysis and proposes an fps correction factor

### How Cinemate analyzes the results

After the recording finishes, Cinemate compares the expected frame count with the actual frames captured. When there is a mismatch, it derives a suggested correction factor and suggests it to the user. If the frame count lands on the expected number of frames (with the default final tolerance of +/- 1 frame), it suggests to keep the existing correction factor.

### Frame-count sync status

Cinemate stores the frame-count sync warning state in Redis as `frames_in_sync`. A value of `1` means the active or latest take is still within tolerance. A value of `0` means Cinemate has seen the take drift outside tolerance and the Simple GUI shows the magenta `SYNC` warning.

During recording, Cinemate compares the live accepted frame-slot count against the expected slot count from the FPS timeline. If the difference grows beyond the default live tolerance of +/- 2 frames, the magenta `SYNC` warning flashes immediately and then latches until the next take starts.

The final check waits until buffered frames have finished flushing to storage. While the RAM buffer is still draining after stop, Cinemate raises `is_writing_buf=1` and the Simple GUI stays green. The DNG count is checked only after that buffered write phase has gone idle, so frames that were still in RAM at stop time are included in the result. The default final analysis tolerance is stricter at +/- 1 frame.

The two tolerances are configurable in `settings.json` as `settings.live_sync_warning_tolerance_frames` and `settings.final_sync_analysis_tolerance_frames`.

For free-running takes, the expected-frame calculation follows FPS changes made during the take. This means speed ramps are counted from the FPS timeline rather than from only the FPS at the start of the take. For fixed-frame takes such as `rec f 100`, the requested frame count remains the expected target.

### Dropped frames vs sync mismatch

Dropped frames and frame-count sync are reported separately. A dropped-frame event means the clip has a hole at a known frame slot. That lights the purple `DROP` warning and increments `drop_frame_count`, but it does not by itself trigger the magenta `SYNC` warning. For sync analysis, those dropped-frame holes count as intentional timeline slots, because a later conform/export step can represent the hole explicitly.

The magenta `SYNC` warning is for a different problem: the live or final number of recorded frame slots does not match the expected take length after dropped-frame holes are accounted for.

### Storage pre-roll and startup guards

Storage pre-roll is excluded from sync analysis and warning state. The warm-up clip is deleted and should not latch `DROP`, `SYNC`, `frames_in_sync=0`, or an FPS correction suggestion.

Immediately after startup or storage pre-roll, cinepi-raw can briefly publish the last frame counter from the warm-up take. Cinemate ignores impossible early frame counts when arming `rec f <frames>`, so a fixed-frame recording starts counting from the new take instead of stopping on a stale pre-roll count.

!!! note ""
     See [here](cli-commands.md) how to run Cinemate manually.
