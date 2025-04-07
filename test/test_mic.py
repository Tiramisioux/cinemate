import subprocess
import re
import time
import logging

logging.basicConfig(level=logging.INFO)

def detect_device():
    output = subprocess.check_output(['arecord', '-l']).decode()
    match = re.search(r'card (\d+):\s+[^\[]+\[([^\]]+)\].*?device (\d+):', output, re.DOTALL)
    if match:
        card = match.group(1)
        name = match.group(2)
        device = match.group(3)
        logging.info(f"Found device: card {card}, device {device} — {name}")
        return card, device, name
    return None, None, None

def try_format(card, device, fmt, channels, rate):
    try:
        cmd = ['arecord', '-D', f'hw:{card},{device}', '--format', fmt, '--channels', str(channels), '--rate', str(rate), '-d', '1', '-f', fmt, '-t', 'raw']
        subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def find_working_config(card, device):
    test_configs = [
        ("S24_3LE", 2, 48000),
        ("S16_LE", 2, 48000),
        ("S16_LE", 1, 48000),
        ("S16_LE", 1, 44100),
    ]
    for fmt, ch, rate in test_configs:
        if try_format(card, device, fmt, ch, rate):
            logging.info(f"✔ Found working config: format={fmt}, channels={ch}, rate={rate}")
            return fmt, ch, rate
    return None, None, None

def monitor_vu(card, device, fmt, channels, rate):
    cmd = [
        'arecord',
        '-D', f'hw:{card},{device}',
        '--format', fmt,
        '--channels', str(channels),
        '--rate', str(rate),
        '-V', 'stereo',
        '-f', fmt,
        '-t', 'raw'
    ]

    logging.info(f"Running: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1)

    try:
        for line in proc.stderr:
            line = line.strip()
            vu = re.findall(r'(\d+)%', line)
            if vu:
                left = vu[0]
                right = vu[1] if len(vu) > 1 else left
                print(f"VU: L={left}% R={right}%", end='\r', flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        proc.terminate()
        proc.wait()

if __name__ == '__main__':
    card, device, name = detect_device()
    if card:
        fmt, channels, rate = find_working_config(card, device)
        if fmt:
            monitor_vu(card, device, fmt, channels, rate)
        else:
            logging.error("No valid audio format found for device.")
    else:
        logging.error("No USB microphone found.")
