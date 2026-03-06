## FPS correction factors and audio sync

Some sensors report different effective frame rates than the requested FPS. This is typically caused by sensor timing details such as vertical blanking (vblank). Vblank changes the total line time the sensor needs per frame, which in turn shifts the *true* FPS even when the target FPS stays constant. Cinemate compensates for this by applying an FPS correction factor so the captured frame timing lines up with your intended rate.

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

After the recording finishes, Cinemate compares the expected frame count with the actual frames captured. When there is a mismatch, it derives a suggested correction factor and suggests it to the user. If the frame count lands on the expected number of frames (with the tolerance of +/- 1 frame), it suggests to keep the existing correction factor.

!!! note ""
     See [here](cli-commands.md) how to run Cinemate manually.
