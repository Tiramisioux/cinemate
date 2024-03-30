```cinemate development branch```

# CineMate – manual controls for cinepi-raw
CineMate scripts is a way for users to implement and customize manual controls for their [cinepi-raw](https://github.com/cinepi/cinepi-raw) build. 

Project aims at offering an easy way to build a custom camera. For basic operation and experimentation, only Raspberry Pi, camera board and monitor is needed. For practical use, buttons and switches can easily be added, allowing for a custom build.

A ready made disk image, with a Bullseye installation + cinepi-raw and CineMate scripts can be found in the release section of this repo.

Join the CinePi Discord [here](https://discord.gg/Hr4dfhuK).

## Hardware requirements
- Rasberry Pi 4B
- Official HQ or GS camera
- External HDMI monitor
- Samsung T5/T7 SSD or Samsung Extreme SSD 

## Getting started

### Installing 

Download the disk image from here: https://github.com/Tiramisioux/cinemate/releases/tag/dev

Burn to SD card (> 8 GB) using Raspberry Pi imager or Balena Etcher. 

CineMate should autostart on startup.

### Basic build

#### CineMate basic buttons

Attach push buttons to the Pi for basic camera operation.

|Function             |GPIO push button|
|---------------------|----|
|start/stop recording |5   |
|LED or rec light indicator |6, 21  |
|increase iso one step|27|
|decrease iso one step|15|
|change resolution |26 (single click)|
|reboot|26 (double click)|
|safe shutdown|26 (triple click)|

Be sure to use a resistor on pins 6 and 21 if you connect an LED!

|Camera setting|Default legal values (arrays)                      |
|--------------|---------------------------------------------------|
|iso           |100, 200, 400, 640, 800, 1200, 1600, 2500 and 3200.|
|shutter angle |1-360 in one degree increments + 172.8 and 346.6   |
|fps           |1-50 fps @ 2028x1080, 1-40 fps @ 2028 x 1520       |

GPIO pins, camera functions and arrays can be customized using the file `settings.json`, found in `cinemate/src` folder. See below.

TIP! Connect GPIO 13 to GPIO 03 using a jumper wire, and the safe shutdown button attached to GPIO 13 will also wake up the Pi, after being shutdown.

## Simple GUI

to be added

## Additional hardware

### Grove Base HAT
to be added
### Petroblock

to be added

### Pisugar


to be added

## CineMate CLI

Cinemate offers a set of Command-Line Interface (CLI) commands that allow users to control camera settings directly from the terminal. This guide will walk you through how to use these commands effectively, including the optional use of arguments to toggle controls.

### Connecting via SSH

For SSH:ing to the Pi, use the following credentials:

    User: pi
    Password: 1

#### Disabling CineMate autostart

CineMate autostarts by default. To disable autostart:

    cd cinemate
    make stop

To enable (and start) again

    cd cinemate
    make start

To run CineMate manually, anywhere in the cli, type

    cinemate


### Trying out camera functions

To start CineMate manually, type `cinemate` anywhere in the cli. This will show a startup sequence and the terminal will now accept the commands from the list below.

![CineMate startup sequence](docs/images/cinemate_cli.png)


For extensive logging and troubleshooting, start CineMate using the `cinemate -debug` command.

#### Basic Commands

Record/Stop (rec, stop): Start or stop recording. No arguments needed.

    > rec
    > stop

Set ISO (set_iso): Adjust the ISO setting. Requires an integer argument.

    > set_iso 800

Set Shutter Angle (set_shutter_a): Set the shutter angle. Requires a float argument for the angle.

    > set_shutter_a 172.8

Set FPS (set_fps): Configure the frames per second. Requires an integer argument.
    > set_fps 24

#### Example Commands

**Set Resolution:** Change the resolution setting.

    > set_resolution 1080
    > set_resolution

**Unmount:** Safely unmount the SSD. No arguments required.

    > unmount

**Display Time:** Show the current system time. No arguments needed.

    > time

**Set RTC Time:** Sync the Real-Time Clock with the system time. No arguments needed.

    > set_rtc_time

**Display SSD Space Left:** Check the remaining space on the SSD. No arguments required.

    > space

**Set PWM Mode:** Toggle or set the PWM mode directly.
    
    > set_pwm_mode
    > set_pwm_mode 1

Set Shutter Angle Sync (set_shutter_a_sync): Synchronize the shutter angle to the FPS. Toggle or set directly, using 0 or 1 as arguments.

    > set_shutter_a_sync
    > set_shutter_a_sync 0

**Lock/unlock iso, shutter angle , fps:** Toggle locks or set them directly.

    > set_iso_lock
    > set_shutter_a_nom_lock 1
    > set_fps_lock

**Double FPS (set_fps_double):** Enable or disable doubling the FPS rate.

    > set_fps_double
    > set_fps_double 1


#### How to Use Arguments
For commands that support or require arguments: Providing an argument directly sets the value.
Omitting the argument (for toggleable commands) will switch between on/off or cycle through available options.

## Cinemate commands
This table includes all the available commands (method calls) for the CineMate CLI and the default GPIO settings of `cinemate/src/settings.json`. 

- For hardware control, GPIOs can be used for buttons and switches. 

- With a Grove Base HAT, analog control of iso, shutter angle and fps via potentiometers are also available.

- Rotary encoders with buttons allow for combined actions, using two buttons.

- Commands are also possible to send to the Pi via USB serial.

| Camera function           | CineMate CLI/USB serial command | arguments                     | GPIO button         | GPIO rotary encoder       | GPIO switch |Grove Base HAT|
| ------------------------- | ------------------------------- | ----------------------------- | ------------------- | ------------------------- | ----------- | -----------|
| start/stop recording      | `rec`                           | None (toggle control)         | 5                 |                           |             |            |
| set iso                   | `set_iso`                       | integer                       |                     | clk 9, dt 11, bu 10       |             |A0          |
| iso increase              | `inc_iso`                       | \-                            | 17                  |                           |             |            |
| iso decrease              | `dec_iso`                       | \-                            | 14                  |                           |             |            |
| set shutter angle         | `set_shutter_a_nom`             | float                         |                     | clk 23, dt 25, bu 26      |             |A2          |
| shu increase 1 deg        | `inc_shutter_a_nom`             | \-                            |                     |                           |             |            |
| shu decrease 1 deg        | `dec_shutter_a_nom`             | \-                            |                     |                           |             |            |
| set fps                   | `set_fps`                       | integer                       |                     | clk 7, dt 8, bu 20        |             |A4          |
| fps increase 1 fps        | `inc_fps`                       | \-                            |                     |                           |             |            |
| fps decrease 1 fps        | `dec_fps`                       | \-                            |                     |                           |             |            |
| lock iso                  | `set_iso_lock`                  | 0, 1 or None (toggle control) |                     | 10 (single click)         |             |            |
| lock shutter angle        | `set_shutter_a_nom_lock`        | 0, 1 or None (toggle control) |                     | 13 (single click)         |             |            |
| lock fps                  | `set_fps_lock`                  | 0, 1 or None (toggle control) |                     | 20 (single click)         |             |            |
| lock all controls         | `set_all_lock`                  | 0, 1 or None (toggle control) |                     |                           |             |            |
| lock shutter angle + fps  | `set_shutter_a_nom_fps_lock`    | 0, 1 or None (toggle control) |                     |                           | 24          |            |
| sync shutter angle to fps | `set_shutter_a_sync`            | 0, 1 or None (toggle control) |                     | hold 13 + single click 26 | 16          |            |
| double fps                | `set_fps_double`                | 0, 1 or None (toggle control) | 12                  | hold 20 + single click 26 |             |            |
| pwm mode                  | `set_pwm_mode`                  | 0, 1 or None (toggle control) |                     | hold 10 + single click 26 | 22          |            |
| change resolution         | `set_resolution`                | 0, 1 or None (toggle control) | 26 (single click)   |                           |             |            |
| reboot                    | `reboot`                        | \-                            | 26 (double click)   |                           |             |            |
| safe shutdown             | `shutdown`                      | \-                            | 26 (triple click)   |                           |             |            |
| unmount drive             | `unmount`                       | \-                            | 26 (hold for 3 sec) |                           |             |            |

## Customizing camera functions and GPIO settings


The settings file can be found in `cinemate/src/settings.json`. Here the user can define their own buttons, switches, rotary encoders and combined actions, modifying the table above.

__Note that if you update this repo, your setting-file will be overwritten with the latest default CineMate settings file. If you are using a custom settings file, be sure to copy it to somewhere outside of the cinemate folder before updating.__


### General Settings
Define your hardware setup and desired application behavior:

    {
    "pwm_pin": 19,
    "rec_out_pin": [6, 21],
    "iso_steps": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],
    "additional_shutter_a_steps": [172.8, 346.6],
    "fps_steps": null
    }

### Analog Controls
Map physical controls to their functions in the application:

    "analog_controls": {
    "iso_pot": "A0",
    "shutter_a_pot": "A2",
    "fps_pot": "A4"
    }

### Buttons

Setup buttons with actions for different interactions:

    "buttons": [
    {
        "pin": 4,
        "pull_up": "False",
        "debounce_time": "0.1",
        "press_action": {"method": "rec"}
    }
    ]

Each button can be configured with a variety of actions based on different interactions:

**Press Action:** Triggers a specified method upon a simple press.

**Single, Double, and Triple Click Actions:** Specify methods to execute based on the number of successive clicks.

**Hold Action:** Executes a method when the button is held down for a longer duration.

Each action can specify a method that corresponds to a function within the application, and args, an array of arguments that the method requires.

Note that if you have both a Press Action and a Single-Click action on a pin, the pin will first execute the Press Action and when released, execute the Single-Click Action. Combining Press Action and Click actions on the same pin is therefore not recommended.

### Two-way switches
Two-way switches are configured in the two_way_switches section and have actions for both states:

**State On Action** and **State Off Action**: Define what actions to take when the switch is turned on or off, respectively. Similar to button actions, these can specify a method and args.

    "two_way_switches": [
    {
        "pin": 24,
        "state_on_action": {"method": "set_pwm_mode", "args": [true]},
        "state_off_action": {"method": "set_pwm_mode", "args": [false]}
    }
    ]

### Rotary Encoders
Configure rotary encoders for settings adjustments and optional button presses:

    "rotary_encoders": [
    {
        "clk_pin": 12,
        "dt_pin": 13,
        "button_pin": "None",
        "pull_up": "False",
        "debounce_time": "0.05",
        "encoder_actions": {
        "rotate_clockwise": {"method": "inc_iso"},
        "rotate_counterclockwise": {"method": "dec_iso"}
        }
    }
    ]

**Clockwise and Counterclockwise Actions**: Specify methods to execute when the encoder is rotated in either direction.

**Button Actions:** If the encoder has a push button, configure actions similar to standalone buttons, including press, click, and hold interactions.

### Combined Actions
Set up interactions involving multiple inputs:

    "combined_actions": [
    {
        "hold_button_pin": 5,
        "action_button_pin": 26,
        "action_type": "press",
        "action": {"method": "combine"}
    }
    ]

Combined actions allow for complex interactions involving multiple buttons or switches:

**Hold Button Pin** and **Action Button Pin:** Define the pins of the buttons involved in the combined action.
**Action Type:** Specifies the type of action required from the action_button_pin (e.g., press).
**Action:** Determines the method to execute when the combined action condition is met.

## Adding non-Samsung SSD drives

to be added

## Updating the Development Branch

    cd cinemate
    git pull origin development



