PREFIX ?= /usr/local
UDEVDIR ?= /etc/udev/rules.d
SYSTEMD_DIR ?= /etc/systemd/system

.PHONY: install uninstall

install:
	install -Dm755 ssd-automount $(DESTDIR)$(PREFIX)/bin/ssd-automount
	install -Dm644 ssd-automount@.service $(DESTDIR)$(SYSTEMD_DIR)/ssd-automount@.service
	install -Dm644 99-ssd-automount.rules $(DESTDIR)$(UDEVDIR)/99-ssd-automount.rules
	sudo udevadm control --reload-rules
	sudo udevadm trigger --subsystem-match=block
	sudo systemctl daemon-reexec

uninstall:
	sudo systemctl stop ssd-automount@*.service || true
	rm -f $(DESTDIR)$(PREFIX)/bin/ssd-automount
	rm -f $(DESTDIR)$(SYSTEMD_DIR)/ssd-automount@.service
	rm -f $(DESTDIR)$(UDEVDIR)/99-ssd-automount.rules
	sudo udevadm control --reload-rules
	sudo systemctl daemon-reexec