from skidl import *

# Define a custom 40-pin header manually
rpi = SubCircuit(name="RaspberryPi_40Pin")

# Manually define 40 GPIO Pins (Generic Header)
rpi.pins = [Pin(num=i, name=f"GPIO{i}", func=Pin.BIDIR) for i in range(1, 41)]

# Define Components
button_rec = Part('Device', 'SW_Push')  # Start/Stop Recording
button_iso_inc = Part('Device', 'SW_Push')  # Increase ISO
button_iso_dec = Part('Device', 'SW_Push')  # Decrease ISO
led_rec = Part('Device', 'LED')
resistor = Part('Device', 'R', value='220')

# Connect Buttons to GPIO Pins
rpi.pins[4] += button_rec[1]
button_rec[2] += rpi.pins[39]  # Connect to Ground

rpi.pins[17] += button_iso_inc[1]
button_iso_inc[2] += rpi.pins[39]  # Connect to Ground

rpi.pins[14] += button_iso_dec[1]
button_iso_dec[2] += rpi.pins[39]  # Connect to Ground

# Connect Rec Light LED
rpi.pins[6] += led_rec[1]
led_rec[2] += resistor[1]
resistor[2] += rpi.pins[39]  # Connect to Ground

# Generate netlist
generate_netlist()
