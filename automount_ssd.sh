#!/bin/bash

exec >> /tmp/auto-mount.log 2>&1
echo "Script started at $(date)"
echo "ACTION: $1, DEVBASE: $2"

ACTION=$1
DEVBASE=$2
DEVICE="/dev/${DEVBASE}"
MOUNT_POINT="/media/RAW"

if [ ! -b "$DEVICE" ]; then
    echo "Device $DEVICE does not exist."
    exit 1
fi

LABEL=$(lsblk -no LABEL $DEVICE)

if [[ ${ACTION} == "add" ]]; then
    if [[ ${LABEL} != "RAW" ]]; then
        echo "Device $DEVICE is not labeled RAW. Ignoring."
        exit 0
    fi

    if findmnt -rno SOURCE,TARGET | grep -q "^$DEVICE $MOUNT_POINT"; then
        echo "$DEVICE is already mounted at $MOUNT_POINT"
        exit 0
    fi

    echo "Creating mount point $MOUNT_POINT"
    sudo mkdir -p $MOUNT_POINT

    echo "Attempting to mount $DEVICE"
    if sudo mount $DEVICE $MOUNT_POINT; then
        echo "Successfully mounted $DEVICE at $MOUNT_POINT"
    else
        echo "Failed to mount $DEVICE"
        sudo rmdir $MOUNT_POINT
    fi

elif [[ ${ACTION} == "remove" ]]; then
    echo "Attempting to unmount $DEVICE"
    if sudo umount $MOUNT_POINT; then
        echo "Successfully unmounted $DEVICE"
        echo "Removing mount point $MOUNT_POINT"
        sudo rmdir $MOUNT_POINT
    else
        echo "Failed to unmount $DEVICE"
    fi
fi