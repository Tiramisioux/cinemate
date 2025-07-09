## Overview
CineMate scripts is a way for users to implement and customize manual controls for their [cinepi-raw](https://github.com/cinepi/cinepi-raw) build. 

Project aims at offering an easy way to build a custom camera. For basic operation and experimentation, Raspberry Pi, camera board and monitor is needed. For practical use, buttons and switches can easily be added.

A ready made disk image can be found [here](https://github.com/Tiramisioux/cinemate/releases).

Join the CinePi Discord [here](https://discord.gg/Hr4dfhuK).

### How CineMate and cinepi-raw fork fit together

The original **cinepi-raw** project by Csaba Nagy is a C++/libcamera application that records 12-bit CinemaDNG sequences on Raspberry Pi hardware. It extends Raspberry Pi’s own *rpicam-apps* with a custom DNG encoder and a lightweight Redis‐based API so external tools can change parameters, start/stop takes, etc.

### CineMate (this repo) – the frontend  
CineMate is a pure-Python companion that autostarts on the Pi, shows a simple GUI over HDMI, maps GPIO buttons/encoders, and talks to **cinepi-raw** through Redis commands. Think of it as the “camera body UI” while *cinepi-raw* is the “sensor & recorder”.

### TL;DR  
* **cinepi/cinepi-raw** =  recorder  
* **cinepi/cinepi-raw cinemate forkk** = recorder + patches CineMate depends on  
* **CineMate** = user interface that drives the fork over Redis  

Use them together for a turnkey Raspberry Pi cinema camera.

## Getting started

### Hardware requirements
- Rasberry Pi 5
- Official HQ or GS camera
- HDMI monitor or device (phone or tablet) for monitoring

### Installation
1. Burn image to SD card. 8 GB or larger.

2. Connect Pi and camera sensor board.

| :exclamation:  When connecting the camera module to the Pi, make sure it is the Pi is not powered. It is not advised to hot-swap the camera cable.   |
|-----------------------------------------|

3) Boot up the Pi. CineMate should autostart

4) For preview, attach a HDMI monitor or connect phone/tablet to: 

Wifi `CinePi` 
password `11111111`.

In web browser, navigate to `cinepi.local:5000`. A clean feed (without GUI) is available at `cinepi.local:8000/stream`.

4. For recording, attach an **SSD drive** (Samsung T7 recommended), high speed **NVME drive** or **[CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/)** by Will Whang. Drive needs to be formatted as ext4 and named "RAW". Connect a button to GPI05 and GND or simply short circuit the two using a paper clip. If you are using the phone preview option, you can start/stop recording by tapping the preview.

## Customization

### Connecting to Pi with SSH:

```
user: pi
password: 1
```

### Starting/stopping CineMate manually

CineMate autostarts by default. 

For running CineMate manually from the cli type `cinemate`. This will also display extensive logging which can be useful when configuring and testing buttons and switches.

To stop the autostarted CineMate instance::

```bash
cd cinemate
```

To stop the autostarted instance:
```bash
make stop
```

To start again:
```bash
make start
```

To disable autostart:
```bash
make disable
```

To enable autostart:
```bash
make install
make enable
```

### Adjusting config.txt for different sensors:

```
sudo nano /boot/firmware/config.txt
```

Uncomment the section for the sensor being used, and make sure to comment out the others. Reboot the Pi for changes to take effect.

CineMate is compatible with Raspberry Pi HQ camera (IMX477), Global Shutter camera (IMX296), OneInchEye (IMX283), StarlightEye (IMX585) color and monochrome variants.

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

| **Command (example syntax)**                            | **Notes**                                                                                                                          |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `rec`                                                   | Start **or** stop recording (toggles each time you issue it).                                                                                    |
| `set iso 800`              | Set the sensor’s ISO gain to an integer value.                                                                                                   |
| `set shutter a 172.8`  | Set the shutter angle (degrees). Use a floating-point number for fractional angles.                                                              |
| `set fps 24`               | Set the project frame-rate in whole frames per second.                                                                                           |
| `set iso lock` <br/>`set iso lock 1`            | **Toggle or set ISO lock**<br/>• Without a value: toggles the lock on/off.<br/>• With a value + `lock 1`: sets ISO to that value *and* locks it. |
| `set shutter a lock`<br/>`set shutter a lock 1` | **Toggle or set shutter-angle lock** (same behavior as ISO lock, but for shutter angle).                                                         |
| `set fps lock`<br/>`set fps lock 1`             | **Toggle or set FPS lock** (same behavior as above, but for frame-rate).                                                                         |
| `set fps_double`                                        | Toggle “FPS double” mode (doubles the current FPS).                                                                                              |
| `set fps_double 1` (or `0`)                             | Explicitly enable (`1`) or disable (`0`) “FPS double” mode.                                                                                      |


## Simple GUI

Simple GUI is available via browser and/or attached HDMI monitor.

- Red color means camera is recording.
- Purple color means camera detected a drop frame 
- Green color means camera is writing buffered frames to disk. You can still start recording at this stage, but any buffered frames from the last recording will be lost.

Buffer meter in the lower left indicates number of frames in buffer. Useful when testing storage media.

When a compatible USB microphone is connected, VU meters appear on the right side of the GUI so you can monitor audio levels.

## Audio recording (experimental) <img src="https://img.shields.io/badge/cinepi--raw%20fork-ff69b4?style=flat" height="14">

CineMate can capture audio alongside the image sequence. Support is currently limited to a few USB microphones with hard coded configurations:
 - **RØDE VideoMic NTG** – recorded in stereo at 24‑bit/48 kHz.
 - **USB PnP microphones** – recorded in mono at 16‑bit/48 kHz.

Audio is written as `.wav` files into the same folder as the `.dng` frames. The implementation is still experimental and audio/video synchronization needs further investigation.

## storage-automount service
`storage-automount` is a systemd service that watches for removable drives and mounts them automatically. The accompanying Python script reacts to udev events and the CFE-HAT eject button so drives can be attached or detached safely.

It understands `ext4`, `ntfs` and `exfat` filesystems. Partitions labelled `RAW` are mounted at `/media/RAW`; any other label is mounted under `/media/<LABEL>` after sanitising the name. This applies to USB SSDs, NVMe drives and the CFE-HAT slot.

The service is already installed on the cinemate image file. To manually install and enable the service with:

```bash
cd cinemate/services/storage-automount
sudo make install
sudo make enable
```

You can stop or disable it later with:
```bash
sudo make stop
sudo make disable
```

## Settings file
The settings file can be found in `/home/pi/cinemate/src/settings.json`. Here the user can define their own buttons, switches and rotary encoders.

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

#### GPIO output
Default rec LED pins are 6 and 21. Make sure to use a 220 Ohm resistor on this pin!

```json
  "gpio_output": {
    "pwm_pin": 19,
    "rec_out_pin": [6, 21]
  },
```

#### Arrays

Set desired arrays for ISO, shutter angle values, fps and white balance.

```json
  "arrays": {
    "iso_steps": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],
    "shutter_a_steps": [1, 45, 90, 135, 172.8, 180, 225, 270, 315, 346.6, 360],
    "fps_steps": [1, 2, 4, 8, 12, 16, 18, 24, 25, 33, 40, 50],
    "wb_steps": [3200, 4400, 5600]
  },
```

CineMate interpolates redis cg_rb settings used by libcamera based on the selected white balance value in the above array and the tuning file for the sensor being used.

#### Settings
```json
  "settings": {
    "light_hz": [50, 60]
  }
```

CineMate dynamically adjusts the shutter_a_steps array on fps change, adding the flicker free angles given the current frame rate and the hz values defined by the user.

#### Anamorphic preview
```json
    "anamorphic_preview": {
      "anamorphic_steps": [1, 1.33, 2.0],
      "default_anamorphic_factor": 1
    }
```

The anamorphic_preview section allows users to define an array of selectable anamorphic factors (anamorphic_steps) and set a default value (default_anamorphic_factor). The anamorphic factor is used to adjust the aspect ratio of the preview.


#### Analog Controls
Default settings are `None`. Map Grove Base HAT ADC channels to iso, shutter angle, fps and white balance controls. 

```json
  "analog_controls": {
    "iso_pot": 0,
    "shutter_a_pot": 2,
    "fps_pot": 4,
    "wb_pot": 6
  }
```

#### Buttons
Setup buttons with actions for different interactions. Methods are the same as the CineMate CLI commands. Arguments can also be added here

```json
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

```json
{
    "pin": 16,
    "state_on_action": {"method": "set_shutter_a_sync", "args": [false]},
    "state_off_action": {"method": "set_shutter_a_sync", "args": [true]}
}
```

#### Rotary Encoders
Configure rotary encoders for settings adjustments and optional button presses:

```json
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

```json
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
| IMX477 | 0    | 2028 x 1080  | 1.87         | 12        | 50      | 4.3            |
|        | 1    | 2028 x 1520  | 1.33         | 12        | 40      | 5.3            |
|        | 2    | 1332 x 990   | 1.34         | 10        | 120     | 2.7             |
| IMX585 | 0    | 1928 x 1090  | 1.77         | 12        | 87      | 4              |
|        | 1    | 3840 x 2160  | 1.77         | 12        | 34      | 4              |


'*' Note that maximum fps will vary according to disk write speed. For the specific fps values for your setup, make test recordings and monitor the output. Purple background in the monitor/web browser indicates drop frames. You can cap CineMates max fps values for your specific build by editing the file `cinemate/src/module/sensor_detect.py`

## Storage media and sustainable frame rates

_To be added._

## Multi camera support <img src="https://img.shields.io/badge/cinepi--raw%20fork-ff69b4?style=flat" height="14">

CineMate automatically detects each camera connected to the Raspberry Pi and spawns a separate `cinepi-raw` process per sensor. By default:

- **Primary camera** (first detected) displays its preview on HDMI port 0.
- **Secondary cameras** run with `--nopreview` and map to subsequent HDMI outputs (cam1→HDMI 1, cam2→HDMI 2, etc.).
- Preview windows are centered and sized according to your `geometry` settings.

You can override default HDMI mappings in `settings.json` under the `output` section:

## Additional hardware

CineMate image file comes pre-installed with:
- [StarlightEye](https://www.tindie.com/products/will123321/starlighteye/)
- [CFE Hat](https://www.tindie.com/products/will123321/cfe-hat-for-raspberry-pi-5/)
- [Grove Base HAT](https://wiki.seeedstudio.com/Grove_Base_Hat_for_Raspberry_Pi/)

## Module architecture
CineMate is composed of many small modules that run as threads. The `main.py` file loads `settings.json`, configures logging and starts each module. These modules talk to one another via the `RedisController` class which wraps a local Redis instance.

`cinepi_multi.CinePiManager` launches one `cinepi-raw` process per detected sensor and relays log messages back through Redis. Input modules (buttons, rotary encoders, serial, etc.) translate hardware events into the CLI commands listed above. Output modules such as `GPIOOutput`, `SimpleGUI` and `I2cOled` read Redis keys to update LEDs, the framebuffer or an OLED display.  

## Backing up the SD card

To make a compressed image backup of the SD card onto the attached drive:

```
img=/media/RAW/cinemate_$(date +%F_%H-%M-%S).img; echo "Start: $(date)"; sudo dd if=/dev/mmcblk0 bs=4M status=progress of="$img" && sudo pishrink -z "$img" && echo "End: $(date)"
```
Backing up CineMate image takes about 10 min.

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

