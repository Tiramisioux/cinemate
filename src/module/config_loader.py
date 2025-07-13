import sys
import json
import logging
from pathlib import Path

def load_settings(filename: str | Path) -> dict:
    """
    Load CineMate’s JSON configuration *and* guarantee that every section the
    code relies on is present with safe defaults.

    Return an always-valid settings dict – never None.
    """
    filename = Path(filename)
    try:
        with filename.open("r", encoding="utf-8") as fp:
            settings = json.load(fp)
    except FileNotFoundError:
        logging.warning("Settings file %s not found – using built-in defaults", filename)
        settings = {}
    except Exception as e:
        logging.error("Failed to load settings %s: %s – using built-in defaults", filename, e)
        settings = {}

    # ── top-level placeholders ───────────────────────────────────────────

    gpio_cfg = settings.setdefault("gpio_output",     {})
    gpio_cfg.setdefault("sys_LED", [])
    gpio_cfg.setdefault("sys_LED_RGB", [])

    settings.setdefault("arrays",          {})
    settings.setdefault("settings",        {"light_hz": [50, 60]})
    settings.setdefault("analog_controls", {})
    settings.setdefault("free_mode",       {
        "iso_free":       False,
        "shutter_a_free": False,
        "fps_free":       False,
        "wb_free":        False,
    })
    settings.setdefault("buttons",              [])
    settings.setdefault("two_way_switches",     [])
    settings.setdefault("rotary_encoders",      [])
    settings.setdefault("quad_rotary_encoders", {})

    # ── preview / zoom defaults ──────────────────────────────────────────
    preview_defaults = {
        "default_zoom": 1.0,
        "zoom_steps"  : [1.0, 1.5, 2.0],
    }
    preview_cfg = settings.setdefault("preview", {})
    for k, v in preview_defaults.items():
        preview_cfg.setdefault(k, v)

    # tidy up preview section
    preview_cfg["zoom_steps"] = sorted(set(preview_cfg["zoom_steps"]))
    if preview_cfg["default_zoom"] not in preview_cfg["zoom_steps"]:
        preview_cfg["default_zoom"] = preview_cfg["zoom_steps"][0]
    settings["preview"] = preview_cfg

    # ── anamorphic preview defaults (used by CinePiController) ───────────
    ana_defaults = {
        "anamorphic_steps":         [1.00, 1.33, 2.00],
        "default_anamorphic_factor": 1.00,
    }
    ana_cfg = settings.setdefault("anamorphic_preview", {})
    for k, v in ana_defaults.items():
        ana_cfg.setdefault(k, v)
    settings["anamorphic_preview"] = ana_cfg

    # ── array step-tables (iso / shutter-angle / fps / white-balance) ────
    array_defaults = {
        "iso_steps":       [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],
        "shutter_a_steps": [1, 45, 90, 135, 172.8, 180, 225, 270, 315, 360],
        "fps_steps":       [1, 2, 4, 8, 12, 16, 18, 24, 25, 30],
        "wb_steps":        [3200, 4400, 5600],
    }
    arrays_cfg = settings["arrays"]
    for k, v in array_defaults.items():
        arrays_cfg.setdefault(k, v)
    settings["arrays"] = arrays_cfg

    # ── Duplicate GPIO pin check ─────────────────────────────────────────
    used_pins = []
    pin_sources = {}

    # Helper to add pins and track their source
    def add_pin(pin, source):
        if pin is not None:
            used_pins.append(pin)
            pin_sources.setdefault(pin, []).append(source)

    # sys_LED
    for led in gpio_cfg.get("sys_LED", []):
        add_pin(led.get("pin"), "gpio_output.sys_LED")

    # sys_LED_RGB
    for led in gpio_cfg.get("sys_LED_RGB", []):
        for pin in led.get("pins", []):
            add_pin(pin, "gpio_output.sys_LED_RGB")

    # pwm_pin
    if "pwm_pin" in gpio_cfg:
        add_pin(gpio_cfg["pwm_pin"], "gpio_output.pwm_pin")

    # rec_out_pin
    for pin in gpio_cfg.get("rec_out_pin", []):
        add_pin(pin, "gpio_output.rec_out_pin")

    # status_led_pin
    if "status_led_pin" in gpio_cfg:
        add_pin(gpio_cfg["status_led_pin"], "gpio_output.status_led_pin")

    # drive_led_pins
    for pin in (gpio_cfg.get("drive_led_pins") or {}).values():
        add_pin(pin, "gpio_output.drive_led_pins")

    # buttons
    for btn in settings.get("buttons", []):
        add_pin(btn.get("pin"), "buttons")

    # two_way_switches
    for sw in settings.get("two_way_switches", []):
        add_pin(sw.get("pin"), "two_way_switches")

    # rotary_encoders
    for enc in settings.get("rotary_encoders", []):
        add_pin(enc.get("clk_pin"), "rotary_encoders.clk_pin")
        add_pin(enc.get("dt_pin"), "rotary_encoders.dt_pin")

    # quad_rotary_encoders
    for enc in settings.get("quad_rotary_encoders", {}).values():
        add_pin(enc.get("gpio_pin"), "quad_rotary_encoders")

    # Check for duplicates
    from collections import Counter
    pin_counts = Counter(used_pins)
    duplicates = []
    for pin, count in pin_counts.items():
        sources = set(pin_sources[pin])
        # Allow overlap between buttons and quad_rotary_encoders only
        if count > 1:
            if sources <= {"buttons", "quad_rotary_encoders"}:
                continue  # allowed
            duplicates.append(pin)

    if duplicates:
        print("\nERROR: Duplicate GPIO pin assignments detected!\n")
        for pin in duplicates:
            print(f"  Pin {pin} is used in: {', '.join(pin_sources[pin])}")
        print("\nPlease resolve these conflicts in your settings.json and restart CineMate.\n")
        sys.exit(1)

    return settings
