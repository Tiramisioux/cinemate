"""ClearHDR data-selection thresholds must not be seeded to a degenerate pair.

The imx585 driver boots the pair at EXP_TH_H 0x0FFF / EXP_TH_L 0x0000 and
carries a comment explaining why: with the two thresholds equal, the sensor
falls back to the AppNote's weighted blend and the ClearHDR combiner output
stays clamped near the black level, so every HDR frame comes out flat.

CineMate used to seed 0/0 into Redis on every boot, writing exactly that
rejected configuration over the driver's default. These tests pin the two
halves of the fix: the shipped settings no longer configure a degenerate
pair, and an unconfigured threshold seeds "" (write nothing) rather than 0.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from module.config_loader import clearhdr_startup_values  # noqa: E402
from module.config_loader import _strip_jsonc_comments, _strip_trailing_commas  # noqa: E402


def _shipped_hdr_settings():
    text = (REPO_ROOT / "settings.jsonc").read_text(encoding="utf-8")
    settings = json.loads(_strip_trailing_commas(_strip_jsonc_comments(text)))
    return settings["image_capture"]["hdr"]


def test_shipped_settings_do_not_configure_a_degenerate_threshold_pair():
    hdr = _shipped_hdr_settings()
    low, high = hdr.get("threshold_low"), hdr.get("threshold_high")

    if low is None or high is None:
        # "leave the driver's pair alone" -- only valid if neither is set,
        # because cinepi-raw writes 0 for whichever side is empty.
        assert low is None and high is None
    else:
        assert low != high


def test_unconfigured_thresholds_seed_empty_not_zero():
    values = clearhdr_startup_values({"image_capture": {"hdr": {}}})

    assert values["hdr_threshold_low"] == ""
    assert values["hdr_threshold_high"] == ""


def test_explicit_null_seeds_empty_not_zero():
    settings = {
        "image_capture": {"hdr": {"threshold_low": None, "threshold_high": None}}
    }

    values = clearhdr_startup_values(settings)

    assert values["hdr_threshold_low"] == ""
    assert values["hdr_threshold_high"] == ""


def test_configured_thresholds_are_passed_through():
    settings = {
        "image_capture": {"hdr": {"threshold_low": 0, "threshold_high": 4095}}
    }

    values = clearhdr_startup_values(settings)

    assert values["hdr_threshold_low"] == 0
    assert values["hdr_threshold_high"] == 4095


def test_blend_and_gain_adder_keep_their_defaults():
    values = clearhdr_startup_values({})

    assert values["hdr_blend"] == 0
    assert values["hdr_gain_adder"] == 1


@pytest.mark.parametrize("hdr_cfg", [None, [], "nonsense", 7])
def test_malformed_hdr_block_does_not_raise(hdr_cfg):
    values = clearhdr_startup_values({"image_capture": {"hdr": hdr_cfg}})

    assert values["hdr_threshold_low"] == ""
    assert values["hdr_gain_adder"] == 1


def test_shipped_settings_validate_against_the_schema():
    jsonschema = pytest.importorskip("jsonschema")

    text = (REPO_ROOT / "settings.jsonc").read_text(encoding="utf-8")
    settings = json.loads(_strip_trailing_commas(_strip_jsonc_comments(text)))
    schema = json.loads((REPO_ROOT / "settings.schema.json").read_text(encoding="utf-8"))

    jsonschema.validate(settings, schema)
