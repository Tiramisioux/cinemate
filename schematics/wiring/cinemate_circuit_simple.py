from skidl import *

# Define Raspberry Pi as a generic 40-pin connector
rpi = Part('Connector', 'Conn_02x20_Odd_Even', footprint='Connector_Generic:Conn_02x20_Odd_Even')

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
