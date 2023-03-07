# cinemate2
Manual controls and a simple GUI for cinepi-raw, adding basic functionality of starting and stopping recording and changing camera parameters (ISO, shutter angle and frame rate) via the GPIO pins.

For the scripts to work properly, some modifications need to be made to the cinepi-raw installation. You can find instructions in the file <code>cinepi_raw_installation_notes_2023-03-03.txt</code> or download and install the ready made image file in the release section of this repository.

## Basic functions

- Autostarts cinepi-raw with a simple GUI on the HDMI display.

- Enables recording on GPIO 4.

- Enables LED rec light on GPIO 21 (be sure to use a resistor between GPIO and LED!)

- Enables toggling of ISO (100, 200, 400, 800, 1600, 3200) on GPIO 23 (up) and GPIO 25 (down). 

- Enables toggling of resolution (full frame/cropped frame) on GPIO 13

## Dependencies
<code>sudo apt update</code>

<code>sudo apt upgrade</code>

<code>sudo apt install python3-pip</code>

<code>sudo pip3 install psutil Pillow redis</code>

## Installation

To install the scripts and make them run as services:

<code>git clone https://github.com/Tiramisioux/cinemate2</code>

<code>cd cinemate2</code>

<code>make install</code>

## Uninstall

To uninstall (or stop) the scripts:

<code>cd cinemate2</code>

<code>make uninstall</code>

## Set initial shutter angle value

Do this once, for the cinepi-raw installation: 

<code>redis-cli</code>

<code>set shutter_a 180</code>

<code>publish cp_controls shutter_a</code>

<code>exit</code> 

## How it works

Script works similar to <code>bmd_proxy.py</code> in CinePi version 1. It uses the file  <code>redis_proxy.py</code> to load control objects of camera parameters and a monitor object to monitor the framecount of cinepi-raw. 

We can add control classes from <code>redis_proxy.py</code>, allowing us to read and write shutter angle and frame rate.

Simple Python example:

<code>from redis_proxy import CameraParameters</code>

<code>fps_setting = CameraParameters("FPS")</code>

<code>current_fps = fps_setting.get()</code>

<code>print(current_fps)</code>

<code>new_fps = fps_setting.set(50)</code>

<code>current_fps = fps_setting.get()</code>

<code>print(current_fps)</code>

## Using the Seeed Studio Grove Base Hat

The file <code>manual_controls_grove_base_hat.py</code> is also autostarted in the above install process. The script allow you to add a Grove Base Hat for easier connection of potentiometers for ISO, shutter speed and frame rate and buttons and switches for other controls.

### Installing the Grove Base Hat

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



### Connections overview

![IMG_0489](https://user-images.githubusercontent.com/74836180/223561273-fed7e4df-c563-4959-aa38-d72583ad1880.JPG)

The script makes use of the inputs as follows:

|Connection |Function  |
--- | --- |
|A0|ISO potentiometer|
|A2|shutter angle potentiometer|
|A4|frame rate potentiometer|
|GPIO 18|     recording pin|
|GPIO 19|     rec signal out pin, for LED rec light (be sure to use a resistor on this pin!)|
|GPIO 26|     resolution switch|
|GPIO 16|     frame rate half speed|
|GPIO 17|     frame rate double speed|
|GPIO 5 |     shutter angle fps sync mode for constant exposure OR constant motion blur on fps change|
|GPIO 22 |    frame rate lock switch|

_Note that GPIO 4 and 21 (rec pin/rec out pin), 23 and 25 (ISO up/down and 13 (toggle resolution) from the basic setup above still works._











