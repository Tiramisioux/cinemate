from skidl import *

# Define Components
rpi = Part('RaspberryPi', 'Raspberry_Pi_4B', footprint='RaspberryPi_40Pin')
button_rec = Part('Device', 'SW_Push', footprint='Button')
button_iso_inc = Part('Device', 'SW_Push', footprint='Button')
button_iso_dec = Part('Device', 'SW_Push', footprint='Button')
led_rec = Part('Device', 'LED', footprint='LED')
resistor = Part('Device', 'R', value='220', footprint='Resistor')

# Connect Buttons
rpi['GPIO4'] += button_rec[1]  # Rec button
button_rec[2] += rpi['GND']

rpi['GPIO17'] += button_iso_inc[1]  # Increase ISO button
button_iso_inc[2] += rpi['GND']

rpi['GPIO14'] += button_iso_dec[1]  # Decrease ISO button
button_iso_dec[2] += rpi['GND']

# Connect Rec Light LED
rpi['GPIO6'] += led_rec[1]
led_rec[2] += resistor[1]
resistor[2] += rpi['GND']

# Generate and save netlist
generate_netlist()
