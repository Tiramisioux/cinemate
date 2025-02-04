from skidl import *

# Create a generic 40-pin Raspberry Pi header
rpi_header = Part("SKiDL", "J", footprint="Connector_Generic:Conn_02x20", dest=TEMPLATE)
rpi_header.pins = [Pin(num=i, name=f"GPIO{i}", func=Pin.BIDIR) for i in range(1, 41)]
