from skidl import *

# Define a Custom 40-Pin Header Instead of Relying on KiCad Libraries
rpi = Part('Device', 'J', value="RaspberryPi_40Pin", footprint='Connector_Generic:Conn_02x20')

# Manually Define 40 GPIO Pins for Raspberry Pi
rpi.pins = [Pin(num=i, name=f"GPIO{i}", func=Pin.BIDIR) for i in range(1, 41)]

# Define Buttons
button_rec = Part('Device', 'SW_Push', footprint='Button')

# Define LED and Resistor
led_rec = Part('Device', 'LED', footprint='LED')
resistor = Part('Device', 'R', value='220', footprint='Resistor')

# Connect Components
rpi[4] += button_rec[1]
button_rec[2] += rpi[39]  # Connect to Ground

rpi[6] += led_rec[1]
led_rec[2] += resistor[1]
resistor[2] += rpi[39]  # Connect to Ground

# Generate Netlist
generate_netlist()

