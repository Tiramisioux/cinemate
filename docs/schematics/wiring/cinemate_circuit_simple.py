from skidl import *

# Define a 40-pin Raspberry Pi header as a subcircuit
@SubCircuit
def RaspberryPi40Pin():
    return [Pin(num=i, name=f"GPIO{i}", func=Pin.BIDIR) for i in range(1, 41)]

rpi_pins = RaspberryPi40Pin()



# Define Buttons
button_rec = Part('Device', 'SW_Push', footprint='Button')  # Start/Stop Recording
button_iso_inc = Part('Device', 'SW_Push', footprint='Button')  # Increase ISO
button_iso_dec = Part('Device', 'SW_Push', footprint='Button')  # Decrease ISO

# Define LED and Resistor for Recording Indicator
led_rec = Part('Device', 'LED', footprint='LED')
resistor = Part('Device', 'R', value='220', footprint='Resistor')

# Connect Buttons to GPIO Pins
rpi[4] += button_rec[1]
button_rec[2] += rpi[39]  # Connect to Ground

rpi[17] += button_iso_inc[1]
button_iso_inc[2] += rpi[39]  # Connect to Ground

rpi[14] += button_iso_dec[1]
button_iso_dec[2] += rpi[39]  # Connect to Ground

# Connect Rec Light LED
rpi[6] += led_rec[1]
led_rec[2] += resistor[1]
resistor[2] += rpi[39]  # Connect to Ground

# Generate netlist
generate_netlist()
