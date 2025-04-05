PREFIX ?= /usr/local

.PHONY: install uninstall

install:
	install -Dm755 nvme-automount $(DESTDIR)$(PREFIX)/bin/nvme-automount
	install -Dm644 99-nvme-automount.rules $(DESTDIR)/etc/udev/rules.d/99-nvme-automount.rules
	install -Dm644 nvme-automount@.service $(DESTDIR)/etc/systemd/system/nvme-automount@.service
	systemctl daemon-reload
	udevadm control --reload-rules

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/nvme-automount
	rm -f $(DESTDIR)/etc/udev/rules.d/99-nvme-automount.rules
	rm -f $(DESTDIR)/etc/systemd/system/nvme-automount@.service
	systemctl daemon-reload
