# Makefile for redis-log-maintenance
PREFIX  ?= /usr/local
SYSDDIR ?= /etc/systemd/system

SCRIPT  = redis-log-maintenance.py
SERVICE = redis-log-maintenance.service
TIMER   = redis-log-maintenance.timer

.PHONY: all install enable disable start stop restart status clean uninstall

all:
	@echo "Nothing to build - use 'make install'"

install:
	install -m 755 $(SCRIPT)  $(PREFIX)/bin/$(SCRIPT)
	install -m 644 $(SERVICE) $(SYSDDIR)/$(SERVICE)
	install -m 644 $(TIMER)   $(SYSDDIR)/$(TIMER)
	systemctl daemon-reload

enable: install
	systemctl enable $(TIMER)
	systemctl start  $(TIMER)

disable:
	- systemctl stop    $(TIMER)
	- systemctl disable $(TIMER)
	- systemctl stop    $(SERVICE)

start:
	systemctl start $(SERVICE)

stop:
	- systemctl stop $(TIMER)
	- systemctl stop $(SERVICE)

restart:
	systemctl restart $(TIMER)
	systemctl start   $(SERVICE)

status:
	systemctl status $(SERVICE) $(TIMER)

clean: disable
	- rm -f $(PREFIX)/bin/$(SCRIPT)
	- rm -f $(SYSDDIR)/$(SERVICE)
	- rm -f $(SYSDDIR)/$(TIMER)
	systemctl daemon-reload
	@echo "Removed $(SERVICE) and $(TIMER)"

uninstall: clean
