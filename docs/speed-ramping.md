# Speed ramping

Speed ramping is the process of changing the camera's frame rate during a shot so that playback speed varies once the footage is conformed to a constant frame rate in post production. Ramping up the frame rate produces slow motion while ramping down speeds up the action.

## Speed ramping in Cinemate

Cinemate exposes frame rate control through the `CinePiController` class. The simplest way to change speed on the fly is the CLI command:

```bash
set fps <value>
```

For quick 2× changes Cinemate also implements `set_fps_double` which toggles between the current FPS and twice that value. This can be used for designing a slow-motion button. Here is how you would to it in the settings file, button section:

```json
{
  "pin": 18,
  "pull_up": true,
  "debounce_time": 0.1,
  "press_action": {"method": "set_fps_double"}
}
```
>No argument is needed here. For methods such as `set_fps_double`, calling the method without an argument will simply toggle the control, in tis caseturning the slow motion on and off. If the user provides an argument, the control will be set explicitly to that value.

The controller contains an experimental `_ramp_fps` helper that gradually steps the frame rate up or down using `ramp_up_speed` and `ramp_down_speed` delays. This can be adapted if smoother transitions are desired.

## Shutter angle synchronisation

When frame rate changes the shutter angle can either remain fixed (preserving motion blur) or adjust to keep the exposure time constant. This behaviour is controlled by `shutter_a_sync_mode`.

Mode `0` keeps the **motion blur consistent** because the physical shutter angle does not change. As the FPS increases the exposure time gets shorter, resulting in a darker image. 

Mode `1` stores the current exposure time and recalculates the shutter angle whenever the FPS is adjusted so that **exposure time** stays the same.

Cinemate updates the nominal exposure time when the user sets a new angle. FPS is recalculated from the stored exposure time: