# cinemate2
Manual controls and a simple GUI for cinepi-raw, adding basic functionality of starting and stopping recording and changing camera parameters (ISO, shutter angle and frame rate) via the GPIO pins.

Preinstalled image file with Raspbian + CinePi RAW can be found in the release section of this repository.

For adding cinemate2, follow install instructions below. 

## Basic functions

- Autostarts cinepi-raw with a simple GUI on the HDMI display.

- Enables recording on GPIO 4.

- Enables LED rec light on GPIO 21 (be sure to use a resistor between GPIO and LED!)

- Enables toggling of ISO (100, 200, 400, 800, 1600, 3200) on GPIO 23 (increase one step) and GPIO 25 (decrease one step). 

- Enables toggling of resolution (full frame/cropped frame) on GPIO 13

## Advanced functions

- Automatic recording of audio scratch track (needs a USB microphone)

- Assign your own GPIO pins for various camera control (start /stop recording, change ISO, resolution etc) 

- Attach a Grove Base HAT for control of ISO, shutter angle and fps via potentiometers

## Dependencies
<code>sudo apt update</code>

<code>sudo apt upgrade</code>

<code>sudo apt install python3-pip</code>

<code>sudo pip3 install psutil Pillow redis</code>

## Installation

To install the scripts and make them run as a service.

<code>git clone https://github.com/Tiramisioux/cinemate2</code>

<code>cd cinemate2</code>

<code>make install</code>

## Uninstall

To uninstall:

<code>cd cinemate2</code>

<code>make uninstall</code>

## Starting and stopping the scripts

<code>cd cinemate2</code>

<code>make start</code> or <code>make stop</code>

or

<code>python3 main.py</code>

## Installing the Grove Base Hat

<code>sudo apt-get install build-essential python3-dev python3-pip python3-smbus python3-serial git</code>

<code>sudo pip3 install -U setuptools wheel</code>

<code>sudo pip3 install -U grove.py</code>

<code>git clone https://github.com/Seeed-Studio/grove.py.git</code>

<code>cd grove.py</code>

<code>sudo python3 setup.py install</code>

### Enable I2C

<code>sudo raspi-config</code>

<code>3 Interface Options > I5 I2C Enable > Yes</code>

<code>sudo reboot</code>

## Default GPIO settings

The script makes use of the GPIO pins as follows:

|Basic GPIO |Function  |
--- | --- |
|GPIO 4|     recording pin|
|GPIO 21|     rec signal out pisn, for LED rec light (be sure to use a resistor on this pin!)|
|GPIO 24|     resolution switch|
|GPIO 26 |     shutter angle lock switch|
|GPIO 18 |    frame rate lock switch|

|Grove Base HAT |Function  |
--- | --- |
|GPIO 5|     recording pin|
|GPIO 6|     rec signal out pin, for LED rec light (be sure to use a resistor on this pin!)
|A0|ISO potentiometer (overrides any GPIO pins assigned to iso)|
|A2|shutter angle potentiometer|
|A4|frame rate potentiometer|

Multiple pins can be assigned to a camera functions. Pins can be defined by the user when instantiating the manual_controls class.
