# Overclocking the Pi

Raise the Raspberry Pi 5 RP1 image-pipeline clock to unlock higher imx585 ClearHDR frame rates. **Pi 5 and CM5 only** — the RP1 southbridge does not exist on the Pi 4 family, so none of this applies there.

!!! warning "Pi 5 / CM5 only"
    Do not apply these steps on a Pi 4 / 400 / CM4. The device-tree overlay
    targets the RP1 (`brcm,bcm2712`) and the libcamera change assumes the PiSP
    (Pi 5) pipeline. Everything the installer does here is gated on that same
    `bcm2712` check, so a Pi 4 install simply skips it.

`cinemate-install.sh` does all of this automatically on a Pi 5 / CM5. You do not need the manual steps at the end of this page unless you are building the stack by hand:

The overclock ships **installed but off**. Use the **Boot config** pane of the settings editor at `http://cinepi.local:5000/settings-editor`. The **RP1 overclock** toggle comments and uncomments the overlay line for you.

!!! warning "Both directions need a reboot"
    The RP1 clock is set from the device tree at boot, so you will have to reboot to see the changes.