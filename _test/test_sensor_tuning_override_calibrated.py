"""Guard against re-shipping an uncalibrated stub as a sensor tuning override.

development/imx283-active-size/ROUND2.md, Defect A: `cinemate-install.sh`
used to overlay `resources/tuning_files/imx283.json` onto libcamera's own
*calibrated* `imx283.json`. The overlay file was a 5-algorithm stub --
byte-identical to libcamera's `uncalibrated.json` except for one field
(`black_level`) -- with `rpi.awb` set to `bayes: 0` and no `ct_curve`. That
produced a 2.70x blue AWB gain and a magenta render in both the preview and
every DNG. imx283 was removed from the override list because libcamera
already ships a calibrated tuning for it; imx585 and imx585_mono stay,
because no stock tuning exists for them.

`resources/tuning_files/imx283.json` itself was kept rather than deleted --
`test_sensor_database.py`'s
`test_log_encode_support_matrix_is_derived_from_tuning_black_levels` reads
its `rpi.black_level` to cross-check `sensors.json`, and the settings-editor
tuning picker (`_list_tuning_files()`) lists it as a manual
`tuning_file_override` choice -- but its *content* is now the calibrated
47 KB file the fork ships in `libcamera`, not the stub, so either reader now
sees real calibration data.

This is the guard against the same mistake recurring, for imx283 or any
future sensor: every file `cinemate-install.sh` installs as a tuning
override must not be a byte-for-byte copy of `uncalibrated.json` (Defect A's
"at minimum" bar), the same holds for `imx283.json` even though it is no
longer installed by default, and imx283 specifically must never be back in
the installed list, since libcamera ships a calibrated tuning for it.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "cinemate-install.sh"
TUNING_DIR = ROOT / "resources/tuning_files"
UNCALIBRATED = TUNING_DIR / "uncalibrated.json"


def _installed_tuning_files(script_text: str) -> list[str]:
    """The `tuning_files=( ... )` array body inside
    install_sensor_tuning_overrides(), one filename per line."""
    match = re.search(
        r"install_sensor_tuning_overrides\(\).*?tuning_files=\((.*?)\)",
        script_text,
        re.DOTALL,
    )
    assert match, f"tuning_files array not found in {INSTALLER}"
    return re.findall(r"(\S+\.json)", match.group(1))


class SensorTuningOverrideCalibratedTests(unittest.TestCase):
    def setUp(self):
        self.script_text = INSTALLER.read_text()
        self.tuning_files = _installed_tuning_files(self.script_text)
        self.uncalibrated_bytes = UNCALIBRATED.read_bytes()

    def test_imx283_is_not_overridden(self):
        # libcamera already ships a calibrated imx283.json; CineMate must not
        # clobber it. See Defect A.
        self.assertNotIn(
            "imx283.json",
            self.tuning_files,
            "imx283.json is back in install_sensor_tuning_overrides()'s list "
            "-- libcamera already ships a calibrated tuning for imx283, so "
            "CineMate overriding it re-introduces the magenta/blue-gain bug "
            "(ROUND2.md Defect A). Confirm the shipped tuning is genuinely "
            "uncalibrated before adding a sensor back to this list.",
        )

    def test_every_installed_override_is_not_an_uncalibrated_copy(self):
        # At minimum: whatever CineMate does install must not be a copy of
        # libcamera's own "no calibration data" placeholder.
        for name in self.tuning_files:
            path = TUNING_DIR / name
            self.assertTrue(path.is_file(), f"{path} does not exist")
            data = path.read_bytes()
            self.assertNotEqual(
                data,
                self.uncalibrated_bytes,
                f"{name} is byte-identical to uncalibrated.json -- it carries "
                "no AWB/CCM/ALSC calibration and will misrender colour "
                "(ROUND2.md Defect A). Do not install this as a tuning "
                "override.",
            )

    def test_imx283_json_itself_is_not_an_uncalibrated_copy(self):
        # imx283.json is not installed any more, but it is still shipped
        # (other readers: the log_encode black-level cross-check test, and
        # the settings-editor tuning picker as a manual override choice), so
        # its content must not regress back to the uncalibrated stub either.
        path = TUNING_DIR / "imx283.json"
        self.assertTrue(path.is_file(), f"{path} does not exist")
        self.assertNotEqual(
            path.read_bytes(),
            self.uncalibrated_bytes,
            "resources/tuning_files/imx283.json is byte-identical to "
            "uncalibrated.json again -- restore the calibrated file from "
            "libcamera/src/ipa/rpi/pisp/data/imx283.json (ROUND2.md Defect A).",
        )


if __name__ == "__main__":
    unittest.main()
