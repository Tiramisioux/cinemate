# i2c hardware
<!-- sidebar group `i2c-hardware` · tab: i2c -->

Edit the headings and the paragraphs. Leave the `<!-- key: ... -->` lines alone —
they are what the GUI looks each string up by when CineMate starts.

---

## i2c hardware
<!-- key: pane.i2cbus.0 -->

Optional peripherals on the camera's I²C bus.

---

## Real-time clock
<!-- key: pane.i2cbus.1 -->

The system clock sets itself whenever the camera can reach the internet. The RTC keeps whatever it was last given, so it only matches after you copy the time across.

### System time
<!-- key: card.i2cbus.0 -->

What the Pi believes the time is.

### RTC time
<!-- key: card.i2cbus.1 -->

What the attached clock chip believes the time is.

### Copy system time to the RTC
<!-- key: card.i2cbus.2 -->

Runs `hwclock --systohc` and reads the clock back to check it took.
