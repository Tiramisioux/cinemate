#!/usr/bin/env python3
import smbus
import RPi.GPIO as GPIO
import time
import os
import subprocess
import sys

i2c_ch = 1
i2c_address = 0x34
bus = smbus.SMBus(i2c_ch)

mounted = 0
device_node = None

def readButtons():
    while 1:
        data = bus.read_byte(i2c_address)
        if data != 0x69:
            break
        time.sleep(0.1)
    eject_button = (data & 0x02 == 0x02)
    insert_button = (data & 0x01 == 0x01)
    return (insert_button, eject_button)

def writeLED(state):
    bus.write_byte(i2c_address, 0x01 if state else 0x00)

def check_for_device(device_name):
    try:
        output = subprocess.check_output("lspci -mm", shell=True, text=True)
        for line in output.split('\n'):
            if device_name in line:
                return "0000:" + line.split()[0] if len(line.split()[0]) <= 7 else line.split()[0]
        return None
    except subprocess.CalledProcessError:
        return None

def get_fs_type(device_path):
    try:
        return subprocess.check_output(["blkid", "-s", "TYPE", "-o", "value", device_path], text=True).strip()
    except:
        return None

def mount_last_partition(device_node):
    partitions = sorted(x for x in os.listdir("/dev/") if x.startswith(f"nvme{device_node[-1]}n1p"))
    if not partitions:
        print("No partitions found.")
        return
    device_path = f"/dev/{partitions[-1]}"
    mount_path = "/media/RAW"
    fs_type = get_fs_type(device_path)
    if not fs_type:
        print("Unknown filesystem.")
        return
    os.system(f"mkdir -p {mount_path}")
    print(f"Mounting {device_path} as {fs_type}...")
    if fs_type == "ntfs":
        os.system(f"mount -t ntfs3 -o uid=1000,gid=1000 {device_path} {mount_path}")
    elif fs_type == "ext4":
        os.system(f"mount -t ext4 {device_path} {mount_path}")
    elif fs_type == "exfat":
        os.system(f"mount -t exfat -o uid=1000,gid=1000 {device_path} {mount_path}")
    else:
        print("Unsupported fs.")
        return
    print(f"Mounted at {mount_path}")

def unmountPCIe():
    global mounted
    global device_node
    print("Unmounting PCIe device")

    try:
        os.system("sudo umount /media/RAW")
    except Exception as e:
        print(f"[WARN] Unmount failed: {e}")

    print("Trying to unbind PCIe controller...")
    try:
        os.system("sudo bash -c 'echo 1000110000.pcie > /sys/bus/platform/drivers/brcm-pcie/unbind'")
        time.sleep(0.5)
    except Exception as e:
        print(f"[ERROR] Failed to unbind PCIe controller: {e}")

    still_present = any(x.startswith("nvme") for x in os.listdir("/dev"))
    if still_present:
        print("[WARN] NVMe still present in /dev after unbind.")
    else:
        print("[INFO] NVMe device successfully removed.")

    writeLED(False)
    mounted = 0
    device_node = None

def mountPCIe():
    global mounted, device_node
    print("Mounting...")
    time.sleep(0.5)
    if os.path.exists('/sys/devices/platform/axi/1000110000.pcie/driver'):
        os.system("echo 1 > /sys/bus/pci/rescan")
    else:
        os.system("echo 1000110000.pcie > /sys/bus/platform/drivers/brcm-pcie/bind")
    time.sleep(0.5)
    device_node = check_for_device("Non-Volatile memory controller")
    if device_node:
        mount_last_partition(device_node)
        writeLED(True)
        mounted = 1

def main_loop():
    global last_insert, last_eject
    last_insert, last_eject = 0, 0
    insert, eject = readButtons()
    if insert == 0 and mounted == 0:
        mountPCIe()
    last_insert, last_eject = insert, eject

    try:
        while True:
            insert, eject = readButtons()
            if last_insert == 1 and insert == 0 and mounted == 0:
                mountPCIe()
            if last_eject == 1 and eject == 0:
                unmountPCIe()
            last_insert, last_eject = insert, eject
            time.sleep(0.1)
    finally:
        pass

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "mount":
            mountPCIe()
        elif sys.argv[1] == "unmount":
            unmountPCIe()
        else:
            print("Usage: script.py [mount|unmount]")
    else:
        main_loop()
