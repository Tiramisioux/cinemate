# cinemate2
Manual controls and a simple GUI for cinepi-raw, adding basic functionality of starting and stopping recording and changing camera parameters (ISO, shutter angle and frame rate) via the GPIO pins. You can also start/stop recording using a USB keyboard.

Preinstalled image file with Raspbian and cinepi-raw can be found in the release section of this repository.

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

- Outputs a tone on RPi audio jack (right channel) during recording of raw frames. Can be used to trigger an external field recorder like the Zoom H6. _Set a limiter on the XY microphone and feed the RPi audio to Track 1 with maximum gain and autostart/stop recording at 0 dB._

## Dependencies
<code>sudo apt update</code>

<code>sudo apt upgrade</code>

<code>sudo apt full-upgrade</code> (updates Raspbian, enabling the Raspberry Pi Global Shutter camera)

<code>sudo apt install python3-pip</code>

<code>sudo apt-get install -y i2c-tools portaudio19-dev</code>

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

<code>main.py</code> must be run as root.

## Default manual control settings

|RPi GPIO |USB Keyboard/Num pad|Grove Base HAT| Type |Function  |
--- | --- | --- | --- | --- |
|4, 6, 22|9 |D6, D22|push button|    start/stop recording|
|5||D5|LED (be sure to use a 320k resistor on this pin!)|     rec signal out, for LED rec light |
|13, 24|8|D24|  push button|change resolution (cropped and full frame)|
|25 |1||push button |ISO decrease (100, 200, 400, 800, 1600, 3200)|
|23 |2||push button |ISO increase (100, 200, 400, 800, 1600, 3200)|
||3|||shutter angle decrease (1-360 degrees)|
||4|||shutter angle increase (1-360 degrees)|
||5|||fps decrease (1-50)|
||6|||fps increase (1-50)|
|18 ||D18|switch |50% frame rate|
|19 ||D19|switch |200% frame rate (up to 50 fps)|
|16||D16|switch|lock shutter angle and frame rate controls|
|||A0|potentiometer|ISO control (overrides any GPIO pins assigned to iso)|
|||A2|potentiometer |shutter angle control|
|||A4|potentiometer|frame rate control|
|26|0|D26|push button|unmount SSD (press and hold push button for 2 sec, or keyboard press "0") / safe shutdown (press and hold push button for 6 sec)|

GPIO pin numbers and Grove Base HAT analog channels can be changed in <code>main.py</code>.

If USB keyboard is connected, Grove Base HAT analog channels are disabled.

Connect GPIO 26 to GPIO 03 using a jumper wire, and the safe shutdown button attached to GPIO 26 will also wake up the Pi, after being shutdown

## Known issues

- HDMI monitor has to be connected on startup for scripts to work.
- Sometimes script does not recognize SSD drive on startup. Then try disconnecting and connecting the drive again.
- Be sure to do a safe shutdown of the Pi before removing the SSD, otherwise the last two clip folders on the drive might become corrupted.

## To-do

- Fix issue with keyboard not working when disconnected and connected
