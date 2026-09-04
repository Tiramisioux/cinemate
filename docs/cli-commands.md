# Commands reference

By typing `cinemate` in the Raspberry Pi CLI we can start CineMate manually. This will stop any autostarted instance of CineMate, show the camera startup sequence and provide the CineMate "pseudo CLI" where can type commands for changing the camera controls and also to start and stop recording.

These commands can also be sent to the Pi as serial via the Tx/Rx pins or via USB. This can be useful for creating external controllers.

The same commands can be sent wirelessly over the camera's Wi-Fi hotspot — see the [Web API](web-api.md) and [Building control units](building-control-units.md).

!!! note ""

    Commands without an explicit argument toggle the current state when possible (e.g. `set fps lock` flips the lock; `set fps lock 1` forces it on).

!!! note ""

    All of the commands below can be mapped to GPIO buttons, rotary encoders and other input devices. See [this section](settings-json.md) for how to configure the settings file.


| Command                                    | Argument        | Example                                 |  Function                                      |
|--------------------------------------------|-------------------|-----------------------------------------|-------------------------------------------------|
| `rec` / `stop`                             | `[cam0\|cam1\|both] [s <seconds>\|f <frames>]` | `rec cam1 f 48`                           | Toggle recording or schedule an automatic stop after a timed duration or frame count; optional leading camera token forces which sensor(s) record on a dual rig |
| `set iso <value>`                          | int               | `set iso 800`                           | Set ISO to nearest allowed step                 |
| `inc iso` / `dec iso`                      | -              |                                | Step ISO up or down; `arrays.iso.free_increment` in free stepping |
| `set shutter a <angle>`                    | float             | `set shutter a 180`                     | Set actual shutter angle (snaps unless free/sync)|
| `inc shutter a` / `dec shutter a`          | -              |                          | Cycle through shutter angles; `arrays.shutter_a.free_increment` in free stepping |
| `set shutter a nom <angle>`                | float             | `set shutter a nom 180`                 | Set nominal shutter angle for motion blur       |
| `inc shutter a nom` / `dec shutter a nom`  | -              |                      | Step the nominal shutter angle                  |
| `set fps <value>`                          | float             | `set fps 24`                            | Change frame rate (snaps unless free)           |
| `inc fps` / `dec fps`                      | -              |                                | Step through FPS list; `arrays.fps.free_increment` in free stepping |
| `set hdr threshold low <n>`                | int               | `set hdr threshold low 500`             | ClearHDR HG→LG data-selection threshold, low side (0–4095), applied live ([ClearHDR](clear-hdr.md)) |
| `inc hdr threshold low` / `dec hdr threshold low` | -        |                                          | Step the low threshold; `arrays.hdr_threshold_low.free_increment` in free stepping |
| `set hdr threshold high <n>`               | int               | `set hdr threshold high 3000`           | ClearHDR HG→LG data-selection threshold, high side (0–4095), applied live |
| `inc hdr threshold high` / `dec hdr threshold high` | -       |                                          | Step the high threshold; `arrays.hdr_threshold_high.free_increment` in free stepping |
| `set hdr blend <n>`                        | int               | `set hdr blend 2`                       | ClearHDR blending mode 0–8, applied live        |
| `inc hdr blend` / `dec hdr blend`          | -              |                                          | Step blending mode; `arrays.hdr_blend.free_increment` in free stepping |
| `set hdr gain adder <n>`                   | int               | `set hdr gain adder 2`                  | ClearHDR low-gain gain adder 0–5 (2 = +12 dB), applied live |
| `inc hdr gain adder` / `dec hdr gain adder`| -              |                                          | Step gain adder; `arrays.hdr_gain_adder.free_increment` in free stepping |
| `set log [<10\|12\|off>]`                   | int, string or none | `set log` / `set log 10` / `set log off` | Toggle [CineMate Log](cinemate-log.md) on/off using the live mode's default target, or force `10`/`12` explicitly where the live mode supports it; restarts the camera when idle, deferred while recording |
| `set thumbnail <n>`                        | int               | `set thumbnail 1`                       | Embedded DNG thumbnail mode: `0` off, `1` mono, `2` colour, applied live (no camera restart), written per frame into new takes only. `thumbnail_size` (the plane's downscale) is not exposed here — its handler restarts the camera, unlike this one |
| `set wb [<Kelvin>]`                        | int or none       | `set wb 5600`                           | Set white balance or cycle active WB steps      |
| `inc wb` / `dec wb`                        | -              |                                 | Step white balance; `arrays.wb.free_increment` (100 K default) in free stepping |
| `set resolution [<mode>]`                  | int or none       | `set resolution 2`                      | Apply or cycle sensor mode                      |
| `set dynamic resolution [0/1]`             | 0/1 or none       | `set dynamic resolution 0`              | Enable/disable/toggle dynamic resolution substitution |
| `set anamorphic factor [<float>]`          | float or none     | `set anamorphic factor 1.33`            | Set or toggle anamorphic stretch                |
| `set zoom [<float>]`                       | float or none     | `set zoom 2`                            | Change digital zoom; omit to cycle              |
| `inc zoom` / `dec zoom`                    | -              |                              | Step preview zoom factor                        |
| `set preview [cam0\|cam1\|both\|pip_cam0\|pip_cam1]` | text or none      | `set preview pip_cam0`                  | Dual-sensor HDMI source: full-screen, side-by-side, or picture-in-picture (one sensor with the other as a corner inset); omit to cycle |
| `mount` / `unmount`                        | -              |                                  | Mount or unmount external storage               |
| `toggle mount`                             | -              |                           | Mount if not mounted, otherwise unmount         |
| `erase`                                    | -              | `erase`                                | Delete every clip on the mounted RAW volume without reformatting |
| `format`                                   | `[ext4\|exfat\|ntfs]` | `format exfat`                         | Reformat the RAW drive (defaults to exfat) and remount it |
| `storage preroll`                          | -              | `storage preroll`                       | Run the storage warm-up recording that prepares the media |
| `time`                                     | -              |                                   | Show system and RTC time                        |
| `set rtc time`                             | -              |                           | Copy system time to the RTC                     |
| `space`                                    | -              |                                  | Report remaining SSD space                      |
| `get`                                      | -              |                                    | Print all current settings (Redis keys in cp_controls channel)                      |
| `set shutter a sync [0/1]`                 | 0/1 or none       | `set shutter a sync 1`                  | Enable exposure sync mode; pots/encoders then step in `arrays.shutter_a.sync_increment` (0.1° default), independent of `free_increment` |
| `set iso lock [0/1]`                       | 0/1 or none       |                           | Lock or unlock ISO setting                      |
| `set shutter a nom lock [0/1]`             | 0/1 or none       | `set shutter a nom lock`                | Lock or unlock nominal shutter                  |
| `set shutter a nom fps lock [0/1]`         | 0/1 or none       | `set shutter a nom fps lock 1`          | Lock nominal shutter and FPS together           |
| `set fps lock [0/1]`                       | 0/1 or none       | `set fps lock 1`                        | Lock or unlock the frame rate                   |
| `set all lock [0/1]`                       | 0/1 or none       | `set all lock 0`                        | Toggle all exposure locks at once               |
| `set fps double [0/1]`                     | 0/1 or none       |                         | Instant or toggled 2× FPS mode                  |
| `reboot` / `shutdown`                      | -              |                                 | Safely reboot or halt the Pi                    |
| `restart camera`                           | -              |                          | Restart the libcamera pipeline                  |
| `restart cinemate`                         | -              |                       | Restart the CineMate process                    |
| `set iso free [0/1]`                       | 0/1 or none       | `set iso free 1`                        | Allow any ISO in 100-unit steps (100–3200), instead of presets |
| `set shutter a free [0/1]`                 | 0/1 or none       | `set shutter a free 0`                  | Allow any shutter angle in 1° steps (1–360°)    |
| `set fps free [0/1]`                       | 0/1 or none       | `set fps free 1`                        | Allow any FPS in 1 fps steps (1–`fps_max`)      |
| `set wb free [0/1]`                        | 0/1 or none       | `set wb free`                           | Use 100 K WB steps from 2800 K to 6500 K        |
| `set hdr threshold low free [0/1]`         | 0/1 or none       | `set hdr threshold low free 1`          | Use 16-unit steps across the full 0–4095 range  |
| `set hdr threshold high free [0/1]`        | 0/1 or none       | `set hdr threshold high free 1`         | Use 16-unit steps across the full 0–4095 range  |
| `set hdr blend free [0/1]`                 | 0/1 or none       | `set hdr blend free 1`                  | Use 1-unit steps across the full 0–8 range      |
| `set hdr gain adder free [0/1]`            | 0/1 or none       | `set hdr gain adder free 1`             | Use 1-unit steps across the full 0–5 range      |
| `set filter <0/1>`                         | 0/1               | `set filter 1`                          | Toggle IR-cut filter (IMX585)                   |

All step sizes above are the shipped defaults and are configurable per parameter via `arrays.<name>.free_increment` in [settings.jsonc](settings-json.md#arrays).

## Timed recording shortcuts

Use the timed modes to walk away from the camera while it captures a precisely bounded take.

- `rec s <seconds>` stops after the requested duration. Short forms such as `sec`, `secs` and `seconds` also work.
- `rec f <frames>` stops after the requested number of frame slots at the locked record-start FPS. Dropped frames still count toward that limit, so the take ends when that many frames should have been recorded, not when that many DNGs were successfully written. You can type `frame` or `frames` instead of `f`.

If recording is not already running, the CLI starts it before arming the timer. An invalid or zero value is ignored so you cannot accidentally stop a clip immediately.

On a dual-sensor rig you can prepend a camera token — `cam0`, `cam1`, or `both` (`dual` is an alias) — to force which sensor(s) capture the take, overriding the [record policy](dual-sensors.md#recording) for that one clip. It combines with the timed modes: `rec cam1`, `rec cam0 s 10`, `rec both f 48`. With a single sensor the token has no effect.

## Storage maintenance commands

`erase` and `format` prepare removable media directly from the CLI. Both require the RAW drive to be mounted; otherwise the CLI reports an error and leaves the media untouched.

- `erase` empties the mounted RAW volume without touching the filesystem structure, so you can clear cards quickly between takes.
- `format [ext4|exfat|ntfs]` reformats the drive with the chosen filesystem (`exfat` by default), remounts it and refreshes the free-space monitor.

## Storage pre-roll warm-up

`storage preroll` triggers the same warm-up clip that CineMate runs automatically on startup or when you mount new storage. During the pre-roll, CineMate temporarily drives the sensor at its maximum FPS, records a short burst, waits for buffers to flush and removes the test clip so the media is primed for the next real take. The manual command stays available even when `system.storage.auto_preroll` is set to `false` in `settings.jsonc`.

See [Storage pre-roll warm-up](storage-preroll.md) for a detailed walkthrough of the workflow and tips on when to run it manually.
