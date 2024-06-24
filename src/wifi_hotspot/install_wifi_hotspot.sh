#!/bin/bash

SERVICE_FILE=wifi_hotspot.service
SERVICE_SOURCE_PATH=/home/pi/cinemate/services/$SERVICE_FILE
SERVICE_DEST_PATH=/etc/systemd/system/

# Copy the service file to the systemd directory
sudo cp $SERVICE_SOURCE_PATH $SERVICE_DEST_PATH

# Enable the service
sudo systemctl enable $SERVICE_FILE

# Reload the systemd daemon
sudo systemctl daemon-reload

# Start the service
sudo systemctl start $SERVICE_FILE

# Check the status of the service
sudo systemctl status $SERVICE_FILE
