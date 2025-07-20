import logging, os, threading, time
from pathlib import Path
from typing import TypedDict

import board, busio, adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont
from module.utils import Utils           # keep your original helper

class i2cOledSettings(TypedDict):
    width: int
    height: int
    enabled: bool
    font_size: int
    values: list[str]

class I2cOled(threading.Thread):
    RECONNECT_INTERVAL = 5      # seconds

    # ──────────────────────────────────────────────────────────────────────
    # Constructor
    # ──────────────────────────────────────────────────────────────────────
    def __init__(self, settings: i2cOledSettings, redis_controller):
        super().__init__(daemon=True)
        logging.info("I2cOled from %s LOADED", __file__)

        s = settings.get("i2c_oled", {})
        self.width    = s.get("width", 128)
        self.height   = s.get("height", 64)
        self.font_sz  = s.get("font_size", 10)
        self.values   = s.get(
            "values", ["iso", "fps", "shutter_a", "resolution", "is_recording"]
        )

        self.redis_controller = redis_controller
        self.i2c, self.oled   = None, None
        self.connected        = False
        self._last_reconnect  = 0

        self.font = self._load_font()
        self._initialize_display()

    # ──────────────────────────────────────────────────────────────────────
    # Font handling
    # ──────────────────────────────────────────────────────────────────────
    def _load_font(self):
        """Return an ImageFont; always succeeds."""
        candidates = [
            Path(__file__).parent / "../../resources/fonts/Arial.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(str(path), self.font_sz)
            except (OSError, IOError):
                continue

        logging.warning("No TTF font found – falling back to Pillow default")
        try:
            return ImageFont.load_default()
        except Exception as e:                     # last-ditch defence
            logging.error("PIL default font failed: %s", e)
            raise                                    # now we *do* stop

    # ──────────────────────────────────────────────────────────────────────
    # Hardware init
    # ──────────────────────────────────────────────────────────────────────
    def _initialize_display(self):
        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            time.sleep(0.1)   # let the bus settle
            self.oled = adafruit_ssd1306.SSD1306_I2C(
                self.width, self.height, self.i2c
            )
            self.connected = True
            logging.info("OLED initialized successfully.")
        except Exception as e:
            self.connected = False
            self._last_reconnect = time.time()
            logging.warning("Failed to init OLED: %s – retry in %ds",
                            e, self.RECONNECT_INTERVAL)

    # ──────────────────────────────────────────────────────────────────────
    # Drawing helper
    # ──────────────────────────────────────────────────────────────────────
    def display_text(self, text, x=0, y=0):
        if not self.connected:
            return
        try:
            img  = Image.new("1", (self.oled.width, self.oled.height))
            draw = ImageDraw.Draw(img)
            draw.text((x, y), text, font=self.font, fill=255)

            self.oled.image(img)
            self.oled.show()
        except RuntimeError as e:      # adafruit_ssd1306 signals bus errors this way
            self.connected = False
            logging.error("OLED I/O error: %s – marking as disconnected", e)

    # ──────────────────────────────────────────────────────────────────────
    # Public update API (unchanged logic)
    # ──────────────────────────────────────────────────────────────────────
    def update(self):
        # reconnect if needed
        if not self.connected and time.time() - self._last_reconnect >= self.RECONNECT_INTERVAL:
            self._initialize_display()
            return

        texts = {
            "shutter_a":  {"label": "SHUTTER", "suffix": "°"},
            "wb_user":    {"label": "WB",      "suffix": "K"},
            "space_left": {"label": "SPACE",   "suffix": "GB"},
            "tc_cam0":   {"label": "", "suffix": ""},
            "RECORDING_TC": {"label": "", "suffix": ""},
        }

        first, lines = [], []
        for key in self.values:
            match key:
                case "is_recording":
                    first.append("●" if int(self.redis_controller.get_value(key, 0)) else " ")
                case "resolution":
                    first.append(
                        f"{self.redis_controller.get_value('width','')}x"
                        f"{self.redis_controller.get_value('height','')}@"
                        f"{self.redis_controller.get_value('bit_depth','')}Bit"
                    )
                case "cpu_load":
                    lines.append(f"CPU: {Utils.cpu_load()}")
                case "cpu_temp":
                    lines.append(f"TEMP: {Utils.cpu_temp()}")
                case "memory_usage":
                    lines.append(f"RAM: {Utils.memory_usage()}")
                case _:
                    v  = self.redis_controller.get_value(key, "N/A")
                    lbl = texts.get(key, {}).get("label", key.upper())
                    suf = texts.get(key, {}).get("suffix", "")
                    lines.append(f"{lbl}: {v}{suf}")

        if first:
            lines.insert(0, " ".join(first))
        self.display_text("\n".join(lines))

    # ──────────────────────────────────────────────────────────────────────
    # Thread loop
    # ──────────────────────────────────────────────────────────────────────
    def run(self):
        while True:
            self.update()
            time.sleep(1)
