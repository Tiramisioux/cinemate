import json
import logging

def load_settings(filename):
    """Load configuration settings from JSON file."""
    try:
        with open(filename, 'r') as file:
            settings = json.load(file)

        # Ensure default values
        settings.setdefault('gpio_output', {})
        settings.setdefault('arrays', {})
        settings.setdefault('settings', {"light_hz": 50})
        settings.setdefault('analog_controls', {})
        settings.setdefault('free_mode', {"iso_free": False, "shutter_a_free": False, "fps_free": False, "wb_free": False})
        settings.setdefault('buttons', [])
        settings.setdefault('two_way_switches', [])
        settings.setdefault('rotary_encoders', [])
        settings.setdefault('quad_rotary_encoders', {})

        return settings
    except Exception as e:
        logging.error(f"Failed to load settings: {e}")
        return {}
