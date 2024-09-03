#!/bin/bash

exec >> /tmp/auto-mount.log 2>&1
echo "Script started at $(date)"
echo "ACTION: $1, DEVBASE: $2"

ACTION=$1
DEVBASE=$2
DEVICE="/dev/${DEVBASE}"

# Check if the device exists
if [ ! -b "$DEVICE" ]; then
    echo "Device $DEVICE does not exist."
    exit 1
fi

MOUNT_POINT="/media/RAW"
LABEL=$(lsblk -no LABEL $DEVICE)

if [[ ${ACTION} == "add" ]]; then
    if [[ ${LABEL} != "RAW" ]]; then
        echo "Device $DEVICE is not labeled RAW. Ignoring."
        exit 0
    fi

    # Check if already mounted
    if findmnt -rno SOURCE,TARGET | grep -q "^$DEVICE $MOUNT_POINT"; then
        echo "$DEVICE is already mounted at $MOUNT_POINT"
        exit 0
    fi

    # Mount the device
    echo "Attempting to mount $DEVICE"
    udisksctl mount -b $DEVICE
    if [ $? -eq 0 ]; then
        echo "Successfully mounted $DEVICE"
    else
        echo "Failed to mount $DEVICE"
    fi

elif [[ ${ACTION} == "remove" ]]; then
    # Unmount the device
    echo "Attempting to unmount $DEVICE"
    udisksctl unmount -b $DEVICE
    if [ $? -eq 0 ]; then
        echo "Successfully unmounted $DEVICE"
    else
        echo "Failed to unmount $DEVICE"
    fi
fi