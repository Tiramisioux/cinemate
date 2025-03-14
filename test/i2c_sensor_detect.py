import subprocess
import re

# Camera I2C address patterns (stored as integers)
CAMERA_SENSORS = {
    "IMX477": {"unique": [0x64], "absent": []},  # IMX477 is uniquely identified by 0x64
    "IMX585 MONO": {"unique": [0x48], "absent": [0x64]},  # IMX585 MONO should NOT have 0x64
}

I2C_BUSES = [1, 4, 11, 12]  # List of buses to check

def scan_i2c(bus):
    """Scans an I2C bus and returns detected addresses as integers."""
    try:
        print(f"\n🔍 Scanning I2C bus {bus}...")
        result = subprocess.run(["i2cdetect", "-y", str(bus)], capture_output=True, text=True)

        # Print raw `i2cdetect` output for debugging
        print(f"📝 Raw i2cdetect output for bus {bus}:\n{result.stdout}")

        detected_addresses = set()
        for line in result.stdout.split("\n"):
            parts = line.split()
            if parts and re.match(r"^[0-9a-fA-F]+:", parts[0]):  # Check for valid I2C data row
                detected_addresses.update(
                    int(x, 16) for x in parts[1:] if re.match(r"^[0-9a-fA-F]{2}$", x) and x != "--"
                )

        print(f"✅ Bus {bus}: Parsed detected addresses -> {detected_addresses}")  # Debugging output
        return detected_addresses
    except Exception as e:
        print(f"⚠️ Error scanning I2C bus {bus}: {e}")
        return set()

def detect_camera():
    """Detects whether an IMX585 MONO or IMX477 camera is attached."""
    detected_addresses = set()

    # Scan all relevant I2C buses
    for bus in I2C_BUSES:
        detected_addresses.update(scan_i2c(bus))

    print(f"\n📌 All detected addresses: {detected_addresses}")  # Debugging output

    # Prioritize IMX477 first (it has a unique identifier)
    if 0x64 in detected_addresses:
        print("\n✅ IMX477 detected due to presence of I2C address 0x64.")
        return "\n✅ Detected Camera: IMX477"

    # If IMX477 was NOT found, check for IMX585 MONO
    if 0x48 in detected_addresses and 0x64 not in detected_addresses:
        print("\n✅ IMX585 MONO detected due to presence of I2C address 0x48.")
        return "\n✅ Detected Camera: IMX585 MONO"

    return "\n❌ No known camera detected."

if __name__ == "__main__":
    print(detect_camera())
