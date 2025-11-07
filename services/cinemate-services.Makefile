.PHONY: all install uninstall

install:
        $(MAKE) -C storage-automount install
        $(MAKE) -C ssd-automount install
        $(MAKE) -C nvme-automount install
        $(MAKE) -C cfe-hat-automount install

uninstall:
        $(MAKE) -C ssd-automount uninstall
        $(MAKE) -C nvme-automount uninstall
        $(MAKE) -C cfe-hat-automount uninstall
        $(MAKE) -C storage-automount uninstall
