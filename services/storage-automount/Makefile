# Shared install for storage-automount Python helper
PREFIX  ?= /usr/local

SCRIPT  = storage-automount.py

.PHONY: all install uninstall clean

all:
	@echo "Nothing to build – use 'make install'"

install:
	install -m 755 $(SCRIPT) $(PREFIX)/bin/$(SCRIPT)

clean uninstall:
	- rm -f $(PREFIX)/bin/$(SCRIPT)
	@echo "Removed $(SCRIPT)"
