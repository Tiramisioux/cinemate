# cinemate2
Manual controls and a simple GUI for cinepi-raw, adding basic functionality of starting and stopping recording and changing camera parameters (ISO, shutter angle and frame rate) via the GPIO pins. You can also start/stop recording using a USB keyboard.

Preinstalled image file with Raspbian + cinepi-raw + cinemate2 can be found in the release section of this repository.

## Basic functions

- Autostarts cinepi-raw with a simple GUI on the HDMI display.

- Enables recording on GPIO 4

- Change camera parameters and start/stop recording via USB keyboard

- Enables LED rec light on GPIO 21 (be sure to use a resistor between GPIO and LED!)

- Enables toggling of ISO (100, 200, 400, 800, 1600, 3200) on GPIO 23 (increase one step) and GPIO 25 (decrease one step). 

- Enables toggling of resolution (full frame/cropped frame) on GPIO 13

## Advanced functions

- Automatic recording of audio scratch track (needs a USB microphone)

- Assign your own GPIO pins for various camera control (start /stop recording, change ISO, resolution etc) 

- Attach a Grove Base HAT for control of ISO, shutter angle and fps via potentiometers

_For adding cinemate2 manually to an existing cinepi-raw installation, follow install instructions below._

## Dependencies
<code>sudo apt update</code>

<code>sudo apt upgrade</code>

<code>sudo apt install python3-pip</code>

<code>sudo apt-get install portaudio19-dev</code>

<code>sudo pip3 install psutil Pillow redis keyboard pyudev sounddevice</code>

## Installation

Even if we are not using the Grove Base HAT, we need to install it for scripts to work

### Installing the Grove Base Hat

<code>sudo apt-get install build-essential python3-dev python3-pip python3-smbus python3-serial git</code>

<code>sudo pip3 install -U setuptools wheel</code>

<code>sudo pip3 install -U grove.py</code>

<code>git clone https://github.com/Seeed-Studio/grove.py.git</code>

<code>cd grove.py</code>

<code>sudo python3 setup.py install</code>

#### Enable I2C

<code>sudo raspi-config</code>

<code>3 Interface Options > I5 I2C Enable > Yes</code>

<code>sudo reboot</code> 

### Install Cinemate2 scripts

<code>git clone https://github.com/Tiramisioux/cinemate2</code>

<code>cd cinemate2</code>

<code>make install</code>

Main.py will now run automatically at startup.

## Uninstall

To uninstall:

<code>cd cinemate2</code>

<code>make uninstall</code>

## Starting and stopping the scripts

<code>cd cinemate2</code>

<code>make start</code> or <code>make stop</code>

or

<code>cd src</code>

<code>sudo python3 main.py</code>

<code>main.py</code> has to be run as root to enable the keyboard module

## Default manual control settings

|GPIO |USB Keyboard|Grove Base HAT Analog channel| Type |Function  |
--- | --- | --- | --- | --- |
|4, 5, 22|r ||push button|    start/stop recording|
|6, 21, 23|||LED (be sure to use a 320k resistor on this pin!)|     rec signal out, for LED rec light |
|24|h||  push button|change resolution (cropped and full frame)|
|25 |1||push button |ISO decrease (100, 200, 400, 800, 1600, 3200)|
|23 |2||push button |ISO increase (100, 200, 400, 800, 1600, 3200)|
||3|||shutter angle decrease (1-360 degrees)|
||4|||shutter angle increase (1-360 degrees)|
||5|||fps decrease (1-50)|
||6|||fps increase (1-50)|
|18 |||switch |50% frame rate|
|19 |||switch |200% frame rate (up to 50 fps)|
|||A0|potentiometer|ISO control (overrides any GPIO pins assigned to iso)|
|||A2|potentiometer |shutter angle control|
|||A4|potentiometer|frame rate control|

GPIO pin numbers and Grove Base HAT analog channels can be in <code>main.py</code>.

If USB keyboard is connected, Grove Base HAT analog channels are disabled.

## Known issues

HDMI monitor has to be connected on startup for scripts to work.

Sometimes script does not recognize SSD drive on startup. Then disconnect and connect the drive again.
