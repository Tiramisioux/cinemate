# Based on the original code by Will Whang: https://github.com/will127534/StarlightEye/blob/main/software/README.md

import json
import logging
import smbus
from module.redis_controller import ParameterKey

# Default I2C address of the StarlightEye IR filter controller
DEFAULT_I2C_ADDRESS = 0x34

# Mapping of camera ports to I2C bus numbers on Raspberry Pi 5
CAM_PORT_TO_BUS = {
    'cam1': 4,  # connector CAM1
    'cam0': 6,  # connector CAM0
}

class IRFilter:
    """Toggle the StarlightEye IR‑cut filter via I²C."""

    def __init__(self, redis_controller, i2c_address: int = DEFAULT_I2C_ADDRESS):
        self.redis = redis_controller
        self.address = i2c_address

    # ------------------------------------------------------------------
    def _get_ports(self):
        """Return camera ports with a colour IMX585 attached."""
        cams_json = self.redis.get_value(ParameterKey.CAMERAS.value) or "[]"
        try:
            cams = json.loads(cams_json)
        except Exception as e:
            logging.error("IRFilter: failed to decode CAMERAS json: %s", e)
            return []

        ports = []
        for cam in cams:
            model = cam.get("model", "").lower()
            is_mono = cam.get("mono", False)
            if "imx585" in model and not is_mono:
                ports.append(cam.get("port", "cam1"))
        return ports

    # ------------------------------------------------------------------
    def set_state(self, enable: bool) -> None:
        """Enable or disable the IR filter on all suitable cameras."""
        ports = self._get_ports()
        if not ports:
            logging.warning("IRFilter: no colour IMX585 sensor found")
        for port in ports:
            bus_num = CAM_PORT_TO_BUS.get(port, 4)
            try:
                bus = smbus.SMBus(bus_num)
                bus.write_byte(self.address, 0x01 if enable else 0x00)
                bus.close()
                logging.info(
                    "IRFilter: %s filter on %s (bus %d)",
                    "Enabled" if enable else "Disabled",
                    port,
                    bus_num,
                )
            except Exception as e:
                logging.error(
                    "IRFilter: failed to toggle filter on %s (bus %d): %s",
                    port,
                    bus_num,
                    e,
                )
        self.redis.set_value(ParameterKey.IR_FILTER.value, int(enable))