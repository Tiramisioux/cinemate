import logging
import os
import threading
import time
from typing import TypedDict
import board
import busio
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont
from module.utils import Utils


class i2cOledSettings(TypedDict):
    width: int
    height: int
    enabled: bool
    font_size: int
    values: list[str]
    

class I2cOled(threading.Thread):
    RECONNECT_INTERVAL = 5  # seconds between reconnection attempts

    def __init__(self, settings: i2cOledSettings, redis_controller):
        super().__init__(daemon=True)
        self.settings: i2cOledSettings = settings.get("i2c_oled", {})
        self.redis_controller = redis_controller
        self.width = self.settings.get("width", 128)
        self.height = self.settings.get("height", 64)
        self.font_size = self.settings.get("font_size", 10)
        self.values = self.settings.get(
            "values", ["iso", "fps", "shutter_a", "resolution", "is_recording"]
        )

        self.i2c = None
        self.oled = None
        self.connected = False
        self._last_reconnect = 0

        self._initialize_display()

    def _initialize_display(self):
        """
        Attempt to set up the I2C interface and OLED display.
        If the device is not found, mark as disconnected and retry later.
        """
        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            # wait briefly for bus
            time.sleep(0.1)
            self.oled = adafruit_ssd1306.SSD1306_I2C(
                self.width, self.height, self.i2c
            )
            self.connected = True
            logging.info("OLED initialized successfully.")
        except Exception as e:
            self.connected = False
            logging.warning(
                "Failed to initialize OLED: %s. Will retry in %ds.",
                e,
                self.RECONNECT_INTERVAL,
            )
            self._last_reconnect = time.time()

    def display_text(self, text, x=0, y=0):
        if not self.connected:
            return

        try:
            image = Image.new("1", (self.oled.width, self.oled.height))
            draw = ImageDraw.Draw(image)
            current_directory = os.path.dirname(os.path.abspath(__file__))
            font_path = os.path.join(
                current_directory, '../../resources/fonts/Arial.ttf'
            )
            font = ImageFont.truetype(font_path, self.font_size)
            draw.text((x, y), text, font=font, fill=255)
            self.oled.image(image)
            self.oled.show()
        except OSError as e:
            # Handle I/O errors (e.g., disconnected during runtime)
            self.connected = False
            logging.error("OLED write error: %s. Marking as disconnected.", e)

    def update(self):
        # Attempt reconnection if disconnected and interval has passed
        if not self.connected:
            now = time.time()
            if now - self._last_reconnect >= self.RECONNECT_INTERVAL:
                self._initialize_display()
            return

        texts = {
            "shutter_a": {"label": "SHUTTER", "suffix": "°"},
            "wb_user": {"label": "WB", "suffix": "K"},
            "space_left": {"label": "SPACE", "suffix": "GB"},
        }
        lines = []
        firstLine = []
        for key in self.values:
            match key:
                case "is_recording":
                    firstLine.append(
                        "●"
                        if bool(int(self.redis_controller.get_value(key, 0)))
                        else " "
                    )
                case "resolution":
                    firstLine.append(
                        f"{self.redis_controller.get_value('width', '')}x"
                        f"{self.redis_controller.get_value('height', '')}@"
                        f"{self.redis_controller.get_value('bit_depth', '')}Bit"
                    )
                case "cpu_load":
                    lines.append(f"CPU: {Utils.cpu_load()}")
                case "cpu_temp":
                    lines.append(f"TEMP: {Utils.cpu_temp()}")
                case "memory_usage":
                    lines.append(f"RAM: {Utils.memory_usage()}")
                case _:
                    value = self.redis_controller.get_value(key, "N/A")
                    label = texts.get(key, {}).get("label", key.upper())
                    suffix = texts.get(key, {}).get("suffix", "")
                    lines.append(f"{label}: {value}{suffix}")

        if firstLine:
            lines.insert(0, " ".join(firstLine))
        text = "\n".join(lines)
        # logging.info("Updating OLED: \n%s", text)
        self.display_text(text, 0, 0)

    def run(self):
        while True:
            self.update()
            time.sleep(1)
