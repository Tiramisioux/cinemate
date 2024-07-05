# GPIO Setup

## Basic Setup

Insert the SD card into the Pi. Connect the camera, HDMI monitor, and SSD drive.

Connect simple push buttons or use a paper clip for basic camera operation.

|Camera function                 |GPIO push button |
|--------------------------------|-----------------|
|start/stop recording            |4, 5             |
|increase iso one step           |27               |
|decrease iso one step           |15               |
|change resolution               |26 (single click)|
|reboot                          |26 (double click)|
|safe shutdown                   |26 (triple click)|
|unmount SSD                     |26 (hold for 3 seconds)|

Rec light LED can be connected to pins 6 or 21.

| :exclamation:  When connecting an LED to the GPIOs, be sure to use a resistor   |
|-----------------------------------------|

|:point_up:  Connect GPIO 26 to GPIO 03 using a jumper wire, and the system button attached to GPIO 26 will also wake up the Pi, after being shutdown.   |
|-----------------------------------------|
    