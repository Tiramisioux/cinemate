.PHONY: all install uninstall

# sudo chmod +x /usr/local/bin/ssd-automount
# sudo chmod +x /usr/local/bin/nvme-automount
# sudo chmod +x /usr/local/bin/cfe-hat-automount


install:
	$(MAKE) -C ssd-automount install
	$(MAKE) -C nvme-automount install
	$(MAKE) -C cfe-hat-automount install

uninstall:
	$(MAKE) -C ssd-automount uninstall
	$(MAKE) -C nvme-automount uninstall
	$(MAKE) -C cfe-hat-automount uninstall
