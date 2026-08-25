"""The imx585 CSI-2 link frequency is a dtoverlay parameter, so it rides on
the same config.txt line as the sensor and the port:

    dtoverlay=imx585,cam0,link-frequency=1039500000

Getting it wrong is quiet on the Pi -- the sensor either refuses to probe at
boot or streams faster than the receiver can hold, and both look like "the
camera stopped working" hours later. So the write path validates against the
list the driver actually vouches for, and the read path round-trips it.

Only imx585 has this menu. imx283's driver supports two frequencies but its
overlay exposes no parameter; imx477 accepts any multiple of 3 MHz with no
upper bound (nothing to offer); imx296 has no link-frequencies property at
all. See the constants block in boot_config.py.
"""

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("psutil", types.SimpleNamespace())

from module.app.boot_config import (
    IMX585_DEFAULT_LINK_FREQUENCY,
    IMX585_LINK_FREQUENCIES,
    apply_config_txt_state,
    overlay_line_for,
    parse_config_txt,
)


def config_txt(*camera_lines: str) -> str:
    return "\n".join([
        "# >>> cinemate-install >>>",
        "# Managed by cinemate-install.sh",
        "",
        "dtparam=i2c_arm=on",
        "dtparam=audio=on",
        "",
        "# ---- Camera section ----",
        "",
        "camera_auto_detect=1",
        *camera_lines,
        "",
        "# ---- End camera section ----",
        "",
        "#dtoverlay=rp1-overclock",
        "# <<< cinemate-install <<<",
    ]) + "\n"


BASE = {"cam0_sensor": "imx585", "cam1_sensor": "none", "i2c": True, "audio": True}


class LinkFrequencyMenuTests(unittest.TestCase):
    def test_the_offered_values_match_the_driver(self):
        # will127534/imx585-v4l2-driver link_freqs[], minus 1188000000, which
        # the README reports as frame-dropping on the Pi 5.
        self.assertEqual(IMX585_LINK_FREQUENCIES, [
            297000000, 360000000, 445500000, 594000000, 720000000, 891000000, 1039500000,
        ])
        self.assertNotIn(1188000000, IMX585_LINK_FREQUENCIES)
        self.assertIn(IMX585_DEFAULT_LINK_FREQUENCY, IMX585_LINK_FREQUENCIES)


class OverlayLineTests(unittest.TestCase):
    def test_a_non_default_frequency_is_written_onto_the_overlay_line(self):
        self.assertEqual(
            overlay_line_for("imx585", "cam0", 1039500000),
            "dtoverlay=imx585,cam0,link-frequency=1039500000",
        )

    def test_the_default_frequency_is_left_off_the_line(self):
        # The overlay already defaults to this. Writing it would put a number
        # in config.txt that the next reader has to look up to learn it means
        # "unchanged".
        self.assertEqual(
            overlay_line_for("imx585", "cam0", IMX585_DEFAULT_LINK_FREQUENCY),
            "dtoverlay=imx585,cam0",
        )

    def test_mono_and_link_frequency_coexist(self):
        self.assertEqual(
            overlay_line_for("imx585_mono", "cam1", 891000000),
            "dtoverlay=imx585,cam1,mono,link-frequency=891000000",
        )

    def test_sensors_without_the_parameter_never_get_one(self):
        for model in ("imx477", "imx296", "imx283"):
            self.assertEqual(overlay_line_for(model, "cam0", 891000000), f"dtoverlay={model},cam0")


class RoundTripTests(unittest.TestCase):
    def test_a_written_frequency_reads_back(self):
        out = apply_config_txt_state(
            config_txt("dtoverlay=imx585,cam0"), {**BASE, "cam0_link_frequency": 1039500000},
        )

        parsed = parse_config_txt(out)
        self.assertEqual(parsed["cam0_sensor"], "imx585")
        self.assertEqual(parsed["cam0_link_frequency"], 1039500000)

    def test_an_absent_parameter_reads_as_none_not_as_the_default_number(self):
        # None means "the overlay decides". Substituting the number here would
        # make the next save write it out as though it had been chosen.
        parsed = parse_config_txt(config_txt("dtoverlay=imx585,cam0"))
        self.assertIsNone(parsed["cam0_link_frequency"])

    def test_mono_with_a_frequency_round_trips(self):
        parsed = parse_config_txt(config_txt("dtoverlay=imx585,cam1,mono,link-frequency=594000000"))
        self.assertEqual(parsed["cam1_sensor"], "imx585_mono")
        self.assertEqual(parsed["cam1_link_frequency"], 594000000)

    def test_the_two_ports_are_independent(self):
        out = apply_config_txt_state(
            config_txt("dtoverlay=imx585,cam0", "dtoverlay=imx585,cam1"),
            {
                "cam0_sensor": "imx585", "cam0_link_frequency": 297000000,
                "cam1_sensor": "imx585", "cam1_link_frequency": 891000000,
            },
        )

        parsed = parse_config_txt(out)
        self.assertEqual(parsed["cam0_link_frequency"], 297000000)
        self.assertEqual(parsed["cam1_link_frequency"], 891000000)

    def test_a_hand_written_garbage_value_reads_as_unknown(self):
        # Reporting 0 would let the next save silently overwrite whatever the
        # operator hand-edited in.
        parsed = parse_config_txt(config_txt("dtoverlay=imx585,cam0,link-frequency=fast"))
        self.assertIsNone(parsed["cam0_link_frequency"])
        self.assertEqual(parsed["cam0_sensor"], "imx585")


class ValidationTests(unittest.TestCase):
    def test_a_value_the_driver_does_not_list_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            apply_config_txt_state(
                config_txt("dtoverlay=imx585,cam0"), {**BASE, "cam0_link_frequency": 500000000},
            )
        self.assertIn("not a supported imx585 link frequency", str(caught.exception))

    def test_the_frame_dropping_value_is_refused(self):
        with self.assertRaises(ValueError):
            apply_config_txt_state(
                config_txt("dtoverlay=imx585,cam0"), {**BASE, "cam0_link_frequency": 1188000000},
            )

    def test_asking_for_one_on_a_sensor_that_has_none_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            apply_config_txt_state(
                config_txt("dtoverlay=imx477,cam0"),
                {**BASE, "cam0_sensor": "imx477", "cam0_link_frequency": 891000000},
            )
        self.assertIn("no selectable link frequency", str(caught.exception))

    def test_a_stale_frequency_on_an_emptied_port_does_not_fail_the_save(self):
        # Pick imx585 + 891, then set the port to none: the form can still be
        # holding the frequency. No overlay line is emitted, so there is
        # nothing to be wrong about.
        out = apply_config_txt_state(
            config_txt("dtoverlay=imx585,cam0"),
            {"cam0_sensor": "none", "cam0_link_frequency": 891000000, "cam1_sensor": "none"},
        )
        self.assertNotIn("link-frequency", out)

    def test_a_non_numeric_value_is_refused(self):
        with self.assertRaises(ValueError):
            apply_config_txt_state(
                config_txt("dtoverlay=imx585,cam0"), {**BASE, "cam0_link_frequency": "fast"},
            )


if __name__ == "__main__":
    unittest.main()
