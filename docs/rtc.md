# Notes on RTC

Cinepi-raw names the clips according to system time. For clips to use the current time of day, an RTC (Realtime Clock Unit) can be installed.

To get the correct system time on the Pi, simply connect to a computer connected to the internet via SSH and the Pi will update its system time.

To check system time in the CineMate CLI:

    time

To write system time to a connected RTC in the CineMate CLI:

    set time

Now, if not connected to the internet, on startup the Pi will get its system time from the RTC.
