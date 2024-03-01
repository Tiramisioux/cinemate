```cinemate development branch```

## Hardware requirements
- Rasberry Pi 4B
- Official HQ or GS camera
- Samsung T5/T7 SSD

## Installing 

Download disk image from here: https://github.com/Tiramisioux/cinemate/releases/tag/dev

Burn to SD card using Raspberry Pi imager or Balena Etcher. CineMate should autostart

    User: pi
    Password: 1

## CineMate autostart

CineMate autostarts by default. To disable autostart:

    cd cinemate
    make stop

To enable (and start) again

    cd cinemate
    make start

To run CineMate manually, type

    cinemate

anywhere in the cli.

## Updating the Development Branch

    cd cinemate
    git pull origin development


## Camera functions

|Function|type|GPIO|cinemate cli/usb serial command|comment|
|---|---|---|---|---|
|start/stop recording|button|4,5|rec||
|rec light|led|5, 21|||
||||||
|iso increase|button|27|`iso inc`||
|iso decrease|button|10|`iso dec`||
|shu increase|button|n/a|`shu inc`||
|shu decrease|button|n/a|`shu dec`||
|fps increase|button|n/a|`fps inc`||
|fps decrease|button|n/a|`fps dec`||
|iso rotary encoder clk|rotary enc|9|||
|iso rotary encoder dt|rotary enc|11|||
|shu rotary encoder clk|rotary enc|23|||
|shu rotary encoder dt|rotary enc|25|||
|fps rotary encoder clk|rotary enc|8|||
|fps rotary encoder dt|rotary enc|7|||
|potentiometer lock|switch|24||Locks shu and fps pots.|
|resolution switch|switch|not assigned|||
|sync shutter angle to fps|switch|16|`shutter_sync 0` or `shutter_sync 1`||
|double fps|button|12||Instant slow motion mode, Press once to double fps and press a second time to revert to original fps. If in PWM mode, camera will speed ramp up and down.|
|pwm mode|switch|22|`pwm 0` or `pwm 1`|Switches camera software to PWM mode.  <br>  <br>Background: https://github.com/Tiramisioux/libcamera-imx477-speed-ramping/|
|PWM pin|output pin|19||Controls shutter angle and fps with hardware PWM signal from the PI (3V) through a voltage divider to the camera XVS trigger pin (wants 1.65V). Also connect the camera ground pin to Pi ground. Now shutter angle and fps can be changed even while in recording mode, without restarting the sensor.|
|system button|button|26|||
|set iso||n/a|`iso` + integer||
|set shutter angle nom||n/a|`shutter_a_nom` + float||
|set fps||n/a|`fps` + integer||
|set resolution||n/a|`res 0` or `res 1`||
|print camera settings to CLI||n/a|`get`||
|unmount SSD||n/a|`unmount`|

