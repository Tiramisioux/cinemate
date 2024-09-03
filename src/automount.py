import smbus
import RPi.GPIO as GPIO
import time
import os
import psutil
import subprocess
import re



i2c_ch = 1
i2c_address = 0x34
bus = smbus.SMBus(i2c_ch)


mounted = 0
lastReadCount = 0
lastWriteCount = 0

device_node = None

def readButtons():
    while 1:
        data = bus.read_byte(i2c_address)
        if data != 0x69:
            break
        time.sleep(0.1)
    eject_button = (data & 0x02 == 0x02)
    insert_button = (data & 0x01 == 0x01)
    return (insert_button,eject_button)


def writeLED(data):
    bus.write_byte(i2c_address,data)

def check_for_device(device_name):
    try:
        # Run the shell command and get the output
        output = subprocess.check_output("lspci -mm", shell=True, text=True)

        # Split the output into lines
        lines = output.split('\n')

        # Iterate over each line
        for line in lines:
            # If "BCM2711 PCIe Bridge" is found in the line
            if device_name in line:
                # Extract the PCI tree node number using regular expressions
                
                if len(line.split(" ")[0]) <= 7:
                    device_name = "0000:" + line.split(" ")[0]
                else:
                    device_name = line.split(" ")[0]                    
                return device_name
        # If not found, return None
        return None
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running the lspci command: {str(e)}")
        return None  # Return None if an error occurred

def get_filesystem_type(device_path):
    try:
        # Using blkid to determine the filesystem type
        result = subprocess.check_output(["sudo", "blkid", "-s", "TYPE", "-o", "value", device_path], text=True).strip()
        return result
    except:
        return None

def mount_last_partition(device_node):
    # List all partitions for the given device and get the last partition number
    partitions = sorted([x for x in os.listdir(f"/dev/") if x.startswith(f"nvme{device_node[-1]}n1p")])
    last_partition = partitions[-1] if partitions else None

    if not last_partition:
        print(f"No partitions found for device {device_node}.")
        return

    device_path = f"/dev/{last_partition}"
    mount_path = "/media/RAW"

    fs_type = get_filesystem_type(device_path)

    if not fs_type:
        print(f"Could not determine the filesystem type of {device_path}.")
        return

    os.system(f"sudo mkdir -p {mount_path}")  # Create mount point with sudo

    print(f"NVMe device {device_node} found, attempting to mount partition {device_path}...")
    
    if fs_type == "ntfs":
        os.system(f"sudo mount -t ntfs3 -o uid=1000,gid=1000 {device_path} {mount_path}")
    elif fs_type == "ext4":
        os.system(f"sudo mount -t ext4 {device_path} {mount_path}")
    elif fs_type == "exfat":
        os.system(f"sudo mount -t exfat -o uid=1000,gid=1000 {device_path} {mount_path}")
    else:
        print(f"Unsupported filesystem type {fs_type}.")
        return

    print(f"NVMe device {device_node} partition {device_path} has been mounted at {mount_path}")


def unmountPCIe():
    global mounted
    global device_node
    print("Unmounting PCIe device")
    try:
        os.system("sudo bash -c 'umount /media/RAW'")
    except:
        pass
    NVMe_port = check_for_device("Non-Volatile memory controller")
    print("NVMe Device found:%s" % NVMe_port)
    if NVMe_port != None:
        os.system("sudo bash -c 'echo 1 >/sys/bus/pci/devices/"+NVMe_port+"/remove'") #os.system("sudo bash -c 'echo fd500000.pcie > /sys/bus/platform/drivers/brcm-pcie/unbind'")
    writeLED(False)
    mounted = 0
    device_node = None

def mountPCIe():
    global mounted
    global device_node
    print("Mounting PCIe device")
    time.sleep(0.5)
    if os.path.exists('/sys/devices/platform/axi/1000110000.pcie/driver'):
        print("1000110000.pcie driver exists, try rescan")
        os.system("sudo bash -c 'echo 1 >/sys/bus/pci/rescan'")
    else:
        print("1000110000.pcie driver has not loaded, binding the driver")
        os.system("sudo bash -c 'echo 1000110000.pcie > /sys/bus/platform/drivers/brcm-pcie/bind'")
    
    time.sleep(0.5)
    # Check if the device is mounted
    device_node = check_for_device("Non-Volatile memory controller")

    # Mount the NVMe drive if it's found
    if device_node:
        mount_last_partition(device_node)
        writeLED(True)
        mounted = 1

last_insert_button = 0
last_eject_button = 0

(insert_button,eject_button) = readButtons()
if insert_button == 0 and mounted == 0:
    mountPCIe()
last_insert_button = insert_button
last_eject_button = eject_button

try:
    while True:
        (insert_button,eject_button) = readButtons()
        #print((insert_button,eject_button),(last_insert_button,last_eject_button))
        if last_insert_button == 1 and insert_button == 0 and mounted == 0:
            mountPCIe()
        if last_eject_button == 1 and eject_button == 0:
            unmountPCIe()
        (last_insert_button,last_eject_button) = (insert_button,eject_button)
        time.sleep(0.1)

finally:
    pass
