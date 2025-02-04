from skidl import *

# Define Components
rpi = Part('RaspberryPi', 'Raspberry_Pi_4B', footprint='RaspberryPi_40Pin')

# Buttons
buttons = {
    "rec": Part('Device', 'SW_Push', footprint='Button'),
    "iso_inc": Part('Device', 'SW_Push', footprint='Button'),
    "iso_dec": Part('Device', 'SW_Push', footprint='Button'),
    "fps_toggle": Part('Device', 'SW_Push', footprint='Button'),
    "system": Part('Device', 'SW_Push', footprint='Button')
}

# Rotary Encoders
encoders = {
    "iso": Part('Device', 'RotaryEncoder', footprint='RotaryEncoder'),
    "shutter": Part('Device', 'RotaryEncoder', footprint='RotaryEncoder'),
    "fps": Part('Device', 'RotaryEncoder', footprint='RotaryEncoder')
}

# Potentiometers (Analog Controls via Grove Base HAT)
pot_iso = Part('Device', 'R_Potentiometer', footprint='Potentiometer', value="10k")
pot_shutter = Part('Device', 'R_Potentiometer', footprint='Potentiometer', value="10k")
pot_fps = Part('Device', 'R_Potentiometer', footprint='Potentiometer', value="10k")

# Switches
switches = {
    "shutter_lock": Part('Device', 'SW_SPST', footprint='Switch'),
    "shutter_sync": Part('Device', 'SW_SPST', footprint='Switch'),
    "pwm_toggle": Part('Device', 'SW_SPST', footprint='Switch')
}

# LED Indicator
led_rec = Part('Device', 'LED', footprint='LED')
resistor = Part('Device', 'R', value='220', footprint='Resistor')

# Button Connections
rpi['GPIO4'] += buttons["rec"][1]  # Rec button
buttons["rec"][2] += rpi['GND']

rpi['GPIO17'] += buttons["iso_inc"][1]  # Increase ISO
buttons["iso_inc"][2] += rpi['GND']

rpi['GPIO14'] += buttons["iso_dec"][1]  # Decrease ISO
buttons["iso_dec"][2] += rpi['GND']

rpi['GPIO12'] += buttons["fps_toggle"][1]  # Toggle FPS
buttons["fps_toggle"][2] += rpi['GND']

rpi['GPIO26'] += buttons["system"][1]  # System Multi-Function
buttons["system"][2] += rpi['GND']

# Rotary Encoder Connections
rpi['GPIO9'] += encoders["iso"][1]
rpi['GPIO11'] += encoders["iso"][2]

rpi['GPIO23'] += encoders["shutter"][1]
rpi['GPIO25'] += encoders["shutter"][2]

rpi['GPIO7'] += encoders["fps"][1]
rpi['GPIO8'] += encoders["fps"][2]

# Potentiometers for Analog Control
rpi['A0'] += pot_iso[1]
rpi['A2'] += pot_shutter[1]
rpi['A4'] += pot_fps[1]

# Switches
rpi['GPIO24'] += switches["shutter_lock"][1]
switches["shutter_lock"][2] += rpi['GND']

rpi['GPIO16'] += switches["shutter_sync"][1]
switches["shutter_sync"][2] += rpi['GND']

rpi['GPIO22'] += switches["pwm_toggle"][1]
switches["pwm_toggle"][2] += rpi['GND']

# Rec Light LED
rpi['GPIO6'] += led_rec[1]
led_rec[2] += resistor[1]
resistor[2] += rpi['GND']

# Generate and save netlist
generate_netlist()
