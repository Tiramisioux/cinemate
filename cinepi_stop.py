import subprocess

# Get the process IDs of the running programs
pids = []
for line in subprocess.check_output(["pgrep", "-f", "manual_controls.py|simple_gui.py|cinepi-raw"]).splitlines():
    pids.append(int(line))

# Terminate the programs
for pid in pids:
    subprocess.call(["sudo", "kill", str(pid)])
