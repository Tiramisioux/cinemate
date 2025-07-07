## Overview
CineMate scripts is a way for users to implement and customize manual controls for their [cinepi-raw](https://github.com/cinepi/cinepi-raw) build. 

Project aims at offering an easy way to build a custom camera. For basic operation and experimentation, Raspberry Pi, camera board and monitor is needed. For practical use, buttons and switches can easily be added.

A ready made disk image can be found [here](https://github.com/Tiramisioux/cinemate/releases).

Join the CinePi Discord [here](https://discord.gg/Hr4dfhuK).

## Hardware requirements
- Rasberry Pi 4/5 or CM4 module
- Official HQ or GS camera
- HDMI monitor or device (phone or tablet) for monitoring

_For recording, use a high speed NVME drive or [CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/) by Will Whang. Drive needs to be formatted as ext4 and named "RAW"._

_CineMate is also compatible with [OneInchEye](https://www.tindie.com/products/will123321/oneincheye/) (Sony IMX 283) and [StarlightEye](https://www.tindie.com/products/will123321/starlighteye/) (Sony IMX 585) by Will Whang. Works with CM4 module and Pi 5B._

## Quickstart guide

1) Burn image to ssd card. 16 GB or larger.

2) Connect Pi and camera sensor board

| :exclamation:  When connecting the camera module to the Pi, make sure it is the Pi is not powered. It is not advised to hot-swap the camera cable.   |
|-----------------------------------------|

3) Boot up the Pi. CineMate should autostart.


### Connecting to Pi with SSH:

```
user: pi
password: 1
```

### Starting CineMate manually

CineMate autostarts by default. 

To stop an autostarted CineMate instance:

```
systemctl stop cinemate-autostart
```

For enabling and disabling autostart [see this section](https://github.com/Tiramisioux/cinemate/blob/dev-pi5/README.md#cinemate-autostart-on-boot).

For running CineMate manually from the cli type `cinemate`. This will also display extensive logging which can be useful when configuring and testing buttons and switches.




### Adjusting config.txt for different sensors:

```
sudo nano /boot/firmware/config.txt
```

Uncomment the section for the sensor being used, and make sure to comment out the others. Reboot the Pi for changes to take effect.

CineMate is compatible with Raspberry Pi HQ camera (imx477), Global Shutter camera (imx296), OneInchEye (imx283), StarlightEye (imx585) and Arducam imx519.

### External monitoring

To view on phone or other device, connect the phone to: 

Wifi `CinePi` 
password `11111111`.

In web browser, navigate to `cinepi.local:5000`. A clean feed (without GUI) is available at `cinepi.local:8000/stream`.

### Recording

External drive should be formatted as ntfs or ext4 and be labeled "RAW". 
  
For starting/stopping recording: 
- in web browser: tap (or click) the preview screen
- from CLI (running CineMate manually): type `rec`
- via GPIO: attach a momentary switch (or simply short circuit) to GPIO 04 or 05 (can be changed in `home/pi/cinemate/src/settings.json`)

A rec LED light can be connected to GPIO 21.

| :exclamation:  When connecting an LED to the GPIOs, be sure to use a resistor   |
|-----------------------------------------|

Note that cinemate v3 is based on cinepi-sdk-002 so it also has [this issue](https://discord.com/channels/1070517330083315802/1070835904169648128/1269459402491166750)⁠, affecting write speed to drive. CFE Hat works great but fps in most cases is max 50 at the moment.

## Simple GUI

Simple GUI is available via browser and/or attached HDMI monitor.

- Red color means camera is recording.
- Purple color means camera detected a drop frame 
- Green color means camera is writing buffered frames to disk. 
- Yellow color indicates low voltage warning.
- Numbers in lower left indicate frame count / frames in buffer. 

CineMate image automatically starts wifi hotspot `Cinepi`, password: `11111111`. Navigate browser to cinepi.local:5000 for simple web gui.

## CineMate CLI commands

When manually running CineMate from the CLI you can type simple commands. The table below includes all the available commands (method calls) + arguments for the CineMate CLI. GPIO column shows default settings of `cinemate/src/settings.json` and can be fully customized by the user. CineMate also listens for commands sent to the Pi via USB serial.

| cinemate cli/usb serial command               | comment                                                                                                                                                                                                                                     | arguments                     | GPIO button             | GPIO rotary encoder   | GPIO switch   | GPIO output   |
|----------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------|------------------------|----------------------|--------------|--------------|
| `rec`                                         | start and stop recording                                                                                                                                                                                                                   | None (toggle control)         | 5                       |                      |              |              |
| `set iso`                                     | set iso to a value (chooses the closest value in the array defined in settings.json)                                                                                                                                                        | integer                       |                         |                      |              |              |
| `inc iso`                                     | increase iso value one step in the array                                                                                                                                                                                                   | -                             | 13                      | clk 9, dt 11, bu 10  |              |              |
| `dec iso`                                     | decrease iso value one step in the array                                                                                                                                                                                                   | -                             | 10                      | clk 9, dt 11, bu 10  |              |              |
| `set shutter a nom`                           | set the nominal shutter angle to a value (chooses the closest value in the array defined in settings.json)                                                                                                                                  | float                         |                         |                      |              |              |
| `inc shutter a nom`                           | increase shutter angle value                                                                                                                                                                                                               | -                             |                         | clk 15, dt 18, bu 23  |              |              |
| `dec shutter a nom`                           | decrease shutter angle value                                                                                                                                                                                                               | -                             |                         | clk 15, dt 18, bu 23  |              |              |
| `set fps`                                     | set fps to a value (chooses the closest value in the array defined in settings.json)                                                                                                                                                        | integer                       |                         |                      |              |              |
| `inc fps`                                     | increase fps value                                                                                                                                                                                                                         | -                             |                         | clk 25, dt 8, bu 7    |              |              |
| `dec fps`                                     | decrease fps value                                                                                                                                                                                                                         | -                             |                         | clk 25, dt 8, bu 7    |              |              |
| `set wb`                                      | set white balance to a value (chooses the closest value in the array defined in settings.json)                                                                                                                                              | integer                       |                         |                      |              |              |
| `inc wb`                                      | increase white balance                                                                                                                                                                                                                     | -                             |                         | clk 12, dt 20, bu 21  |              |              |
| `dec wb`                                      | decrease white balance                                                                                                                                                                                                                     | -                             |                         | clk 25, dt 8, bu 7    |              |              |
| `set resolution`                              | select the next available resolution option                                                                                                                                                                                               | 0, 1 or None (toggle control) | 13, 26 (single click)   |                      |              |              |
| `set anamorphic factor`                       | set or toggle the anamorphic factor (explicit value or toggle through anamorphic_steps)                                                                                                                                                     | float or None (toggle control)|                         |                      |              |              |
| `reboot`                                      | reboot the pi                                                                                                                                                                                                                             | -                             | 26 (double click)   |                      |              |              |
| `shutdown`                                    | shutdown the pi                                                                                                                                                                                                                           | -                             | 26 (triple click)   |                      |              |              |
| `unmount`                                     | unmount CFE card/SSD                                                                                                                                                                                                                      | -                             | 26 (hold for 3 sec) |                      |              |              |


### Example CLI commands

Start/stop recording:

    > rec

Adjust the ISO setting. Requires an integer argument.

    > set iso 800

Set the shutter angle. Requires a float argument for the angle.

    > set shutter a 172.8

Configure the frames per second. Requires an integer argument.

    > set fps 24

Lock/unlock iso, shutter angle or fps: Toggle locks or set them directly. Providing an argument directly sets the value. Omitting the argument will toggle the control.

    > set iso lock

    > set shutter a nom lock 1

    > set fps lock

Enable or disable doubling the FPS rate. 

    > set fps_double
    
    > set fps_double 1

## CineMate autostart on boot

Go to cinemate folder:

    cd cinemate

To enable autostart:

    make install
    make enable

To stop the autostarted instance:

    make stop

To start again:

    make start

To disable autostart:

    make disable


## Settings file

### Geometry and Output Configuration
CineMate supports multiple cameras with per‑port customization in your `settings.json`. Two key sections control this behavior:

```json
{
  "geometry": {
    "cam0": {
      "rotate_180": false,
      "horizontal_flip": false,
      "vertical_flip": true
    },
    "cam1": {
      "rotate_180": true,
      "horizontal_flip": false,
      "vertical_flip": false
    }
  },
  "output": {
    "cam0": { "hdmi_port": 1 },
    "cam1": { "hdmi_port": 0 }
  }
}
```

- **geometry.cam0/cam1**: Defines image orientation for each physical camera port:
  - `rotate_180`: flip image upside‑down when `true`.
  - `horizontal_flip`: mirror image left‑to‑right when `true`.
  - `vertical_flip`: mirror image top‑to‑bottom when `true`.

- **output.cam0/cam1**: Maps each camera to an HDMI output port. By default, `cam0`→HDMI 0 and `cam1`→HDMI 1, but you can remap as needed.

Continue with your existing settings configuration below.

The settings file can be found in `/home/pi/cinemate/src/settings.json`. Here the user can define their own buttons, switches and rotary encoders.



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

#### Anamorphic preview
```
    "anamorphic_preview": {
      "anamorphic_steps": [1, 1.33, 2.0],
      "default_anamorphic_factor": 1
    }
```

The anamorphic_preview section allows users to define an array of selectable anamorphic factors (anamorphic_steps) and set a default value (default_anamorphic_factor). The anamorphic factor is used to adjust the aspect ratio of the preview.


#### Analog Controls
Default settings are `None`. Map Grove Base HAT ADC channels to iso, shutter angle, fps and white balance controls. 

```
  "analog_controls": {
    "iso_pot": 0,
    "shutter_a_pot": 2,
    "fps_pot": 4,
    "wb_pot": 6
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
  "quad_rotary_encoders": {
    "0": {"setting_name": "iso", "gpio_pin": 5},
    "1": {"setting_name": "shutter_a", "gpio_pin": 16},
    "2": {"setting_name": "fps", "gpio_pin": 26},
    "3": {"setting_name": "wb", "gpio_pin": 5}
  }
```

##### Defaults encoder push buttons settings

- Encoder 0 (ISO): Encoder push button clones behaviour of rec button on GPIO 5
- Encoder 1 (Shutter Angle): Encoder push button clones behaviour of fps double button in GPIO 16
- Encoder 2 (FPS): Encoder push button clones behaviour of system push button on GPIO 26
- Encoder 3 (White Balance): Encoder push button clones behaviour of rec button on GPIO 5

These push buttons can be programmed to perform various functions like toggling locks, changing modes, or triggering specific actions, just like regular GPIO buttons. The `gpio_pin` setting clones the behaviour of pins defined in the Buttons section of the settings file.

## Compatible sensors 

| Sensor | Cinemate sensor mode | Resolution   | Aspect Ratio | Bit Depth | Max FPS* | File Size (MB) |
|--------|------|--------------|--------------|-----------|---------|----------------|
| IMX283 | 0    | 2736 x 1538  | 1.80         | 12        | 40      | 7.1            |
|        | 1    | 2736 x 1824  | 1.53         | 12        | 34      | 8.2            |
| IMX296 | 0    | 1456 x 1088  | 1.33         | 12        | 60      | 2              |
| IMX477 | 0    | 2028 x 1080  | 1.87         | 12        | 50      | 3.2            |
|        | 1    | 2028 x 1520  | 1.33         | 12        | 40      | 4.5            |
|        | 2    | 1332 x 990   | 1.34         | 10        | 120     | 2.8            |
| IMX519 | 0    | 1280 x 720   | 1.77         | 10        | 80      | 7.1            |
|        | 1    | 1920 x 1080  | 1.77         | 10        | 60      | 8.2            |
|        | 2    | 2328 x 1748  | 1.77         | 10        | 30      | 8.2            |
|        | 3    | 3840 x 2160  | 1.77         | 10        | 18      | 31             |
| IMX585 | 0    | 1928 x 1090  | 1.77         | 12        | 87      | 4              |


'*' Note that maximum fps will vary according to disk write speed. For the specific fps values for your setup, make test recordings and monitor the output. Purple background in the monitor/web browser indicates drop frames. You can cap CineMates max fps values for your specific build by editing the file `cinemate/src/module/sensor_detect.py`

## Multi camera support

CineMate automatically detects each camera connected to the Raspberry Pi and spawns a separate `cinepi-raw` process per sensor. By default:

- **Primary camera** (first detected) displays its preview on HDMI port 0.
- **Secondary cameras** run with `--nopreview` and map to subsequent HDMI outputs (cam1→HDMI 1, cam2→HDMI 2, etc.).
- Preview windows are centered and sized according to your `geometry` settings.

You can override default HDMI mappings in `settings.json` under the `output` section:

## Additional hardware

CineMate image file comes pre-installed with:
- [OneInchEye](https://www.tindie.com/products/will123321/oneincheye/)
- [StarlightEye](https://www.tindie.com/products/will123321/starlighteye/)
- [CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/)
- [Grove Base HAT](https://wiki.seeedstudio.com/Grove_Base_Hat_for_Raspberry_Pi/)

## PWM mode (experimental)
Trigger mode 2 sets the Raspberry Pi HQ/GS sensors in sink mode, as explained here: https://github.com/Tiramisioux/libcamera-imx477-speed-ramping

This makes it possible to feed the sensor XVS input with hardware PWM signal from the pi (CineMate uses pin 19 as default, but pin 18 also supports hardware PWM), allowing for hardware control of fps and shutter angle during recording. By using a precise clock source this could potentially fix the fluctuating fps of image sensors, allowing for precise audio syncing.

| :exclamation:  Note! Be sure to use a voltage divider so PWM signal is converted to 1.65V.   |
|-----------------------------------------|

From my tests I have noticed that changing fps works fine, but sometimes camera has to be reset a couple of times to work properly (toggling the PWM mode button). Changing shutter angle in PWM mode (or having shutter angle sync engaged) also doesn't seem to work properly.

## Backing up the SD card

To make a compressed image backup of the SD card onto the attached drive:

```
sudo sh -c 'pv -s $(blockdev --getsize64 /dev/mmcblk0) /dev/mmcblk0 | xz -3 -c > /media/RAW/cinemate_v3-pi_4+5_bookworm_image_$(date +%Y-%m-%d_%H-%M-%S).img.xz'
```

Backing up CineMate image takes about 30 min.

## Notes when using Pi 4

On Raspberry Pi 4 the tuning file currently fails to load properly for libcamera so no tuning file is applied to the actual image. The tuning file is used though for CineMate calculation of WB values.

## Known issues

- Frame drops when using NTFS formatted SSD drives
- Recording stops after a couple of seconds when using ext4 formatted SSD drives    

## Todo

- [x] fix shutter angle values array calculation
- [ ] simple_gui.py adaptive layout for non 1920x1080 screens
- [x] fix frame rate / shutter angle sync for constant exposure during fps change
- [x] mounting mechanism should be improved. Drives seem to not mount when detatched and then reconnected
- [x] anamorphic factor to be moved to settings file.
- [ ] 16 bit modes for imx585
- [ ] support for imx294
- [x] optimize recording to allow for the use of 300 MB/s SSD drive
- [x] optimize operating system for faster boot and smaller image file
- [ ] overclocking of ISP
- [ ] optional auto-exposure
- [ ] hardware sync of sensor frame capture, perhaps via a pico
- [ ] rendering mode, for creating proxy files in camera (using https://github.com/mrjulesfletcher/dng_to_video)
- [ ] automatic detection of attached sensor and dynamic dtoverlay

