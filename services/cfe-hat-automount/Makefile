PREFIX ?= /usr/local

.PHONY: install uninstall

install:
	install -Dm755 cfe-hat-automount.py $(DESTDIR)$(PREFIX)/bin/cfe-hat-automount
	install -Dm644 cfe-hat-automount.service $(DESTDIR)/etc/systemd/system/cfe-hat-automount.service
	sudo systemctl daemon-reload
	sudo systemctl enable --now cfe-hat-automount.service

uninstall:
	sudo systemctl disable --now cfe-hat-automount.service || true
	rm -f $(DESTDIR)$(PREFIX)/bin/cfe-hat-automount
	rm -f $(DESTDIR)/etc/systemd/system/cfe-hat-automount.service
	sudo systemctl daemon-reload
