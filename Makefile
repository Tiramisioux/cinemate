# -------------------------------------------------------------------
# Systemd service – cinemate-autostart
# -------------------------------------------------------------------
SERVICE_NAME        := cinemate-autostart

# where systemd expects it
SYSTEMD_DIR         := /etc/systemd/system
SERVICE_FILE_PATH   := $(SYSTEMD_DIR)/$(SERVICE_NAME).service

# where the service file lives inside the repo
SERVICE_DIR         := services/$(SERVICE_NAME)
LOCAL_SERVICE_FILE  := $(SERVICE_DIR)/$(SERVICE_NAME).service

.PHONY: all install enable disable start stop restart status clean help

# -------------------------------------------------------------------
# Default target
# -------------------------------------------------------------------
all: help

# -------------------------------------------------------------------
# Install / update the service file
# -------------------------------------------------------------------
install:
	cd src/module/app && npm ci
	sudo install -m 644 $(LOCAL_SERVICE_FILE) $(SERVICE_FILE_PATH)
	sudo systemctl daemon-reload
	@echo "Installed $(SERVICE_FILE_PATH)"

# -------------------------------------------------------------------
# Enable / disable (boot autostart)
# -------------------------------------------------------------------
enable: install
	sudo systemctl enable  $(SERVICE_NAME)
	@echo "Enabled  $(SERVICE_NAME)"

disable:
	sudo systemctl disable $(SERVICE_NAME)
	@echo "Disabled $(SERVICE_NAME)"

# -------------------------------------------------------------------
# Runtime control
# -------------------------------------------------------------------
start:
	sudo systemctl start $(SERVICE_NAME)

stop:
	sudo systemctl stop $(SERVICE_NAME)

restart:
	sudo systemctl restart $(SERVICE_NAME)

status:
	sudo systemctl status $(SERVICE_NAME)

# -------------------------------------------------------------------
# Remove everything
# -------------------------------------------------------------------
clean:
	- sudo systemctl stop    $(SERVICE_NAME)
	- sudo systemctl disable $(SERVICE_NAME)
	- sudo rm -f             $(SERVICE_FILE_PATH)
	 sudo systemctl daemon-reload
	@echo "Removed $(SERVICE_NAME)"

# -------------------------------------------------------------------
# Quick help
# -------------------------------------------------------------------
help:
	@echo "cinemate-autostart Make targets:"
	@echo "  make install   – copy/update the service file"
	@echo "  make enable    – enable and (re)install"
	@echo "  make disable   – disable autostart"
	@echo "  make start     – start service now"
	@echo "  make stop      – stop service"
	@echo "  make restart   – restart service"
	@echo "  make status    – show status"
	@echo "  make clean     – stop, disable and remove service file"
