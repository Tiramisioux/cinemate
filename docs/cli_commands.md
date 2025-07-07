### 7.3 CineMate “Pseudo-CLI”

CineMate doesn’t use a real command-line parser or shell. Instead, it implements a “pseudo-CLI” inside the running Python process to let you type or send simple, human-readable commands over and SSH session and USB/serial Here’s how it works:
 

#### Available Commands

| Command                | Argument(s)           | What it does                                          |
|--------------------------------|-----------------------|-------------------------------------------------------|
| `rec` / `stop`                 | _none_                | Toggle recording on/off                               |
| `set iso <100–3200>`           | `int`                 | Set ISO (clamps to nearest valid step)               |
| `inc iso` / `dec iso`          | _none_                | Step ISO up/down                                      |
| `set shutter a <float>`        | `float`               | Set shutter angle (snaps unless in free/sync mode)   |
| `inc shutter a` / `dec shutter a` | _none_             | Step shutter angle through dynamic list              |
| `set shutter a nom <float>`    | `float`               | Set nominal shutter (motion-blur target)             |
| `inc shutter a nom` / `dec shutter a nom` | _none_     | Step nominal shutter angle                           |
| `set fps <float>`              | `float`               | Set frames-per-second (snaps or free)                 |
| `inc fps` / `dec fps`          | _none_                | Step FPS up/down                                      |
| `set wb [<Kelvin>]`            | `int` or _none_       | Set or cycle white balance                           |
| `inc wb` / `dec wb`            | _none_                | Cycle WB up/down                                      |
| `set resolution [<mode>]`      | `int` or _none_       | Apply or cycle sensor-mode (restarts pipeline)        |
| `set anamorphic factor [<float>]` | `float` or _none_ | Set/toggle anamorphic squeeze factor                  |
| `mount` / `unmount`            | _none_                | Mount/unmount removable storage                       |
| `time`                         | _none_                | Print system + RTC time                               |
| `set rtc time`                 | _none_                | Sync RTC from system clock                            |
| `space`                        | _none_                | Log remaining SSD free space                          |
| `get`                          | _none_                | Pretty-print all current settings                     |
| `set … lock`                   | `0`/`1` or _none_     | Toggle or force-set locks on ISO / shutter / FPS      |
| `set fps double [0/1]`         | `0`/`1` or _none_     | Enable/disable instant or ramped 2× FPS mode          |
| `set … free`                   | `0`/`1` or _none_     | Unlock / re-lock “free” ranges for ISO/shutter/FPS/WB |
| `set filter <0/1>`             | `0`/`1`                | Toggle IR-cut filter (IMX585 only)                    |
| `reboot` / `shutdown`          | _none_                | Safe OS reboot or halt (stops recording first)        |
| `restart`                      | _none_                | Soft-restart only the libcamera pipeline               |

> **Note:** Commands without an explicit argument will **toggle** state when meaningful (e.g. `set fps lock` flips the lock; `set fps lock 1` forces it on).

#### Examples

```text
# Start recording
> rec

# Lock ISO so it cannot change
> set iso lock

# Double the frame rate instantly
> set fps double 1

# Set shutter angle to 172.8° (snaps to nearest valid)
> set shutter a 172.8

# Cycle white balance to the next step in your wb_steps array
> set wb

# Print all current settings (ISO, FPS, shutter, etc.)
> get
