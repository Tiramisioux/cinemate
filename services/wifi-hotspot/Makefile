# Makefile for wifi-hotspot
PREFIX  ?= /usr/local
SYSDDIR ?= /etc/systemd/system

SCRIPT  = wifi-hotspot.py
SERVICE = wifi-hotspot.service

.PHONY: all install enable disable start stop restart status clean uninstall

all:
	@echo "Nothing to build – use 'make install'"

install:
	install -m 755 $(SCRIPT)  $(PREFIX)/bin/$(SCRIPT)
	install -m 644 $(SERVICE) $(SYSDDIR)/$(SERVICE)
	systemctl daemon-reload

enable: install
	systemctl enable  $(SERVICE)
	systemctl start   $(SERVICE)

disable:
	- systemctl stop    $(SERVICE)
	- systemctl disable $(SERVICE)

start:
	systemctl start $(SERVICE)

stop:
	systemctl stop $(SERVICE)

restart:
	systemctl restart $(SERVICE)

status:
	systemctl status $(SERVICE)

clean: disable
	- rm -f $(PREFIX)/bin/$(SCRIPT)
	- rm -f $(SYSDDIR)/$(SERVICE)
	systemctl daemon-reload
	@echo "Removed $(SERVICE)"

uninstall: clean     # alias for convenience
