from skidl import *

# Create a Raspberry Pi 40-Pin Header using SKiDL, NO KiCad library needed!
class RaspberryPi40Pin(SubCircuit):
    def __init__(self):
        super().__init__("RaspberryPi_40Pin")
        self.pins = [Pin(num=i, name=f"GPIO{i}", func=Pin.BIDIR) for i in range(1, 41)]

# Create RPi as a SubCircuit
rpi = RaspberryPi40Pin()

# Define Components
button_rec = Part('Device', 'SW_Push')  # Start/Stop Recording
button_iso_inc = Part('Device', 'SW_Push')  # Increase ISO
button_iso_dec = Part('Device', 'SW_Push')  # Decrease ISO
led_rec = Part('Device', 'LED')
resistor = Part('Device', 'R', value='220')

# Connect Buttons to GPIO Pins
rpi.pins[3] += button_rec[1]   # GPIO3 (Physical Pin 5)
button_rec[2] += rpi.pins[39]  # Connect to Ground

rpi.pins[5] += button_iso_inc[1]  # GPIO5 (Physical Pin 7)
button_iso_inc[2] += rpi.pins[39]

rpi.pins[7] += button_iso_dec[1]  # GPIO7 (Physical Pin 26)
button_iso_dec[2] += rpi.pins[39]

# Connect Rec Light LED
rpi.pins[8] += led_rec[1]  # GPIO8 (Physical Pin 24)
led_rec[2] += resistor[1]
resistor[2] += rpi.pins[39]

# Generate netlist
generate_netlist()
