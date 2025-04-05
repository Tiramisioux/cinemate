import pyudev
import subprocess
import os

def get_device_info(devname):
    try:
        result = subprocess.run(
            ['lsblk', '-no', 'LABEL,FSTYPE,MOUNTPOINT', f'/dev/{devname}'],
            stdout=subprocess.PIPE, check=True, text=True
        )
        lines = result.stdout.strip().split('\n')
        if len(lines) >= 1:
            label, fstype, mountpoint = (lines[0].strip().split() + [None, None])[:3]
            return {
                'label': label or '(no label)',
                'fstype': fstype or '(unknown)',
                'mountpoint': mountpoint or '(not mounted)'
            }
    except Exception as e:
        return {'label': '(error)', 'fstype': '(error)', 'mountpoint': '(error)'}
    return None

def handle_event(action, device):
    if device.device_type != 'partition':
        return

    devname = os.path.basename(device.device_node)
    info = get_device_info(devname)

    if action == 'add':
        print(f"[+] /dev/{devname} connected")
        print(f"    Label: {info['label']}, FS: {info['fstype']}, Mount: {info['mountpoint']}")
    elif action == 'remove':
        print(f"[-] /dev/{devname} removed")

def monitor_devices():
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by('block')

    print("🔍 Monitoring device events... (press Ctrl+C to exit)")
    for device in iter(monitor.poll, None):
        handle_event(device.action, device)

if __name__ == "__main__":
    monitor_devices()
