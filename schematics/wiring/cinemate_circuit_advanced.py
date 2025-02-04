from skidl import *

# Define Raspberry Pi as a 40-pin connector
rpi = Part('Connector', 'Conn_02x20_Odd_Even', footprint='Connector_Generic:Conn_02x20_Odd_Even')

# Define Buttons
buttons = {
    "rec": Part('Device', 'SW_Push', footprint='Button'),
    "iso_inc": Part('Device', 'SW_Push', footprint='Button'),
    "iso_dec": Part('Device', 'SW_Push', footprint='Button'),
    "fps_toggle": Part('Device', 'SW_Push', footprint='Button'),
    "system": Part('Device', 'SW_Push', footprint='Button')
}

# Define Rotary Encoders
encoders = {
    "iso": Part('Device', 'RotaryEncoder', footprint='RotaryEncoder'),
    "shutter": Part('Device', 'RotaryEncoder', footprint='RotaryEncoder'),
    "fps": Part('Device', 'RotaryEncoder', footprint='RotaryEncoder')
}

# Define Potentiometers (Analog Controls)
pot_iso = Part('Device', 'R_Potentiometer', footprint='Potentiometer', value="10k")
pot_shutter = Part('Device', 'R_Potentiometer', footprint='Potentiometer', value="10k")
pot_fps = Part('Device', 'R_Potentiometer', footprint='Potentiometer', value="10k")

# Define Switches
switches = {
    "shutter_lock": Part('Device', 'SW_SPST', footprint='Switch'),
    "shutter_sync": Part('Device', 'SW_SPST', footprint='Switch'),
    "pwm_toggle": Part('Device', 'SW_SPST
