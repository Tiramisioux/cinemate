# ---------------------------------------------------------------
# Manage *all* services under cinemate/services/*
# ---------------------------------------------------------------
SUBSERVICES := cfe-hat-automount nvme-automount ssd-automount wifi-hotspot

.PHONY: all install enable disable start stop restart status clean uninstall \
        $(addprefix install-,$(SUBSERVICES))  \
        $(addprefix enable-,$(SUBSERVICES))   \
        $(addprefix disable-,$(SUBSERVICES))  \
        $(addprefix start-,$(SUBSERVICES))    \
        $(addprefix stop-,$(SUBSERVICES))     \
        $(addprefix restart-,$(SUBSERVICES))  \
        $(addprefix status-,$(SUBSERVICES))   \
        $(addprefix clean-,$(SUBSERVICES))    \
        $(addprefix uninstall-,$(SUBSERVICES)) \
        help

# ---------------------------------------------------------------
# Helper macro – call sub-makefile
# ---------------------------------------------------------------
define CALL_SUB
	$(MAKE) -C $(1) $(2)
endef

# ---------------------------------------------------------------
# umbrella targets
# ---------------------------------------------------------------
install enable disable start stop restart status clean:
	@for svc in $(SUBSERVICES); do \
	  $(call CALL_SUB,$$svc,$@); \
	done

# ---------------------------------------------------------------
# service-specific shortcut targets  (install-storage, enable-wifi, …)
# ---------------------------------------------------------------
$(foreach s,$(SUBSERVICES),\
  $(eval install-$(s): ; $(call CALL_SUB,$(s),install)) \
  $(eval enable-$(s) : ; $(call CALL_SUB,$(s),enable )) \
  $(eval disable-$(s): ; $(call CALL_SUB,$(s),disable)) \
  $(eval start-$(s)  : ; $(call CALL_SUB,$(s),start  )) \
  $(eval stop-$(s)   : ; $(call CALL_SUB,$(s),stop   )) \
  $(eval restart-$(s): ; $(call CALL_SUB,$(s),restart)) \
  $(eval status-$(s) : ; $(call CALL_SUB,$(s),status )) \
  $(eval clean-$(s)  : ; $(call CALL_SUB,$(s),clean  )) )

# ---------------------------------------------------------------
# default help
# ---------------------------------------------------------------
all help:
	@echo "Targets: install|enable|disable|start|stop|restart|status|clean"
	@echo "Add -<service> suffix for one service only, e.g. 'make start-storage-automount'"
