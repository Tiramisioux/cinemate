# Speed ramping

Speed ramping is the process of changing the camera's frame rate during a shot so that playback speed varies once the footage is conformed to a constant frame rate in post production. Ramping up the frame rate produces slow motion while ramping down speeds up the action.

## Speed ramping in Cinemate

Cinemate exposes frame rate control through the `CinePiController` class. The simplest way to change speed on the fly is the CLI command:

```bash
set fps <value>
```

For quick 2× changes Cinemate also implements `set_fps_double` which toggles between the current FPS and twice that value:

```python
    def set_fps_double(self, value=None):
        target_double_state = not self.fps_double if value is None else value in (1, True)
        if target_double_state:
            if not self.fps_double:
                self.fps_saved = self.fps
                target_fps = min(self.fps * 2, self.fps_max)
                self.set_fps(target_fps)
        else:
            if self.fps_double:
                self.set_fps(self.fps_saved)
        self.fps_double = target_double_state
```

The controller contains an experimental `_ramp_fps` helper that gradually steps the frame rate up or down using `ramp_up_speed` and `ramp_down_speed` delays. This can be adapted if smoother transitions are desired.

## Shutter angle synchronisation

When frame rate changes the shutter angle can either remain fixed (preserving motion blur) or adjust to keep the exposure time constant. This behaviour is controlled by `shutter_a_sync_mode`.

```python
        if self.shutter_a_sync_mode == 0:
            # keep motion-blur constant
            self.initialize_shutter_angle_steps()
            self.shutter_angle_actual = min(
                self.shutter_a_steps_dynamic,
                key=lambda x: abs(x - self.shutter_angle_actual))
        else:
            # keep exposure-time constant
            self.shutter_angle_actual = round(
                self.exposure_time_nominal * self.current_fps * 360, 1)
            self.shutter_angle_actual = min(360.0,
                                            max(1.0, self.shutter_angle_actual))
```

Mode `0` keeps the motion blur consistent because the physical shutter angle does not change. As the FPS increases the exposure time gets shorter, resulting in a darker image. Mode `1` stores the current exposure time and recalculates the shutter angle whenever the FPS is adjusted so that brightness stays the same.

Cinemate updates the nominal exposure time when the user sets a new angle:

```python
    if self.shutter_a_sync_mode == 1:
        self.exposure_time_nominal = (new_angle / 360) / self.current_fps
        self.shutter_angle_actual = new_angle
        self.is_shutter_angle_transient = True
        self.redis_controller.set_value(ParameterKey.SHUTTER_A_TRANSIENT.value, 1)
        threading.Timer(0.5, self.end_shutter_angle_transient).start()
```

When the transient period ends, the FPS is recalculated from the stored exposure time:

```python
    def end_shutter_angle_transient(self):
        self.is_shutter_angle_transient = False
        self.redis_controller.set_value(ParameterKey.SHUTTER_A_TRANSIENT.value, 0)
        if self.shutter_a_sync_mode == 1:
            adjusted_fps = (self.shutter_angle_nom / 360) / self.exposure_time_nominal
            self.update_fps(round(adjusted_fps, 1))
```