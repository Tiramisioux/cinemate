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
- Samsung T5/T7 SSD or Samsung Extreme SSD (more SSD types can be added manually by the user) 

## Getting started

### Installing 

Download the disk image from here: https://github.com/Tiramisioux/cinemate/releases/tag/dev

Burn to SD card using Raspberry Pi imager or Balena Etcher. CineMate should autostart

For SSH:ing to the Pi, use the following credentials:

    User: pi
    Password: 1

## Basic build

### Buttons

|Function|GPIO|
|--------|----|
|start/stop recording|4, 5|
|LED or rec light indicator (be sure to use a 320k resistor on this pin!|6, 21|
|change resolution (toggle between cropped and full frame)|13, 24|
|iso decrease|25|
|iso increase|23|
|unmount SSD (double click) / safe shutdown (triple click)|26|

GPIO settings and arrays for legal values can be customized in `main.py`.

TIP! Connect GPIO 26 to GPIO 03 using a jumper wire, and the safe shutdown button attached to GPIO 26 will also wake up the Pi, after being shutdown.

### Rotary encoders

### Grove Base HAT and analog controls




### Petroblock (power management)
### PiSugar (battery and power management)

## Custom build

### Connecting via SSH
### CineMate autostart

CineMate autostarts by default. To disable autostart:

    cd cinemate
    make stop

To enable (and start) again

    cd cinemate
    make start

To run CineMate manually, type

    cinemate

anywhere in the cli.

### CineMate CLI

Cinemate offers a set of Command-Line Interface (CLI) commands that allow users to control camera settings directly from the terminal. This guide will walk you through how to use these commands effectively, including the optional use of arguments to toggle controls.

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

#### Advanced Configuration Commands

Set Resolution (set_resolution): Change the resolution setting.

    > set_resolution 1080
    > set_resolution

Unmount (unmount): Safely unmount the SSD. No arguments required.

    > unmount

Display Time (time): Show the current system time. No arguments needed.

    > time

Set RTC Time (set_rtc_time): Sync the Real-Time Clock with the system time. No arguments needed.

    > set_rtc_time

Display SSD Space Left (space): Check the remaining space on the SSD. No arguments required.

    > space

##### Lock and Mode Commands

These commands allow toggling or setting specific modes and locks, enhancing control over the recording parameters.

Set PWM Mode (`set_pwm_mode`): Toggle or set the PWM mode directly.
    
    > set_pwm_mode
    > set_pwm_mode 1

Set Shutter Angle Sync (set_shutter_a_sync): Synchronize the shutter angle to the FPS.

    > set_shutter_a_sync
    > set_shutter_a_sync 0

Lock ISO (set_iso_lock), Shutter Angle (set_shutter_a_nom_lock), FPS (set_fps_lock): Toggle locks or set them directly.

> set_iso_lock
> set_shutter_a_nom_lock 1
> set_fps_lock

Double FPS (set_fps_double): Enable or disable doubling the FPS rate.

> set_fps_double
> set_fps_double 1


##### How to Use Arguments
For commands that support or require arguments:
Providing an argument directly sets the value.
Omitting the argument (for toggleable commands) will switch between on/off or cycle through available options.


#### Cinemate extended GPIO functions and method index for CineMate CLI and settings.json

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

### Customizing `settings.json`

#### General Settings
Define your hardware setup and desired application behavior:

    {
    "pwm_pin": 19,
    "rec_out_pin": [6, 21],
    "iso_steps": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],
    "additional_shutter_a_steps": [172.8, 346.6],
    "fps_steps": null
    }

#### Analog Controls
Map physical controls to their functions in the application:

    "analog_controls": {
    "iso_pot": "A0",
    "shutter_a_pot": "A2",
    "fps_pot": "A4"
    }

#### Buttons

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

**Press Action (press_action):** Triggers a specified method upon a simple press.

**Single, Double, and Triple Click Actions:** Specify methods to execute based on the number of successive clicks.

**Hold Action (hold_action):** Executes a method when the button is held down for a longer duration.

Each action can specify a method that corresponds to a function within the application, and args, an array of arguments that the method requires.

#### Two-way switches

Two-way switches are configured in the two_way_switches section and have actions for both states:

Pin (pin): The GPIO pin the switch is connected to.
State On Action (state_on_action) and State Off Action (state_off_action): Define what actions to take when the switch is turned on or off, respectively. Similar to button actions, these can specify a method and args.

    "two_way_switches": [
    {
        "pin": 24,
        "state_on_action": {"method": "set_pwm_mode", "args": [true]},
        "state_off_action": {"method": "set_pwm_mode", "args": [false]}
    }
    ]

#### Rotary Encoders
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


#### Combined Actions
Set up interactions involving multiple inputs:

    "combined_actions": [
    {
        "hold_button_pin": 5,
        "action_button_pin": 26,
        "action_type": "press",
        "action": {"method": "combine"}
    }
    ]


#### Pull-Up 
Pull-Up (pull_up): This setting dictates whether a pull-up resistor is used for a button or encoder pin. When pull_up is set to True, it indicates that the internal pull-up resistor of the microcontroller is enabled, pulling the pin to a high state by default. A press action then brings the pin to a low state. Conversely, setting pull_up to False implies an external pull-down resistor or a naturally low state until the button press makes it high. This configuration is crucial for ensuring accurate detection of press actions according to your hardware setup.

#### Debounce

When a mechanical switch or button is pressed or released, the physical contacts inside the switch do not make or break the connection cleanly. Instead, they tend to "bounce" against each other a few times before settling into a stable state. This bouncing effect can cause multiple unwanted rapid ON/OFF signals to be detected by the microcontroller or computer, even though the user intended only a single press or release action.

##### Role of debounce_time
The debounce_time parameter specifies the minimum amount of time (typically in seconds or milliseconds) that the software waits after detecting the first press or release signal before it accepts another one. This wait time allows the contacts to settle into their final state, thus ensuring that only a single action is registered for each press or release, regardless of any bouncing that may occur.

For example, if debounce_time is set to 0.1 (seconds), after the button is pressed, the system will ignore any further changes in the button's state for the next 0.1 seconds. This filtering ensures that only one press is detected and processed, even if the physical contacts bounce several times within that timeframe.

#### Button Actions


Introducing Two-Way Switches

Detailing Rotary Encoders
Rotary encoders can have both rotation actions and a button press action if they include a push button:

Clockwise and Counterclockwise Actions (rotate_clockwise, rotate_counterclockwise): Specify methods to execute when the encoder is rotated in either direction.
Button Actions (button_actions): If the encoder has a push button, configure actions similar to standalone buttons, including press, click, and hold interactions.
Understanding Combined Actions
Combined actions allow for complex interactions involving multiple buttons or switches:

Hold Button Pin (hold_button_pin) and Action Button Pin (action_button_pin): Define the pins of the buttons involved in the combined action.
Action Type (action_type): Specifies the type of action required from the action_button_pin (e.g., press).
Action (action): Determines the method to execute when the combined action condition is met.



### Adding non-Samsung SSD drives

### Updating the Development Branch

    cd cinemate
    git pull origin development
