import xml.etree.ElementTree as ET
import zipfile
import os

# Create the root element
fritzing = ET.Element("fritzing")
fritzing.set("version", "0.9.3b")

# Add the parts section
parts = ET.SubElement(fritzing, "parts")

# Define a Raspberry Pi part
rpi_part = ET.SubElement(parts, "part")
rpi_part.set("moduleIdRef", "Raspberry_Pi_4B")
rpi_part.set("id", "rpi")

# Define a button
button_part = ET.SubElement(parts, "part")
button_part.set("moduleIdRef", "Tactile_Push_Button")
button_part.set("id", "button")

# Add wires (connections)
connections = ET.SubElement(fritzing, "connections")

# Connect GPIO4 to the button
wire = ET.SubElement(connections, "wire")
ET.SubElement(wire, "connector").set("part", "rpi")
ET.SubElement(wire, "connector").set("connectorId", "GPIO4")
ET.SubElement(wire, "connector").set("part", "button")
ET.SubElement(wire, "connector").set("connectorId", "1")

# Save the Fritzing XML
xml_tree = ET.ElementTree(fritzing)
xml_filename = "cinemate_circuit_simple.fz"
xml_tree.write(xml_filename)

# Create an FZZ archive (ZIP)
fzz_filename = "docs/schematics/wiring/cinemate_circuit_simple.fzz"
with zipfile.ZipFile(fzz_filename, 'w') as fzz:
    fzz.write(xml_filename, "Fritzing.fz")

# Cleanup
os.remove(xml_filename)

print(f"Fritzing file created: {fzz_filename}")
