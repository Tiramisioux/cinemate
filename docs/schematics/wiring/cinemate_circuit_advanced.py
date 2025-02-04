from skidl import *
import os

# Load backup library to avoid missing component errors
load_backup_lib()  

# Manually define Raspberry Pi 40-pin connector
rpi = Part("backup", "J", value="RaspberryPi_40Pin", footprint="Connector_Generic:Conn_02x20", dest=TEMPLATE)

# Manually define 40 GPIO Pins
rpi.pins = [Pin(num=i, name=f"GPIO{i}", func=Pin.BIDIR) for i in range(1, 41)]
                                                                     
# Example component connection
button_rec = Part("backup", "SW_Push")
rpi.pins[4] += button_rec[1]  # Connect button to GPIO4
button_rec[2] += rpi.pins[39]  # Connect to Ground

# Generate netlist


# Define Buttons
buttons = {
    "rec": Part('backup', 'SW_Push', footprint='Button'),
    "iso_inc": Part('backup', 'SW_Push', footprint='Button'),
    "iso_dec": Part('backup', 'SW_Push', footprint='Button'),
    "fps_toggle": Part('backup', 'SW_Push', footprint='Button'),
    "system": Part('backup', 'SW_Push', footprint='Button')
}

# Define Rotary Encoders
encoders = {
    "iso": Part('backup', 'RotaryEncoder', footprint='RotaryEncoder'),
    "shutter": Part('backup', 'RotaryEncoder', footprint='RotaryEncoder'),
    "fps": Part('backup', 'RotaryEncoder', footprint='RotaryEncoder')
}

# Define Potentiometers (Analog Controls)
pot_iso = Part('backup', 'R_Potentiometer', footprint='Potentiometer', value="10k")
pot_shutter = Part('backup', 'R_Potentiometer', footprint='Potentiometer', value="10k")
pot_fps = Part('backup', 'R_Potentiometer', footprint='Potentiometer', value="10k")

# Define Switches
switches = {
    "shutter_lock": Part('backup', 'SW_SPST', footprint='Switch'),
    "shutter_sync": Part('backup', 'SW_SPST', footprint='Switch'),
    "pwm_toggle": Part('backup', 'SW_SPST', footprint='Switch')
}

# Define LED and Resistor
led_rec = Part('backup', 'LED', footprint='LED')
resistor = Part('backup', 'R', value='220', footprint='Resistor')

# Connect Buttons to GPIOs
rpi[4] += buttons["rec"][1]
buttons["rec"][2] += rpi[39]

rpi[17] += buttons["iso_inc"][1]
buttons["iso_inc"][2] += rpi[39]

rpi[14] += buttons["iso_dec"][1]
buttons["iso_dec"][2] += rpi[39]

rpi[12] += buttons["fps_toggle"][1]
buttons["fps_toggle"][2] += rpi[39]

rpi[26] += buttons["system"][1]
buttons["system"][2] += rpi[39]

# Connect Rotary Encoders
rpi[9] += encoders["iso"][1]
rpi[11] += encoders["iso"][2]

rpi[23] += encoders["shutter"][1]
rpi[25] += encoders["shutter"][2]

rpi[7] += encoders["fps"][1]
rpi[8] += encoders["fps"][2]

# Connect Potentiometers for Analog Control
rpi[1] += pot_iso[1]
rpi[2] += pot_shutter[1]
rpi[3] += pot_fps[1]

# Connect Switches
rpi[24] += switches["shutter_lock"][1]
rpi[16] += switches["shutter_sync"][1]
rpi[22] += switches["pwm_toggle"][1]

# Connect Rec Light LED
rpi[6] += led_rec[1]
led_rec[2] += resistor[1]
resistor[2] += rpi[39]

# Generate netlist
generate_netlist()
