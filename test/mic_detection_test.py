import subprocess
import re
import sys

def get_connected_mic():
    output = subprocess.check_output("arecord -l", shell=True).decode()
    if "RØDE VideoMic NTG" in output:
        return "mic_24bit", "S24_3LE", 2, 48000
    elif "Generic USB Mic" in output:
        return "mic_16bit", "S16_LE", 1, 48000
    else:
        return None

def parse_vu(line):
    match = re.search(r'(\d+)%', line)
    return int(match.group(1)) if match else None

def vu_meter_only():
    mic_info = get_connected_mic()
    if not mic_info:
        print("No recognized mic connected.")
        sys.exit(1)

    device, fmt, channels, rate = mic_info
    print(f"Using {device} ({fmt}, {channels} channel(s), {rate} Hz)")
    print("VU meter running. Press Ctrl+C to stop.\n")

    cmd = [
        'arecord', '-D', device,
        '-f', fmt,
        '-c', str(channels),
        '-r', str(rate),
        '-vvv',
        '/dev/null'
    ]

    process = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        universal_newlines=True
    )

    try:
        for line in process.stderr:
            vu_level = parse_vu(line)
            if vu_level is not None:
                print(f"\rVU Level: {vu_level:3d}%", end='', flush=True)
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        print("\nStopped.")

if __name__ == '__main__':
    vu_meter_only()
