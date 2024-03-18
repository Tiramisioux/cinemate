```cinemate development branch```

## Hardware requirements
- Rasberry Pi 4B
- Official HQ or GS camera
- Samsung T5/T7 SSD

## Installing 

Download disk image from here: https://github.com/Tiramisioux/cinemate/releases/tag/dev

Burn to SD card using Raspberry Pi imager or Balena Etcher. CineMate should autostart

    User: pi
    Password: 1

## CineMate autostart

CineMate autostarts by default. To disable autostart:

    cd cinemate
    make stop

To enable (and start) again

    cd cinemate
    make start

To run CineMate manually, type

    cinemate

anywhere in the cli.

## Updating the Development Branch

    cd cinemate
    git pull origin development



## Method index for settings.json

This table includes all the methods defined within the `CinePiController` class, along with their arguments.

| Method Name/cinemate-cli command   | Arguments                      |Comment          |
|------------------------------|--------------------------------|-----------------|
| `rec`                        |                                |Start/stops recording
| `set_iso`                    |value 
| `set_shutter_a_nom`          |value
| `set_fps`                    |value
| `set_iso_lock`               |none (toggle), `0`, `1` |
| `set_shutter_a_nom_lock`     |none (toggle), `0`, `1`|
| `set_shutter_a_nom_fps_lock` |none (toggle), `0`, `1` |
| `set_fps_lock`               |none (toggle), `0`, `1` |
| `set_resolution`             |none (toggle), `0`, `1`|
| `inc_iso`                    |
| `dec_iso`                    | 
| `inc_shutter_a_nom`          | 
| `dec_shutter_a_nom`          | 
| `inc_fps`                    | 
| `dec_fps`                    | 
| `set_shutter_a_sync`         |none (toggle), `0`, `1`|
| `set_fps_double`             |none (toggle), `0`, `1`|ramps if in `pwm mode 1`
| `set_pwm_mode`               |none (toggle), `0`, `1`|requires soldering
| `unmount`                    |
| `safe_shutdown`              |


