# Makefile for cinemate-recovery
#
# Deviates from the wifi-hotspot Makefile in one way: the script is installed
# into a private LIBDIR rather than $(PREFIX)/bin, because it ships with a
# sibling module (jsonc.py) that it imports. Putting an importable module on
# the PATH would be untidy and would risk shadowing.
PREFIX  ?= /usr/local
LIBDIR  ?= $(PREFIX)/lib/cinemate-recovery
SYSDDIR ?= /etc/systemd/system

SCRIPT  = cinemate-recovery.py
MODULES = jsonc.py
SERVICE = cinemate-recovery.service

.PHONY: all install enable disable start stop restart status clean uninstall

all:
	@echo "Nothing to build - use 'make install'"

install:
	install -d $(LIBDIR)
	install -m 755 $(SCRIPT)  $(LIBDIR)/$(SCRIPT)
	install -m 644 $(MODULES) $(LIBDIR)/
	install -m 644 $(SERVICE) $(SYSDDIR)/$(SERVICE)
	install -d -m 755 /var/lib/cinemate
	install -d -m 700 /var/lib/cinemate/backups
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
	- rm -rf $(LIBDIR)
	- rm -f $(SYSDDIR)/$(SERVICE)
	systemctl daemon-reload
	@echo "Removed $(SERVICE) (kept /var/lib/cinemate and its backups)"

uninstall: clean     # alias for convenience
