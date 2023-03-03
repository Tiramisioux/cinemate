# cinemate2
Handy scripts for manual control of cinepi-raw, adding basic functionality of starting and stopping recording and changing camera parameters (ISO, shutter angle and frame rate) via the GPIO pins.

For the scripts to work properly, some modifications need to be made to the cinepi-raw installation. You can find instructions in the file <code>cinepi_raw_installation_notes_2023-03-03.txt</code> or download and install the ready made image file in the release section of this repository.

## Basic functions

Autostarts cinepi-raw, manual controls and a simple gui on the HDMI display.

Enables recording on GPIO 4.

Enables LED rec light on GPIO 21 (be sure to use a resistor between GPIO and LED!)

Enables toggling of ISO (100, 200, 400, 800, 1600, 3200) on GPIO 23 (up) and GPIO 25 (down). 

Enables toggling of resolution (full frame/cropped frame) on GPIO 13

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







