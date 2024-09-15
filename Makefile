# Makefile for Cinemate Service

# Variables
SERVICE_NAME = cinemate
SERVICE_FILE = $(SERVICE_NAME).service
SERVICE_PATH = /etc/systemd/system/$(SERVICE_FILE)

# Phony targets
.PHONY: all install uninstall start stop restart status

# Default target
all: install start

# Install the service
install:
	@echo "Installing $(SERVICE_NAME) service..."
	@sudo cp $(SERVICE_FILE) $(SERVICE_PATH)
	@sudo systemctl daemon-reload
	@sudo systemctl enable $(SERVICE_NAME)
	@echo "$(SERVICE_NAME) service installed successfully."

# Uninstall the service
uninstall:
	@echo "Uninstalling $(SERVICE_NAME) service..."
	@sudo systemctl stop $(SERVICE_NAME)
	@sudo systemctl disable $(SERVICE_NAME)
	@sudo rm -f $(SERVICE_PATH)
	@sudo systemctl daemon-reload
	@echo "$(SERVICE_NAME) service uninstalled successfully."

# Start the service
start:
	@echo "Starting $(SERVICE_NAME) service..."
	@sudo systemctl start $(SERVICE_NAME)
	@echo "$(SERVICE_NAME) service started."

# Stop the service
stop:
	@echo "Stopping $(SERVICE_NAME) service..."
	@sudo systemctl stop $(SERVICE_NAME)
	@echo "$(SERVICE_NAME) service stopped."

# Restart the service
restart:
	@echo "Restarting $(SERVICE_NAME) service..."
	@sudo systemctl restart $(SERVICE_NAME)
	@echo "$(SERVICE_NAME) service restarted."

# Check the status of the service
status:
	@echo "Checking status of $(SERVICE_NAME) service..."
	@sudo systemctl status $(SERVICE_NAME)

# Help target
help:
	@echo "Available targets:"
	@echo "  install   - Install and enable the service"
	@echo "  uninstall - Stop, disable, and remove the service"
	@echo "  start     - Start the service"
	@echo "  stop      - Stop the service"
	@echo "  restart   - Restart the service"
	@echo "  status    - Check the status of the service"
	@echo "  all       - Install and start the service (default)"