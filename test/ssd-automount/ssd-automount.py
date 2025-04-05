#!/home/pi/.cinemate-env/bin/python3

import os
import time
import subprocess
import pyudev
import re

MOUNT_PATH = "/media/RAW"

def get_filesystem_type(device_path):
    try:
        result = subprocess.check_output(["blkid", "-s", "TYPE", "-o", "value", device_path], text=True).strip()
        return result
    except:
        return None

def get_label(device_path):
    try:
        result = subprocess.check_output(["blkid", "-s", "LABEL", "-o", "value", device_path], text=True).strip()
        return result
    except:
        return None

def is_ssd(device_path):
    # Check if the device path matches the pattern for SSDs (sda*)
    return bool(re.match(r'/dev/sd[a-z]\d*', device_path))

def mount_device(device_path):
    if not is_ssd(device_path):
        print(f"Device {device_path} is not an SSD. Skipping.")
        return

    fs_type = get_filesystem_type(device_path)
    label = get_label(device_path)

    if label != "RAW":
        print(f"Device {device_path} is not labeled RAW. Skipping.")
        return

    if not fs_type:
        print(f"Could not determine the filesystem type of {device_path}.")
        return

    if fs_type not in ["ntfs", "ext4"]:
        print(f"Unsupported filesystem type {fs_type} for {device_path}.")
        return

    os.makedirs(MOUNT_PATH, exist_ok=True)

    if fs_type == "ntfs":
        mount_cmd = f"mount -t ntfs3 -o uid=1000,gid=1000 {device_path} {MOUNT_PATH}"
    elif fs_type == "ext4":
        mount_cmd = f"mount -t ext4 {device_path} {MOUNT_PATH}"

    try:
        subprocess.run(mount_cmd, shell=True, check=True)
        print(f"SSD {device_path} has been mounted at {MOUNT_PATH}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to mount SSD {device_path}: {e}")

def unmount_device():
    try:
        subprocess.run(f"umount {MOUNT_PATH}", shell=True, check=True)
        print(f"Device has been unmounted from {MOUNT_PATH}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to unmount from {MOUNT_PATH}: {e}")

def main():
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem='block', device_type='partition')

    print("SSD Auto-mount service is running. Waiting for RAW-labeled SSD device events...")

    for device in iter(monitor.poll, None):
        if device.action == 'add':
            print(f"New device detected: {device.device_node}")
            mount_device(device.device_node)
        elif device.action == 'remove':
            if is_ssd(device.device_node):
                print(f"SSD removed: {device.device_node}")
                unmount_device()

if __name__ == "__main__":
    main()