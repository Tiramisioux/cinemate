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
    gpio_defaults = {
        "pwm_pin": 19,
        "rec_out_pin": [6, 21],
    }
    gpio_cfg = settings.setdefault("gpio_output", {})
    for k, v in gpio_defaults.items():
        gpio_cfg.setdefault(k, v)
    settings["gpio_output"] = gpio_cfg
    settings.setdefault("arrays",          {})
    settings.setdefault("settings",        {"light_hz": [50, 60], "conform_frame_rate": 24})
    system_cfg = settings.setdefault("system", {})
    wifi_defaults = {
        "name": "CinePi",
        "password": "11111111",
        "enabled": True,
    }
    wifi_cfg = system_cfg.setdefault("wifi_hotspot", {})
    for k, v in wifi_defaults.items():
        wifi_cfg.setdefault(k, v)
    system_cfg["wifi_hotspot"] = wifi_cfg
    settings["system"] = system_cfg
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
    settings.setdefault(
        "quad_rotary_controller",
        {"enabled": False, "encoders": {}}
    )
    settings.setdefault("welcome_message", "THIS IS A COOL MACHINE")
    settings.setdefault("welcome_image", None)
    settings.setdefault("state_model", "v1")

    launch_cfg = settings.setdefault("launch", {})
    launch_cfg.setdefault("rt_mode", "off")
    launch_cfg.setdefault("rt_priority", 20)
    launch_cfg.setdefault("cpu_affinity", "1-3")
    settings["launch"] = launch_cfg

    recording_profiles = settings.setdefault("recording_profiles", {})
    recording_profiles.setdefault("active", "B")
    profile_table = recording_profiles.setdefault("profiles", {})
    profile_table.setdefault(
        "A",
        {
            "encode_workers": 3,
            "disk_workers": 2,
            "encode_affinity": "1-2",
            "disk_affinity": "2",
            "encode_nice": -10,
            "disk_nice": -5,
        },
    )
    profile_table.setdefault(
        "B",
        {
            "encode_workers": 2,
            "disk_workers": 1,
            "encode_affinity": "2-3",
            "disk_affinity": "1",
            "encode_nice": -6,
            "disk_nice": -12,
        },
    )
    profile_table.setdefault(
        "C",
        {
            "encode_workers": 2,
            "disk_workers": 2,
            "encode_affinity": "1-2",
            "disk_affinity": "3",
            "encode_nice": -8,
            "disk_nice": -8,
        },
    )
    profile_table.setdefault("custom", dict(profile_table["B"]))
    recording_profiles["profiles"] = profile_table
    settings["recording_profiles"] = recording_profiles

    stdout_metadata_cfg = settings.setdefault("stdout_metadata", {})
    stdout_metadata_cfg.setdefault("enabled", False)
    settings["stdout_metadata"] = stdout_metadata_cfg

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

    # ── resolution filter defaults ─────────────────────────────────────
    resolution_defaults = {
        "k_steps": [1.5, 2.0, 4.0],
        "bit_depths": [10, 12],
        "custom_modes": {},
    }
    res_cfg = settings.setdefault("resolutions", {})
    for k, v in resolution_defaults.items():
        res_cfg.setdefault(k, v)
    settings["resolutions"] = res_cfg

    return settings
