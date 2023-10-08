# CineMate – manual controls for CinePi v2
CineMate Python scripts is a way for users to implement and customize manual controls for their CinePi v2 build. 

Project aims at offering an easy way to build a custom camera. For basic operation and experimentation, only Raspberry Pi, camera board and monitor is needed. For practical use, buttons and switches can easily be added, allowing for a custom build.

## Functions
- Enables recording and various camera controls with **RPi GPIO**, **USB keyboard/numpad**, **serial input** via USB (works with any microcontroller writing to serial) and (a rudimentary) **CineMate CLI** via SSH.
- Simple GUI on the HDMI display.
- Recording of audio scratch track using a USB microphone.
- System button for safe shutdown, start-up and unmounting of SSD drive.
- Attach a Grove Base HAT for iso, shutter angle and fps controls via potentiometers.

## CLI example

<img width="500" alt="cinemate_cli_example2" src="https://github.com/Tiramisioux/cinemate/assets/74836180/e920dab4-a37c-494d-a91c-c3eba709ef1b">

Startup sequence showing the output from the different CineMate modules. For users experimenting with their own build/GPIO configuration, scripts output extensive logging info.

## Hardware setup
In order to get cinepi-raw and CineMate scripts running, you need:

- Raspberry Pi 4B (4 or 8 GB versions have been tested)
- Raspberry Pi IMX477 HQ camera board (rolling/global shutter variants both work)
- HDMI capable monitor/computer screen

For recording raw frames, a fast SSD is needed. Samsung T5/T7 will work. SSD needs to be formatted as NTFS and named "RAW".

For hardware control of camera settings and recording, see below.

## Installation
### Preinstalled image 
Preinstalled image file with Raspbian, cinepi-raw and CineMate scripts can be found in the release section of this repository. Burn this image onto an SD card and start up the Pi. Make sure you have an HDMI monitor hooked up on startup, in order for the simple gui module to start up properly.

### Manual install
The scripts can be also manually installed onto a Rasberry Pi 4B already running CinePi v2.
#### Modifications to cinepi-raw
For CineMate scritps to work properly, some modifications need do be made to the cinepi-raw installation. 

Instructions here: https://github.com/Tiramisioux/cinemate/blob/main/docs/cinepi_raw_installation_notes_2023-03-03.txt

#### Dependencies
`sudo apt update`

`sudo apt upgrade`

`sudo apt full-upgrade` (updates Raspbian, enabling the Raspberry Pi Global Shutter camera)

`sudo apt install python3-pip`

`sudo apt-get install -y i2c-tools portaudio19-dev`

`sudo pip3 install psutil Pillow redis keyboard pyudev sounddevice smbus2 gpiozero RPI.GPIO evdev termcolor pyserial inotify_simple`

#### Installing the Grove Base HAT
`sudo apt-get install build-essential python3-dev python3-pip python3-smbus python3-serial git`

`sudo pip3 install -U setuptools wheel`

`sudo pip3 install -U grove.py`

`git clone https://github.com/Seeed-Studio/grove.py.git`

`cd grove.py`

`sudo python3 setup.py install`

`sudo raspi-config`

3 Interface Options > I5 I2C Enable > Yes

`sudo reboot`

#### Installing CineMate scripts
`git clone https://github.com/Tiramisioux/cinemate.git`

`cd cinemate`

`make install`

`main.py` will now run automatically at startup.

## Starting and stopping CineMate scripts
`cd cinemate`

`make start` / `make stop`

`main.py` is located in the cinemate/src folder and can be manually started from there:

`cd cinemate/src`

`sudo python3 main.py`

Note that `main.py` must be run as root.

## Disable/enable automatic start of CineMate scripts:
in `/home/pi/cinemate/`:

`make uninstall` / `make install`

## Controlling the camera 
Camera settings can be set by using any one of the following methods:

1) Connecting to the Pi via SSH and running the CineMate scripts manually (see above), allowing for a rudimentary CLI.
2) Connecting a USB keyboard or numpad to the Pi.
3) Connecting push buttons to the GPIOs of the Raspberry Pi.
4) Serial control from a microcontroller (such as the Raspberry Pico) connected via USB.
5) Using a Seeed Grove Base HAT, allowing for control using Grove buttons and potentiometers.

|Function|CLI (via SSH) and serial|GPIO|USB keyboard/num pad|Grove Base HAT|
|---|---|---|---|---|
|start/stop recording|`rec`|4, 6, 22|`9`|D6, D22|
|LED or rec light indicator (be sure to use a 320k resistor on this pin!|      |5||D5|
|change iso|`iso` + `value`|||A0|
|change shutter angle|`shutter_a` + `value`|||A2|
|change fps|`fps` + `value`|||A4|
|change resolution (cropped and full frame)|`res 1080` / `res 1520`|13, 24|`8`|D24|
|iso decrease|`iso inc`|25|`1`||
|iso increase|`iso dec`|23|`2`||
|shutter angle decrease|`shutter_a inc`||`3`||
|shutter angle increase|`shutter_a dec`||`4`||
|fps decrease|`fps inc`||`5`||
|fps increase|`fps dec`||`6`||
|50% frame rate||18||D18|
|200% frame rate (up to 50 fps)||19||D19|
|lock shutter angle and frame rate controls||16||D16|
|unmount SSD (double click) / safe shutdown (triple click)|`unmount`|26|`0`|D26|
|print current camera settings to the CLI|`get`||||
|print system time and RTC time to the cli|`time`||||
|set RTC time to system time|`set time`||||

GPIO settings and arrays for legal values can be customized in `main.py`.

TIP! Connect GPIO 26 to GPIO 03 using a jumper wire, and the safe shutdown button attached to GPIO 26 will also wake up the Pi, after being shutdown.

## Mapping of iso, shutter_a and fps to default arrays

When changing iso, shutter angle or fps using the `inc` or `dec` commands, default arrays are used. This can be helpful to limit the amount of possible values, making hardware controls easier to design. 

|Camera setting|Default legal values|
|---|---|
|ISO |100, 200, 400, 640, 800, 1200, 1600, 2500, 3200|
|Shutter angle |45, 90, 135, 172.8, 180, 225, 270, 315, 346.6, 360|
|FPS |1, 2, 4, 8, 16, 18, 24, 25, 33, 48, 50|

Above default arrays can be customized in `main.py`. 

## Precise control of iso, shutter_a and fps 

When setting iso, shutter angle or fps using Cinemate CLI or serial control, any value can be set. 

For CineMate CLI/serial, type the `control name` + `blank space` + `value`. Iso and fps accept integers. Shutter angle accepts floating point numbers with one decimal. 

`iso 450` 

`shutter_a 23.4`

`fps 31`

## Simple GUI

<img width="500" alt="cinemate_cli_example2" src="https://github.com/Tiramisioux/cinemate/assets/74836180/8dd9aac9-ea98-4e8c-8691-5c5541f35b54">

Simple GUI is displaying iso, shutter angle, frame rate, CPU load and temperature and minutes of recording left on the disk.

During recording, the GUI shows red bands above and below the preview to indicate recording. If a microphone, keyboard and/or serial device is connected and recognized by the system, this is indicated by the GUI.

Finally GUI diplays the lastly written file to the SSD, and also if the last clip is accompanied by a scratch audio track to help the user to make sure dng files are ending up on the SSD.

## Ideas for build
Tinkercad model for the below build can be found here:

https://www.tinkercad.com/things/eNhTTYdgOM0

Build is designed to work with a Sony RX100 camera cage.

Step by step instruction + parts list coming soon.

<img width="500" alt="cinemate_3_" src="https://github.com/Tiramisioux/cinemate/assets/74836180/3feb15b4-8ba5-4590-bc9c-a678d1c64ff1">

<img width="500" alt="cinemate_14" src="https://github.com/Tiramisioux/cinemate/assets/74836180/76800c52-ff97-4b83-9995-9046259b1da7">

<img width="500" alt="cinemate_6_" src="https://github.com/Tiramisioux/cinemate/assets/74836180/ae3ef7d1-90c4-4940-ba70-dbcf4c27585e">

<img width="500" alt="cinemate_16" src="https://github.com/Tiramisioux/cinemate/assets/74836180/87f6b97e-f073-4200-bbe4-d12be3d5c396">


## Known issues

- HDMI monitor has to be connected on startup for scripts to work.
- Sometimes script does not recognize SSD drive on startup. Then try disconnecting and connecting the drive again.
- Be sure to do a safe shutdown of the Pi before removing the SSD, otherwise the last two clip folders on the drive might become corrupted.

## Notes on audio sync

Actual frame rate of the IMX477 sensor fluctuates about 0.01% around the mean value. This has no visual impact but will impact syncing of external audio. If recording synced audio, make sure to use a clapper board in the beginning and the end of the take. This will make it easier to sync the sound, but sync might still drift back and forth.

Solution to this might be to use an external trigger for the camera board, like suggested here:

https://www.raspberrypi.com/documentation/accessories/camera.html#using-the-hq-camera

Currently investigating the possibility to use the hardware PWM signal on the Pi, fed to the camera board via a voltage divider, for the frame rate to be dead on the selected value.

Audio scratch track function has been confirmed to work whih this type of USB microphone:

<img width="200" alt="cinemate_still_4" src="https://github.com/Tiramisioux/cinemate/assets/74836180/f5be69e9-b4cb-4050-9a45-3206ade71b4b">

## Notes on RTC

Cinepi-raw names the clips according to system time. For clips to use the current time of day, an RTC (realtime clock unit) can be installed.

To get the right system time on the Pi, simply connect to a computer connected to the internet via SSH and the Pi will update its system time.

To check system time in the CineMate CLI, type `time`

To write system time to a connected RTC, in the Cinemate CLI, type `set time`. 

Now, if not connected to the internet, on startup the Pi will get its system time from the RTC.

## Notes on rec light logic

Occationaly, the red color in the simple gui, and the LED connected to the rec light output might blink. This is expected behaviour and does not mean frames are dropped.

The reason is that the rec light logic is based on whether frames are writted to the SSD. Occationaly, cinepi-raw buffers frames before writing them to the SSD, leading to a brief pause in the writing of files to the SSD, causing the light to blink.

## Backing up the SD card

To make a compressed image backup of the SD card onto the SSD:

```sudo dd if=/dev/mmcblk0 bs=1M status=progress | xz -c > /media/RAW/cinepi_cinemate_raspbian_image_$(date +%Y-%m-%d_%H-%M-%S).img.xz```

## Image examples

Images shot with Schneider Kreuznach Variagon 18-40 zoom / 1967. Developed as BMD RAW in Davinci Resolve with Arri LogC to Rec LUT

<img width="500" alt="cinemate_still_3" src="https://github.com/Tiramisioux/cinemate/assets/74836180/5d1a914a-982e-4077-b3a4-683bb2a65615">

<img width="500" alt="cinemate_still_2" src="https://github.com/Tiramisioux/cinemate/assets/74836180/b4915ce4-2d02-4892-a21d-ec88e59120c1">

<img width="500" alt="cinemate_still_1" src="https://github.com/Tiramisioux/cinemate/assets/74836180/8c95b7d6-7f7e-4502-94c0-81efdf24fe04">

<img width="500" alt="cinemate_still_5" src="https://github.com/Tiramisioux/cinemate/assets/74836180/6d373857-d086-4ae9-8cea-8987112bffcc">

<img width="500" alt="cinemate_still_4" src="https://github.com/Tiramisioux/cinemate/assets/74836180/70aaeefb-3e32-41fe-ba7c-783532f02a47">

## CineMate build

<img width="500" alt="cinemate_7" src="https://github.com/Tiramisioux/cinemate/assets/74836180/9f2dd0b7-4236-4910-adf9-51d6eb768ec9">

<img width="500" alt="cinemate_10" src="https://github.com/Tiramisioux/cinemate/assets/74836180/0369ea53-2d9b-4e6d-a2c5-28ed46c6d366">

<img width="500" alt="cinemate_8" src="https://github.com/Tiramisioux/cinemate/assets/74836180/b024e2a4-d721-4d50-972d-c7bf72116f75">

<img width="500" alt="cinemate_9" src="https://github.com/Tiramisioux/cinemate/assets/74836180/c4331f89-ef47-43b0-818b-8ebda90e28b3">

