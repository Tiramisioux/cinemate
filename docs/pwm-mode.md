# PWM Mode (Experimental)

PWM mode sets the Raspberry Pi HQ/GS sensors in sink mode, as explained [here](https://github.com/Tiramisioux/libcamera-imx477-speed-ramping).

This makes it possible to feed the sensor XVS input with a hardware PWM signal from the Pi (CineMate uses pin 19 as default, but pin 18 also supports hardware PWM), allowing for hardware control of FPS and shutter angle during recording, without restarting the camera.

| :exclamation:  Note! Be sure to use a voltage divider so the PWM signal is converted to 1.65V.   |
|-----------------------------------------|

This function is an experiment inspired by my old Nizo 8mm camera which has a button for doubling the motor speed, achieving in-camera speed ramping.

From my tests, I have noticed that changing FPS works fine, but sometimes the camera has to be reset a couple of times to work properly (toggling the PWM mode button). Changing the shutter angle in PWM mode (or having shutter angle sync engaged) also doesn't seem to work properly.
