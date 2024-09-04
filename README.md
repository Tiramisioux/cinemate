

# Overview
CineMate scripts is a way for users to implement and customize manual controls for their [cinepi-raw](https://github.com/cinepi/cinepi-raw) build. 

Project aims at offering an easy way to build a custom camera. For basic operation and experimentation, Raspberry Pi, camera board and monitor is needed. For practical use, buttons and switches can easily be added, allowing for a custom build.

A ready made disk image can be found in the release section of this repo.

Join the CinePi Discord [here](https://discord.gg/Hr4dfhuK).

# Hardware requirements
- Rasberry Pi 5
- Official HQ or GS camera
- HDMI monitor or device (phone or tablet) 

_For recording, use a high speed NVME drive or CFE card module with CFE card module by Will Whang. SSD needs to be formatted as NTFS and named "RAW"._

_CineMate Pi 5 is also compatible with OneInchEye (Sony IMX 283) and StarlightEye (Sony IMX 585) by Will Whang._

# Quickstart guide

1) Burn image to ssd card

2) Connect RPi 5 and camera sensor board

| :exclamation:  When connecting the camera module to the Pi, make sure it is the Pi is not powered. It is not advised to hot-swap the camera cable.   |
|-----------------------------------------|

3) Connect to Pi with SSH:

```
user: pi
password: 1
```

4) Start cinemate by typing "cinemate" anywhere in the cli

5) To adjust installation for different sensors:

```
sudo nano /boot/firmware/config.txt
```

Cinemate is compatible with Raspberry Pi HQ camera, Global Shutter camera, OneInchEye and StarlightEye

To view on phone or other device, connect the phone to wifi Cinepi, password 11111111. In phones browser, navigate to cinepi.local:5000

For starting/stopping recording from phone, tap the preview screen

Burn to SD card (> 8 GB) using Raspberry Pi imager or Balena Etcher. 

| :exclamation:  When connecting an LED to the GPIOs, be sure to use a resistor   |
|-----------------------------------------|

|:point_up:  Connect GPIO 26 to GPIO 03 using a jumper wire, and the system button attached to GPIO 26 will also wake up the Pi, after being shutdown.   |
|-----------------------------------------|

# CineMate CLI

This table includes all the available commands (method calls) + arguments for the CineMate CLI. GPIO column shows default settings of `cinemate/src/settings.json` and can be fully customized by the user. 

Commands are also possible to send to the Pi via USB serial.

| CineMate CLI | Camera function           | arguments                     | GPIO button         | GPIO rotary encoder       |
| ------------------------------- | ------------------------- | ----------------------------- | ------------------- | ------------------------- |
| `rec`                           | start/stop recording      | None                          | 4, 5                |                           |
| `set iso`                       | set iso                   | integer                       |                     | clk 9, dt 11              |
| `inc iso`                       | iso increase              | None                          | 27                  | clk 9, dt 11 (clockwise)  |
| `dec iso`                       | iso decrease              | None                          | 10                  | clk 9, dt 11 (counter-clockwise) |
| `set shutter a nom`             | set nominal shutter angle | float                         |                     | clk 24, dt 25             |
| `inc shutter a nom`             | nominal shutter angle increase | None                     |                     | clk 24, dt 25 (clockwise) |
| `dec shutter a nom`             | nominal shutter angle decrease | None                     |                     | clk 24, dt 25 (counter-clockwise) |
| `set fps`                       | set fps                   | float                         |                     | clk 0, dt 8               |
| `inc fps`                       | fps increase              | None                          |                     | clk 0, dt 8 (clockwise)   |
| `dec fps`                       | fps decrease              | None                          |                     | clk 0, dt 8 (counter-clockwise) |
| `set wb`                        | set white balance         | integer                       |                     | clk 16, dt 20             |
| `inc wb`                        | white balance increase    | None                          |                     | clk 16, dt 20 (clockwise) |
| `dec wb`                        | white balance decrease    | None                          |                     | clk 16, dt 20 (counter-clockwise) |
| `set resolution`                | change resolution         | None                          | 13 (single click)   |                           |
| `unmount`                       | unmount drive             | None                          | 13 (hold)           |                           |
| `set all lock`                  | lock all controls         | None                          | 22 (press)          |                           |
| `set fps double`                | double fps                | None                          | 1 (single click)    |                           |
| `set trigger mode`              | set trigger mode          | None                          | 12 (hold), 1 (double click) |                   |
| `set shutter a sync mode`       | set shutter angle sync mode | None                        | 12 (single click)   |                           |
| `reboot`                        | reboot                    | None                          | 1 (hold), 13 (triple click) |                   |
| `restart camera`                | restart camera            | None                          | 22 (hold), 13 (double click) |                   |

## Example CLI commands

Start/stop recording:

    > rec

Adjust the ISO setting. Requires an integer argument.

    > set iso 800

Set the shutter angle. Requires a float argument for the angle.

    > set shutter a 172.8

Configure the frames per second. Requires an integer argument.

    > set fps 24

Lock/unlock iso, shutter angle or fps: Toggle locks or set them directly. Providing an argument directly sets the value. Omitting the argument will toggle the control.

    > set iso_lock

    > set shutter a nom lock 1

    > set fps lock

Enable or disable doubling the FPS rate. 

    > set fps_double
    
    > set fps_double 1

# CineMate autostart on boot

To enable autostart:

    cd cinemate
    make install

To stop the autostarted instance:

    cd cinemate
    make stop

To enable (and start) again:

    cd cinemate
    make start

To disable autostart:

    cd cinemate
    make uninstall


# Settings file

The settings file can be found in `cinemate/src/settings.json`. Here the user can define their own buttons, switches, rotary encoders and combined actions, modifying the table above.

### GPIO output
Default rec LED pin is 21. Make sure to use a 220 Ohm resistor on this pin!

    {
    "pwm_pin": 19,
    "rec_out_pin": [6, 21],
    "iso_steps": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],
    "additional_shutter_a_steps": [172.8, 346.6],
    "fps_steps": null
    }

### Arrays

Set desired arrays for ISO, shutter angle values, fps and white balance.

```
  "arrays": {
    "iso_steps": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],
    "shutter_a_steps": [1, 45, 90, 135, 172.8, 180, 225, 270, 315, 346.6, 360],
    "fps_steps": [1, 2, 4, 8, 12, 16, 18, 24, 25, 33, 40, 50],
    "wb_steps": [3200, 4400, 5600]
  },
```

### Analog Controls
Default settings are `None`. Map Grove Base HAT ADC channels to iso, shutter angle and fps controls. 

```
  "analog_controls": {
    "iso_pot": "A0",
    "shutter_a_pot": "A2",
    "fps_pot": "A4",
    "wb_pot": "A6"
  },
````


### Buttons
Setup buttons with actions for different interactions. Methods are the same as the CineMate CLI commands. Arguments can also be added here

    "buttons": [
    {
        "pin": 5,
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
        "pin": 16,
        "state_on_action": {"method": "set_shutter_a_sync", "args": [false]},
        "state_off_action": {"method": "set_shutter_a_sync", "args": [true]}
      },
    }
    ]

### Rotary Encoders
Configure rotary encoders for settings adjustments and optional button presses:

```
  "rotary_encoders": [
    {
      "clk_pin": 9,
      "dt_pin": 11,
      "encoder_actions": {
        "rotate_clockwise": {"method": "inc_iso", "args": []},
        "rotate_counterclockwise": {"method": "dec_iso", "args": []}
      }
    },
```

**Clockwise and Counterclockwise Actions**: Specify methods to execute when the encoder is rotated in either direction.

Note that if rotary encoders with buttons are used, these are connected and defined as normal push buttons in the Button-section of the settings file.

### Adafruit Neopixel Quad Rotary Encoder

```
  "quad_rotary_encoders": {
    "0": {"setting_name": "iso", "gpio_pin": 22},
    "1": {"setting_name": "shutter_a", "gpio_pin": 12},
    "2": {"setting_name": "fps", "gpio_pin": 1},
    "3": {"setting_name": "wb", "gpio_pin": 13}
  }
```

- Encoder 0 (ISO): Push button on GPIO 22
- Encoder 1 (Shutter Angle): Push button on GPIO 12
- Encoder 2 (FPS): Push button on GPIO 1
- Encoder 3 (White Balance): Push button on GPIO 13

These push buttons can be programmed to perform various functions like toggling locks, changing modes, or triggering specific actions, just like regular GPIO buttons.

For example, based on default setting settings:
- The ISO encoder's push button (GPIO 22) is set to lock all controls when pressed.
- The Shutter Angle encoder's push button (GPIO 12) is set to toggle the shutter angle sync mode on a single click.
- The FPS encoder's push button (GPIO 1) is set to toggle FPS doubling on a single click.
- The White Balance encoder's push button (GPIO 13) is set to change resolution on a single click.

By using the Quad Rotary Encoder, you can have a compact, intuitive interface for adjusting camera settings while still maintaining the flexibility of programmable push button actions.

# Additional hardware

## Grove Base HAT
to be added

## Petroblock
to be added

## Pisugar
to be added

## PWM mode (experimental)
PWM mode sets the Raspberry Pi HQ/GS sensors in sink mode, as explained here: https://github.com/Tiramisioux/libcamera-imx477-speed-ramping

This makes it possible to feed the sensor XVS input with hardware PWM signal from the pi (CineMate uses pin 19 as default, but pin 18 also supports hardware PWM), allowing for hardware control of fps and shutter angle during recording, without restarting the camera. 

| :exclamation:  Note! Be sure to use a voltage divider so PWM signal is converted to 1.65V.   |
|-----------------------------------------|

This function is an experiment inspired by my old Nizo 8mm camera which has a button for doubling the motor speed, achieving in-camera speed ramping. 

From my tests I have noticed that changing fps works fine, but sometimes camera has to be reset a couple of times to work properly (toggling the PWM mode button). Changing shutter angle in PWM mode (or having shutter angle sync engaged) also doesn't seem to work properly.

# Backing up the SD card

To make a compressed image backup of the SD card onto the SSD:

    sudo dd if=/dev/mmcblk0 bs=1M status=progress | xz -c > /media/RAW/cinepi_cinemate_raspbian_image_$(date +%Y-%m-%d_%H-%M-%S).img.xz

Backing up an 8 GB CineMate image takes about 2 hours.