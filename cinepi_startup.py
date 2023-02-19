import subprocess

# List of commands to run
commands = [
    ['python3', '/home/pi/cinemate2/manual_controls.py'],
    ['python3', '/home/pi/cinemate2/simple_gui.py'],
    ['cinepi-raw']
]

# Start each command in a separate process
for cmd in commands:
    subprocess.Popen(cmd)