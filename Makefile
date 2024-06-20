SERVICE_FILE = cinemate.service
SERVICE_PATH = /etc/systemd/system/

.PHONY: install start stop uninstall status

install:
	@if grep -q "Raspberry Pi 4" /proc/device-tree/model; then \
		echo "Raspberry Pi 4 detected. Enabling and starting pigpiod..."; \
		sudo systemctl enable pigpiod; \
		sudo systemctl start pigpiod; \
	else \
		echo "Not a Raspberry Pi 4. Skipping pigpiod..."; \
	fi
	@sudo cp services/$(SERVICE_FILE) $(SERVICE_PATH)
	@sudo systemctl enable $(SERVICE_FILE)
	@sudo systemctl daemon-reload

start:
	@sudo systemctl start $(SERVICE_FILE)

stop:
	@sudo systemctl stop $(SERVICE_FILE)

uninstall:
	@sudo systemctl stop $(SERVICE_FILE)
	@sudo systemctl disable $(SERVICE_FILE)
	@sudo rm $(SERVICE_PATH)$(SERVICE_FILE)
	@sudo systemctl daemon-reload

status:
	@sudo systemctl status $(SERVICE_FILE)
