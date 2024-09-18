SERVICE_NAME := cinemate-autostart
SERVICE_FILE_PATH := /etc/systemd/system/$(SERVICE_NAME).service
LOCAL_SERVICE_FILE := ./services/$(SERVICE_NAME)/$(SERVICE_NAME).service

.PHONY: all install enable disable start stop restart status clean

# Default target
all: help

# Install the service file to systemd directory
install:
	sudo cp $(LOCAL_SERVICE_FILE) $(SERVICE_FILE_PATH)
	sudo systemctl daemon-reload
	@echo "Service installed to $(SERVICE_FILE_PATH)"

# Enable the service to start on boot
enable:
	sudo systemctl enable $(SERVICE_NAME)
	@echo "Service $(SERVICE_NAME) enabled"

# Disable the service
disable:
	sudo systemctl disable $(SERVICE_NAME)
	@echo "Service $(SERVICE_NAME) disabled"

# Start the service
start:
	sudo systemctl start $(SERVICE_NAME)
	@echo "Service $(SERVICE_NAME) started"

# Stop the service
stop:
	sudo systemctl stop $(SERVICE_NAME)
	@echo "Service $(SERVICE_NAME) stopped"

# Restart the service
restart:
	sudo systemctl restart $(SERVICE_NAME)
	@echo "Service $(SERVICE_NAME) restarted"

# Check the status of the service
status:
	sudo systemctl status $(SERVICE_NAME)

# Clean up: remove the service file from the systemd directory
clean:
	sudo systemctl stop $(SERVICE_NAME) || true
	sudo systemctl disable $(SERVICE_NAME) || true
	sudo rm -f $(SERVICE_FILE_PATH)
	sudo systemctl daemon-reload
	@echo "Service $(SERVICE_NAME) removed"

# Display help message
help:
	@echo "Makefile for managing the $(SERVICE_NAME) service"
	@echo ""
	@echo "Usage:"
	@echo "  make install    - Copy the service file to systemd directory"
	@echo "  make enable     - Enable the service to start on boot"
	@echo "  make disable    - Disable the service"
	@echo "  make start      - Start the service"
	@echo "  make stop       - Stop the service"
	@echo "  make restart    - Restart the service"
	@echo "  make status     - Show the status of the service"
	@echo "  make clean      - Stop, disable, and remove the service file"
