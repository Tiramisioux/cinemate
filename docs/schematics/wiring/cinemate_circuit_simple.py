from skidl import *
from custom_lib import rpi_header

# Load backup library
load_backup_lib()

# Define power and ground
vcc, gnd = Net("VCC"), Net("GND")

# Use the custom-defined Raspberry Pi header
rpi = rpi_header()

# Define a push button
button = Part("SKiDL", "SW_Push")

# Connect button to GPIO4 and GND
rpi[4] += button[1]
button[2] += gnd

# Connect power and ground
rpi[2] += vcc  # Pin 2 is 5V
rpi[6] += gnd  # Pin 6 is GND

# Generate netlist
generate_netlist(file_="docs/schematics/wiring/cinemate_circuit_simple.net")
