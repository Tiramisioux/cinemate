# Cinemate terminal commands

Cinemate doesn’t use a real shell parser. Instead, a background thread
reads simple text commands from SSH or the serial port and calls the
corresponding controller methods.

## Available Commands

| Command                                    | Input type        | Example                                 |  Function                                      |
|--------------------------------------------|-------------------|-----------------------------------------|-------------------------------------------------|
| `rec` / `stop`                             | none              | `rec`                                   | Toggle recording on or off                      |
| `set iso <value>`                          | int               | `set iso 800`                           | Set ISO to nearest allowed step                 |
| `inc iso` / `dec iso`                      | none              | `inc iso`                               | Step ISO up or down                             |
| `set shutter a <angle>`                    | float             | `set shutter a 180`                     | Set actual shutter angle (snaps unless free/sync)|
| `inc shutter a` / `dec shutter a`          | none              | `inc shutter a`                         | Cycle through shutter angles                    |
| `set shutter a nom <angle>`                | float             | `set shutter a nom 180`                 | Set nominal shutter angle for motion blur       |
| `inc shutter a nom` / `dec shutter a nom`  | none              | `inc shutter a nom`                     | Step the nominal shutter angle                  |
| `set fps <value>`                          | float             | `set fps 24`                            | Change frame rate (snaps unless free)           |
| `inc fps` / `dec fps`                      | none              | `inc fps`                               | Step through FPS list                           |
| `set wb [<Kelvin>]`                        | int or none       | `set wb 5600`                           | Set white balance or cycle presets              |
| `inc wb` / `dec wb`                        | none              | `inc wb`                                | Cycle white balance steps                       |
| `set resolution [<mode>]`                  | int or none       | `set resolution 2`                      | Apply or cycle sensor mode                      |
| `set anamorphic factor [<float>]`          | float or none     | `set anamorphic factor 1.33`            | Set or toggle anamorphic stretch                |
| `set zoom [<float>]`                       | float or none     | `set zoom 2`                            | Change digital zoom; omit to cycle              |
| `inc zoom` / `dec zoom`                    | none              | `inc zoom`                              | Step preview zoom factor                        |
| `mount` / `unmount`                        | none              | `mount`                                 | Mount or unmount external storage               |
| `toggle mount`                             | none              | `toggle mount`                          | Mount if not mounted, otherwise unmount         |
| `time`                                     | none              | `time`                                  | Show system and RTC time                        |
| `set rtc time`                             | none              | `set rtc time`                          | Copy system time to the RTC                     |
| `space`                                    | none              | `space`                                 | Report remaining SSD space                      |
| `get`                                      | none              | `get`                                   | Print all current settings                      |
| `set shutter a sync [0/1]`                 | 0/1 or none       | `set shutter a sync 1`                  | Enable exposure sync mode                       |
| `set iso lock [0/1]`                       | 0/1 or none       | `set iso lock`                          | Lock or unlock ISO setting                      |
| `set shutter a nom lock [0/1]`             | 0/1 or none       | `set shutter a nom lock`                | Lock or unlock nominal shutter                  |
| `set shutter a nom fps lock [0/1]`         | 0/1 or none       | `set shutter a nom fps lock 1`          | Lock nominal shutter and FPS together           |
| `set fps lock [0/1]`                       | 0/1 or none       | `set fps lock 1`                        | Lock or unlock the frame rate                   |
| `set all lock [0/1]`                       | 0/1 or none       | `set all lock 0`                        | Toggle all exposure locks at once               |
| `set fps double [0/1]`                     | 0/1 or none       | `set fps double`                        | Instant or toggled 2× FPS mode                  |
| `reboot` / `shutdown`                      | none              | `reboot`                                | Safely reboot or halt the Pi                    |
| `restart camera`                           | none              | `restart camera`                        | Restart the libcamera pipeline                  |
| `restart cinemate`                         | none              | `restart cinemate`                      | Restart the Cinemate process                    |
| `set iso free [0/1]`                       | 0/1 or none       | `set iso free 1`                        | Allow any ISO instead of presets                |
| `set shutter a free [0/1]`                 | 0/1 or none       | `set shutter a free 0`                  | Allow any shutter angle                         |
| `set fps free [0/1]`                       | 0/1 or none       | `set fps free 1`                        | Allow any FPS                                   |
| `set wb free [0/1]`                        | 0/1 or none       | `set wb free`                           | Allow any white balance                         |
| `set filter <0/1>`                         | 0/1               | `set filter 1`                          | Toggle IR-cut filter (IMX585)                   |

> Commands without an explicit argument will toggle the current state when
> possible (e.g. `set fps lock` flips the lock; `set fps lock 1` forces it on).

