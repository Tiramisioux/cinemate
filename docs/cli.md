# CineMate CLI

CineMate offers a set of Command-Line Interface (CLI) commands that allow users to control camera settings directly from the terminal.

## Disabling CineMate Autostart

To stop the autostarted instance:

    cd cinemate
    make stop

To enable (and start) again:

    cd cinemate
    make start

To disable autostart:

    cd cinemate
    make uninstall

To enable autostart:

    cd cinemate
    make install

## Running CineMate Manually

Anywhere in the CLI, type:

    cinemate

This will show a startup sequence. The terminal will now accept the commands from the list below.

![CineMate startup sequence](./images/cinemate_cli.png)

*Example startup sequence, showing the output from CineMate's modules*

For extensive logging and troubleshooting, CineMate can be started using the `cinemate -debug` command.

## Example CLI Commands

Start/stop recording:

    > rec

Adjust the ISO setting. Requires an integer argument.

    > set_iso 800

Set the shutter angle. Requires a float argument for the angle.

    > set_shutter_a 172.8

Configure the frames per second. Requires an integer argument.

    > set_fps 24

Lock/unlock ISO, shutter angle, or FPS: Toggle locks or set them directly. Providing an argument directly sets the value. Omitting the argument will toggle the control.

    > set_iso_lock
    > set_shutter_a_nom_lock 1
    > set_fps_lock

Enable or disable doubling the FPS rate:

    > set_fps_double
    > set_fps_double 1

## Command Index

This table includes all the available commands (method calls) + arguments for the CineMate CLI and the GPIO default settings of `cinemate/src/settings.json`.

Commands are also possible to send to the Pi via USB serial.

| Camera function           | CineMate CLI/USB serial command | arguments                     | GPIO button         | GPIO rotary encoder       | GPIO switch |Grove Base HAT|USB keyboard|
| ------------------------- | ------------------------------- | ----------------------------- | ------------------- | ------------------------- | ----------- |-----------| -----------|
| start/stop recording      | `rec`                           | None (toggle control)         | 4, 5                   |                           |             |           | `0`           |
| set iso                   | `set_iso`                       | integer                       |                     | clk 9, dt 11, bu 10       |             |A0          |
| iso increase              | `inc_iso`                       | \\-                            | 17                  |                           |             |            | `1`           |
| iso decrease              | `dec_iso`                       | \\-                            | 14                  |                           |             |            |`2`            |
| set shutter angle         | `set_shutter_a_nom`             | float                         |                     | clk 23, dt 25, bu 13      |             |A2          |
| shu increase 1 deg        | `inc_shutter_a_nom`             | \\-                            |                     |                           |             |            |`3`            |
| shu decrease 1 deg        | `dec_shutter_a_nom`             | \\-                            |                     |                           |             |            |`4`         |
| set fps                   | `set_fps`                       | integer                       |                     | clk 7, dt 8, bu 20        |             |A4          |
| fps increase 1 fps        | `inc_fps`                       | \\-                            |                     |                           |             |            |`5`            |
| fps decrease 1 fps        | `dec_fps`                       | \\-                            |                     |                           |             |            |`6`            |
| lock iso                  | `set_iso_lock`                  | 0, 1 or None (toggle control) |                     | 10 (single click)         |             |            |            |
| lock shutter angle        | `set_shutter_a_nom_lock`        | 0, 1 or None (toggle control) |                     | 13 (single click)         |             |            |            |
| lock fps                  | `set_fps_lock`                  | 0, 1 or None (toggle control) |                     | 20 (single click)         |             |            |            |
| lock all controls         | `set_all_lock`                  | 0, 1 or None (toggle control) |                     |                           |             |            |            |
| lock shutter angle + fps  | `set_shutter_a_nom_fps_lock`    | 0, 1 or None (toggle control) |                     |                           | 24          |            |            |
| sync shutter angle to fps | `set_shutter_a_sync`            | 0, 1 or None (toggle control) |                     | hold 13 + single click 26 | 16          |            |            |
| double fps                | `set_fps_double`                | 0, 1 or None (toggle control) | 12                  | hold 20 + single click 26 |             |            |            |
| pwm mode                  | `set_pwm_mode`                  | 0, 1 or None (toggle control) |                     | hold 10 + single click 26 | 22          |            |            |
| change resolution         | `set_resolution`                | 0, 1 or None (toggle control) | 26 (single click)   |                           |             |            |`8`            |
| reboot                    | `reboot`                        | \\-                            | 26 (double click)   |                           |             |            |            |
| safe shutdown             | `shutdown`                      | \\-                            | 26 (triple click)   |                           |             |            |            |
| unmount drive             | `unmount`                       | \\-                            | 26 (hold for 3 sec) |                           |             |            |`9`            |

## Default ISO, Shutter Angle, and FPS Arrays

|Setting|Values                     |
|--------------|---------------------------------------------------|
|iso           |100, 200, 400, 640, 800, 1200, 1600, 2500, 3200.|
|shutter angle |1-360 in one degree increments + 172.8 and 346.6   |
|fps           |1-50 fps @ 2028x1080, 1-40 fps @ 2028x1520         |

The arrays can be customized using the settings file (see below).
