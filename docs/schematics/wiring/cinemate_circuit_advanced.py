from skidl import *

# Load backup library
load_backup_lib()

# Define power and ground
vcc, gnd = Net("VCC"), Net("GND")

# Create a Raspberry Pi 40-pin header
rpi = Part("SKiDL", "J", footprint="Connector_Generic:Conn_02x20")
rpi.ref = "RaspberryPi"

# Define a push button
button = Part("Device", "SW_Push")
button.ref = "BTN1"

# Define an LED with a 330Ω resistor
led = Part("Device", "LED")
led.ref = "LED1"
resistor = Part("Device", "R", value="330Ω")
resistor.ref = "R1"

# Connect button to GPIO4 and GND
gpio4 = rpi[4]  # Pin 4 is GPIO4
gpio4 += button[1]
button[2] += gnd

# Connect LED circuit (GPIO17 → Resistor → LED → GND)
gpio17 = rpi[11]  # Pin 11 is GPIO17
gpio17 += resistor[1]
resistor[2] += led[1]
led[2] += gnd

# Connect power and ground
rpi[2] += vcc  # Pin 2 is 5V
rpi[6] += gnd  # Pin 6 is GND

# Generate netlist for netlistsvg
generate_netlist(file_="docs/schematics/wiring/cinemate_circuit_advanced.net")
