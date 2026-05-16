# Modifying config.txt

## Adjusting config.txt for different sensors:

!!! tip ""
    For easy editing of `config.txt` on the preinstalled image file, type `editboot` anywhere in Raspberry Pi terminal.

If using a manual install without the above alias, type:

```
sudo nano /boot/firmware/config.txt
```

For headless HDMI installs on Raspberry Pi Bookworm, also edit `/boot/firmware/cmdline.txt` and append a single-line KMS video override such as `video=HDMI-A-1:1920x1080M@60D` or `video=HDMI-A-2:1920x1080M@60D`. This pins the boot framebuffer to 1080p so hotplugged HDMI does not fall back to `1024x768`.

Uncomment the section for the sensor being used, and make sure to comment out the others. The clean-install default is `imx477` on `cam0`. For IMX296, IMX283, or StarlightEye color, uncomment that sensor section and set the camera port to the physical connector you are using. Reboot the Pi for changes to take effect.

The raw `P`/`U` packing choice is not set in `config.txt`. Cinemate applies that when launching CinePi-RAW: IMX296 and IMX477 use packed mode on Raspberry Pi 4-family boards and unpacked mode on Raspberry Pi 5 / CM5.

### Example config.txt

```shell
# For more options and information see
# http://rptl.io/configtxt
# Some settings may impact device functionality. See link above for details

# Uncomment some or all of these to enable the optional hardware interfaces
dtparam=i2c_arm=on
#dtparam=i2s=on
#dtparam=spi=on

# Enable audio (loads snd_bcm2835)
dtparam=audio=on

# ---- Camera section ----

# Raspberry Pi HQ camera (IMX477, clean-install default on cam0)
camera_auto_detect=1
dtoverlay=imx477,cam0

# Raspberry Pi GS camera (IMX296, 10-bit RAW)
#camera_auto_detect=1
#dtoverlay=imx296,cam0

# OneInchEye (IMX283)
#camera_auto_detect=0
#dtoverlay=imx283,cam0

# StarlightEye color (IMX585)
#camera_auto_detect=0
#dtoverlay=imx585,cam0

# StarlightEye Mono (IMX585 mono)
#camera_auto_detect=0
#dtoverlay=imx585,cam1,mono

# ---- End camera section ----

# Automatically load overlays for detected DSI displays
display_auto_detect=1

# Automatically load initramfs files, if found
auto_initramfs=1

# Enable DRM VC4 V3D driver
dtoverlay=vc4-kms-v3d
max_framebuffers=2

# Don't have the firmware create an initial video= setting in cmdline.txt.
# Use the kernel's default instead.
disable_fw_kms_setup=1

# Run in 64-bit mode
arm_64bit=1

# Disable compensation for displays with overscan
disable_overscan=1

# Run as fast as firmware / board allows
arm_boost=1

[cm4]
# Enable host mode on the 2711 built-in XHCI USB controller.
# This line should be removed if the legacy DWC2 controller is required
# (e.g. for USB device mode) or if USB support is not required.
otg_mode=1

[cm5]
dtoverlay=dwc2,dr_mode=host

# CFE Hat PCIe 3.0
dtparam=pciex1
dtparam=pciex1_gen=3

[all]
auto_initramfs=1
avoid_warnings=1
disable_splash=1
dtparam=i2c1=on
dtoverlay=miniuart-bt
```

Exit the editor by pressing Ctrl+X.

!!! note ""

    Note that Cinemate needs you to explicitly set the camera port, match that of the physical camera port you are using. Default is `cam0`.

!!! tip ""

    The preinstalled image file comes with **OneInchEye** and **StarlightEye** preinstalled.
