from skidl import *

# Create a Raspberry Pi 40-Pin Header using SKiDL, NO KiCad library needed!
class RaspberryPi40Pin(SubCircuit):
    def __init__(self):
        super().__init__("RaspberryPi_40Pin")
        self.pins = [Pin(num=i, name=f"GPIO{i}", func=Pin.BIDIR) for i in range(1, 41)]

# Create RPi as a SubCircuit
rpi = RaspberryPi40Pin()

# Define Buttons
buttons = {
    "rec": Part('Device', 'SW_Push'),
    "iso_inc": Part('Device', 'SW_Push'),
    "iso_dec": Part('Device', 'SW_Push'),
    "fps_toggle": Part('Device', 'SW_Push'),
    "system": Part('Device', 'SW_Push')
}

# Define Rotary Encoders
encoders = {
    "iso": Part('Device', 'RotaryEncoder'),
    "shutter": Part('Device', 'RotaryEncoder'),
    "fps": Part('Device', 'RotaryEncoder')
}

# Define Potentiometers (Analog Controls)
pot_iso = Part('Device', 'R_Potentiometer', value="10k")
pot_shutter = Part('Device', 'R_Potentiometer', value="10k")
pot_fps = Part('Device', 'R_Potentiometer', value="10k")

# Define Switches
switches = {
    "shutter_lock": Part('Device', 'SW_SPST'),
    "shutter_sync": Part('Device', 'SW_SPST'),
    "pwm_toggle": Part('Device', 'SW_SPST')
}

# Define LED and Resistor
led_rec = Part('Device', 'LED')
resistor = Part('Device', 'R', value='220')

# Connect Buttons to GPIOs
rpi.pins[3] += buttons["rec"][1]
buttons["rec"][2] += rpi.pins[39]

rpi.pins[5] += buttons["iso_inc"][1]
buttons["iso_inc"][2] += rpi.pins[39]

rpi.pins[7] += buttons["iso_dec"][1]
buttons["iso_dec"][2] += rpi.pins[39]

rpi.pins[11] += buttons["fps_toggle"][1]
buttons["fps_toggle"][2] += rpi.pins[39]

rpi.pins[13] += buttons["system"][1]
buttons["system"][2] += rpi.pins[39]

# Connect Rotary Encoders
rpi.pins[15] += encoders["iso"][1]
rpi.pins[16] += encoders["iso"][2]

rpi.pins[18] += encoders["shutter"][1]
rpi.pins[19] += encoders["shutter"][2]

rpi.pins[21] += encoders["fps"][1]
rpi.pins[22] += encoders["fps"][2]

# Connect Potentiometers for Analog Control
rpi.pins[23] += pot_iso[1]
rpi.pins[24] += pot_shutter[1]
rpi.pins[26] += pot_fps[1]

# Connect Switches
rpi.pins[29] += switches["shutter_lock"][1]
rpi.pins[31] += switches["shutter_sync"][1]
rpi.pins[33] += switches["pwm_toggle"][1]

# Connect Rec Light LED
rpi.pins[8] += led_rec[1]
led_rec[2] += resistor[1]
resistor[2] += rpi.pins[39]

# Generate netlist
generate_netlist()
