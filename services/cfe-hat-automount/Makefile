PREFIX  ?= /usr/local
SYSDDIR ?= /etc/systemd/system

SERVICE = cfe-hat-automount.service

.PHONY: all install enable disable start stop restart status clean uninstall

all:
	@echo "Nothing to build – use 'make install'"

install:
	$(MAKE) -C ../storage-automount install
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
	- rm -f $(SYSDDIR)/$(SERVICE)
	systemctl daemon-reload
	@echo "Removed $(SERVICE)"

uninstall: clean
