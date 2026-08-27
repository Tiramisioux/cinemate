"""The RP1 overclock toggle must not claim success it cannot deliver.

Flipping the toggle rewrites one line in config.txt and then reboots. If that
line is not in the file -- a Pi 4, or a Pi 5 installed before the installer
started writing it -- the substitution matches nothing. The old code still
returned "Saved." and rebooted, so the operator came back to a Pi on stock
clocks with nothing to explain it. Enabling now fails loudly; disabling stays
silent, because a missing line genuinely means the overclock is off.
"""

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# module.app.__init__ pulls in redis_controller, which needs neither library
# for anything this test touches -- same stubbing the other editor tests use.
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("psutil", types.SimpleNamespace())

from module.app.boot_config import RP1_OVERCLOCK_LINE, apply_config_txt_state, parse_config_txt


def config_txt(rp1_line: str | None) -> str:
    body = [
        "# >>> cinemate-install >>>",
        "# Managed by cinemate-install.sh",
        "",
        "dtparam=i2c_arm=on",
        "#dtparam=i2s=on",
        "#dtparam=spi=on",
        "dtparam=audio=on",
        "",
        "# ---- Camera section ----",
        "",
        "camera_auto_detect=1",
        "dtoverlay=imx477,cam0",
        "",
        "# ---- End camera section ----",
        "",
    ]
    if rp1_line is not None:
        body.append(rp1_line)
    body.append("# <<< cinemate-install <<<")
    return "\n".join(body) + "\n"


BASE_STATE = {
    "cam0_sensor": "imx477",
    "cam1_sensor": "none",
    "i2c": True,
    "i2s": False,
    "spi": False,
    "audio": True,
}


class Rp1ToggleTests(unittest.TestCase):
    def test_enabling_uncomments_the_overlay_line(self):
        text = config_txt("#" + RP1_OVERCLOCK_LINE)

        out = apply_config_txt_state(text, {**BASE_STATE, "rp1_overclock": True})

        self.assertIn("\n" + RP1_OVERCLOCK_LINE + "\n", out)
        self.assertTrue(parse_config_txt(out)["rp1_overclock"])

    def test_disabling_comments_the_overlay_line(self):
        text = config_txt(RP1_OVERCLOCK_LINE)

        out = apply_config_txt_state(text, {**BASE_STATE, "rp1_overclock": False})

        self.assertIn("\n#" + RP1_OVERCLOCK_LINE + "\n", out)
        self.assertFalse(parse_config_txt(out)["rp1_overclock"])

    def test_enabling_without_the_line_is_refused_rather_than_silently_ignored(self):
        text = config_txt(None)

        with self.assertRaises(ValueError) as caught:
            apply_config_txt_state(text, {**BASE_STATE, "rp1_overclock": True})

        # The message has to name the fix; a bare "failed" sends the operator
        # back to reading source.
        self.assertIn("cinemate-install.sh", str(caught.exception))

    def test_disabling_without_the_line_is_accepted(self):
        # Absent means off. Refusing here would 400 every unrelated save on a
        # Pi 4, since the form always submits rp1_overclock.
        text = config_txt(None)

        out = apply_config_txt_state(text, {**BASE_STATE, "rp1_overclock": False})

        self.assertNotIn("rp1-overclock", out)

    def test_unrelated_edits_still_apply_on_a_board_without_the_line(self):
        text = config_txt(None)

        out = apply_config_txt_state(
            text, {**BASE_STATE, "cam0_sensor": "imx585", "spi": True, "rp1_overclock": False},
        )

        parsed = parse_config_txt(out)
        self.assertEqual(parsed["cam0_sensor"], "imx585")
        self.assertTrue(parsed["spi"])

    def test_rp1_available_reports_whether_the_line_exists(self):
        self.assertTrue(parse_config_txt(config_txt("#" + RP1_OVERCLOCK_LINE))["rp1_available"])
        self.assertFalse(parse_config_txt(config_txt(None))["rp1_available"])

    def test_nothing_outside_the_managed_block_is_touched(self):
        text = "# hand-written prologue\n" + config_txt("#" + RP1_OVERCLOCK_LINE) + "dtparam=nvme\n"

        out = apply_config_txt_state(text, {**BASE_STATE, "rp1_overclock": True})

        self.assertTrue(out.startswith("# hand-written prologue\n"))
        self.assertTrue(out.endswith("dtparam=nvme\n"))


if __name__ == "__main__":
    unittest.main()
