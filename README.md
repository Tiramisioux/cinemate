

## Overview
CineMate scripts is a way for users to implement and customize manual controls for their [cinepi-raw](https://github.com/cinepi/cinepi-raw) build. 

Project aims at offering an easy way to build a custom camera. For basic operation and experimentation, Raspberry Pi, camera board and monitor is needed. For practical use, buttons and switches can easily be added.

A ready made disk image can be found [here](https://github.com/Tiramisioux/cinemate/releases).

Join the CinePi Discord [here](https://discord.gg/Hr4dfhuK).

## Hardware requirements
- Rasberry Pi 5
- Official HQ or GS camera
- HDMI monitor or device (phone or tablet) 

_For recording, use a high speed NVME drive or [CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/) by Will Whang. Drive needs to be formatted as ext4 and named "RAW"._

_CineMate Pi 5 is also compatible with [OneInchEye](https://www.tindie.com/products/will123321/oneincheye/) (Sony IMX 283) and [StarlightEye](https://www.tindie.com/products/will123321/starlighteye/) (Sony IMX 585) by Will Whang._

## Quickstart guide

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


## Simple GUI

- Red color means camera is recording. 
- Green color means camera is writing buffered frames to disk. 
- Yellow color indicates low voltage warning.
- Numbers in lower left indicate frame count / frames in buffer. 

CineMate image automatically starts wifi hotspot `Cinepi`, password: `11111111`. Navigate browser to cinepi.local:5000 for simple web gui.

## CineMate CLI

This table includes all the available commands (method calls) + arguments for the CineMate CLI. GPIO column shows default settings of `cinemate/src/settings.json` and can be fully customized by the user. 

Commands are also possible to send to the Pi via USB serial.

| CineMate CLI | Camera function           | arguments                     | GPIO button         | GPIO rotary encoder       |
| ------------------------------- | ------------------------- | ----------------------------- | ------------------- | ------------------------- |
| `rec`                           | start/stop recording      | None                          | 4, 5                |                           |
| `set iso`                       | set iso                   | integer                       |                     |                           |
| `inc iso`                       | iso increase              | None                          | 27                  | clk 9, dt 11 (clockwise)  |
| `dec iso`                       | iso decrease              | None                          | 10                  | clk 9, dt 11 (counter-clockwise) |
| `set shutter a nom`             | set nominal shutter angle | float                         |                     |                           |
| `inc shutter a nom`             | nominal shutter angle increase | None                     |                     | clk 24, dt 25 (clockwise) |
| `dec shutter a nom`             | nominal shutter angle decrease | None                     |                     | clk 24, dt 25 (counter-clockwise) |
| `set fps`                       | set fps                   | float                         |                     |                           |
| `inc fps`                       | fps increase              | None                          |                     | clk 0, dt 8 (clockwise)   |
| `dec fps`                       | fps decrease              | None                          |                     | clk 0, dt 8 (counter-clockwise) |
| `set wb`                        | set white balance         | integer                       |                     |                           |
| `inc wb`                        | white balance increase    | None                          |                     | clk 16, dt 20 (clockwise) |
| `dec wb`                        | white balance decrease    | None                          |                     | clk 16, dt 20 (counter-clockwise) |
| `set fps double`                | double fps                | None                          | 1 (single click)    |                           |
| `set trigger mode`              | set trigger mode          | None                          | 1 (double click) |                   |
| `set resolution`                | change resolution         | integer or None (toggles res  | 13 (single click)   |                           |
| `restart camera`                | restart camera            | None                          | 13 (double click) |                   |
| `reboot`                        | reboot                    | None                          | 13 (triple click) |                   |
| `unmount`                       | unmount drive             | None                          | 13 (hold)           |                           |
| `set all lock`                  | lock all controls         | None                          | 22 (press)          |                           |
| `set shutter a sync mode`       | set shutter angle sync mode | None                        | 12 (single click)   |                           |


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

## CineMate autostart on boot

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


## Settings file

The settings file can be found in `cinemate/src/settings.json`. Here the user can define their own buttons, switches and rotary encoders.

#### GPIO output
Default rec LED pins are 6 and 21. Make sure to use a 220 Ohm resistor on this pin!

```
  "gpio_output": {
    "pwm_pin": 19,
    "rec_out_pin": [6, 21]
  },
```

#### Arrays

Set desired arrays for ISO, shutter angle values, fps and white balance.

```
  "arrays": {
    "iso_steps": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],
    "shutter_a_steps": [1, 45, 90, 135, 172.8, 180, 225, 270, 315, 346.6, 360],
    "fps_steps": [1, 2, 4, 8, 12, 16, 18, 24, 25, 33, 40, 50],
    "wb_steps": [3200, 4400, 5600]
  },
```

CineMate interpolates redis cg_rb settings used by libcamera based on the selected white balance value in the above array and the tuning file for the sensor being used.

#### Settings
```
  "settings": {
    "light_hz": [50, 60]
  }
```

CineMate dynamically adjusts the shutter_a_steps array on fps change, adding the flicker free angles given the current frame rate and the hz values defined by the user.

#### Analog Controls
Default settings are `None`. Map Grove Base HAT ADC channels to iso, shutter angle, fps and white balance controls. 

```
  "analog_controls": {
    "iso_pot": "A0",
    "shutter_a_pot": "A2",
    "fps_pot": "A4",
    "wb_pot": "A6"
  }
```

#### Buttons
Setup buttons with actions for different interactions. Methods are the same as the CineMate CLI commands. Arguments can also be added here

```
{
    "pin": 22,
    "pull_up": "False",
    "debounce_time": "0.1",
    "press_action": {"method": "set_all_lock"},
    "single_click_action": "None",
    "double_click_action": "None",
    "hold_action": {"method": "restart_camera"}
}
```

Each button can be configured with a variety of actions based on different interactions:

**Press Action:** Triggers a specified method upon a simple press.

**Single, Double, and Triple Click Actions:** Specify methods to execute based on the number of successive clicks.

**Hold Action:** Executes a method when the button is held down for a longer duration.

Each action can specify a method that corresponds to a function within the application, and args, an array of arguments that the method requires.

Note that if you have both a Press Action and a Single-Click action on a pin, the pin will first execute the Press Action and when released, execute the Single-Click Action. Combining Press Action and Click actions on the same pin is therefore not recommended.

#### Two-way switches
Two-way switches are configured in the two_way_switches section and have actions for both states:

**State On Action** and **State Off Action**: Define what actions to take when the switch is turned on or off, respectively. Similar to button actions, these can specify a method and args.

```
{
    "pin": 16,
    "state_on_action": {"method": "set_shutter_a_sync", "args": [false]},
    "state_off_action": {"method": "set_shutter_a_sync", "args": [true]}
}
```

#### Rotary Encoders
Configure rotary encoders for settings adjustments and optional button presses:

```
{
    "clk_pin": 9,
    "dt_pin": 11,
    "encoder_actions": {
    "rotate_clockwise": {"method": "inc_iso", "args": []},
    "rotate_counterclockwise": {"method": "dec_iso", "args": []}
}
```

**Clockwise and Counterclockwise Actions**: Specify methods to execute when the encoder is rotated in either direction.

Note that if rotary encoders with buttons are used, these are connected and defined as normal push buttons in the Button-section of the settings file.

#### Adafruit Neopixel Quad Rotary Encoder

```
{
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

These push buttons can be programmed to perform various functions like toggling locks, changing modes, or triggering specific actions, just like regular GPIO buttons. The `gpio_pin` setting clones the behaviour of pins defined in the Buttons section of the settings file.

For example, based on default settings above:
- The ISO encoder's push button clones GPIO 22 (toggle `set_all_lock`).
- The Shutter Angle encoder's push button clones GPIO 12 (toggle `set shutter a sync mode`).
- The FPS encoder's push button clones GPIO 1 (toggle `set fps double`).
- The White Balance encoder's push button GPIO 13 (toggle through resolution modes using `set resolution` without argument).

## Resolution modes  

| Sensor | Mode | Resolution   | Aspect Ratio | Bit Depth | Max FPS | File Size (MB) |
|--------|------|--------------|--------------|-----------|---------|----------------|
| IMX296 | 0    | 1456 x 1088  | 1.33         | 12        | 60      | 2              |
| IMX283 | 0    | 2736 x 1538  | 1.80         | 12        | 40      | 7.1            |
|        | 1    | 2736 x 1824  | 1.53         | 12        | 34      | 8.2            |
| IMX477 | 0    | 2028 x 1080  | 1.87         | 12        | 50      | 3.2            |
|        | 1    | 2028 x 1520  | 1.33         | 12        | 40      | 4.5            |
|        | 2    | 1332 x 990   | 1.34         | 10        | 120     | 2.8            |
| IMX519 | 0    | 1280 x 720   | 1.77         | 10        | 80      | 7.1            |
|        | 1    | 1920 x 1080  | 1.77         | 10        | 60      | 8.2            |
|        | 2    | 2328 x 1748  | 1.77         | 10        | 30      | 8.2            |
|        | 3    | 3840 x 2160  | 1.77         | 10        | 18      | 31             |
| IMX585 | 0    | 1928 x 1090  | 1.77         | 12        | 87      | 4              |
|        | 1    | 3856 x 2180  | 1.77         | 12        | 34      | 13             |
|        | 2    | 1928 x 1090  | 1.77         | 16        | 30      | 13             |

## Additional hardware

CineMate image file comes pre-installed with:
- [OneInchEye](https://www.tindie.com/products/will123321/oneincheye/)
- [StarlightEye](https://www.tindie.com/products/will123321/starlighteye/)
- [CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/)
- [Grove Base HAT](https://wiki.seeedstudio.com/Grove_Base_Hat_for_Raspberry_Pi/)
- Petroblock Powerblock
- Pisugar 

## PWM mode (experimental)
Trigger mode 2 sets the Raspberry Pi HQ/GS sensors in sink mode, as explained here: https://github.com/Tiramisioux/libcamera-imx477-speed-ramping

This makes it possible to feed the sensor XVS input with hardware PWM signal from the pi (CineMate uses pin 19 as default, but pin 18 also supports hardware PWM), allowing for hardware control of fps and shutter angle during recording, without restarting the camera. 

| :exclamation:  Note! Be sure to use a voltage divider so PWM signal is converted to 1.65V.   |
|-----------------------------------------|

This function is an experiment inspired by my old Nizo 8mm camera which has a button for doubling the motor speed, achieving in-camera speed ramping. 

From my tests I have noticed that changing fps works fine, but sometimes camera has to be reset a couple of times to work properly (toggling the PWM mode button). Changing shutter angle in PWM mode (or having shutter angle sync engaged) also doesn't seem to work properly.

## Backing up the SD card

To make a compressed image backup of the SD card onto the SSD:

```
echo "Start time: $(date)"; sudo dd if=/dev/mmcblk0 bs=1M status=progress | xz -9 -c > /media/RAW/cinepi-sdk-002_cinemate-pi5_bookworm_image_$(date +%Y-%m-%d_%H-%M-%S).img.xz; echo "End time: $(date)"
```

Backing up an 8 GB CineMate image takes about 2 hours.

## Known issues

- Frame drops when using NTFS formatted SSD drives
- Recording stops after a couple of seconds when using ext4 formatted SSD drives
- 16 bit mode on StarlightEye not working properly

## Todo

- [ ] optimize reciording to allow for the use of 300 MB/s SSD drive
- [ ] optimize operating system for faster boot and smaller image file
- [ ] change rec light logic to be based on framecount from redis
- [ ] fix shutter angle values array calculation
- [ ] fix web gui for proper display of framcount and frame buffer
- [ ] implement control of StarlightEye mechanical filter
- [ ] make RPi4 compatible image file for cinepi-V2 + cinemate

