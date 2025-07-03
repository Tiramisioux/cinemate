#!/usr/bin/env python3
import glob, time, sys, os, gpiod
from smbus2 import SMBus, i2c_msg

GPIO_CHIP = "/dev/gpiochip0"   # RP1 main bank
RESET_GPIO_CAM0, RESET_GPIO_CAM1 = 42, 43
I2C_ADDR = 0x1A

SENSORS = [ ("imx585", 0x0016, 0x0585, 0x0FFF),
            ("imx477", 0x0016, 0x0477, 0x0FFF),
            ("imx283", 0x0016, 0x0283, 0x0FFF),
            ("imx296", 0x3004, 0x0296, 0x0FFF) ]

BUS2PORT = {13: "cam0", 14: "cam1"}

def raise_resets():
    chip  = gpiod.Chip(GPIO_CHIP)
    lines = chip.get_lines([RESET_GPIO_CAM0, RESET_GPIO_CAM1])
    lines.request(consumer="cinepi-rst",
                  type=gpiod.LINE_REQ_DIR_OUT,
                  default_vals=[1, 1])
    time.sleep(0.003)          # 3 ms ≥ datasheet
    lines.release()

def read_word(bus, reg):
    hi, lo = (reg >> 8) & 0xFF, reg & 0xFF
    wr, rd = i2c_msg.write(I2C_ADDR, [hi, lo]), i2c_msg.read(I2C_ADDR, 2)
    bus.i2c_rdwr(wr, rd)
    d = list(rd)
    return (d[0] << 8) | d[1]

def identify(busnum):
    try:
        with SMBus(busnum) as bus:
            try:
                bus.read_byte(I2C_ADDR)     # quick ACK test
            except OSError:
                return None, None
            for name, reg, exp, mask in SENSORS:
                try:
                    val = read_word(bus, reg)
                except OSError:
                    continue
                if (val & mask) == (exp & mask):
                    return name, val
            return "unknown", None
    except FileNotFoundError:
        return None, None

def list_buses():
    return sorted(int(p.split("-")[-1]) for p in glob.glob("/dev/i2c-*"))

def main():
    if os.geteuid() != 0:
        sys.exit("Run with sudo.")
    raise_resets()

    any_found = False
    for bus in list_buses():
        name, val = identify(bus)
        if name:
            port = BUS2PORT.get(bus, "?")
            print(f"Bus {bus:02d}: {name} (ID 0x{val:04X}) → {port}"
                  if name != "unknown"
                  else f"Bus {bus:02d}: unknown sensor on {port}")
            any_found = True
    if not any_found:
        print("No camera sensors detected – check flex, power, GPIO numbers.")

if __name__ == "__main__":
    main()
