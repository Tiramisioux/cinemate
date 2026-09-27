"""A driver switch must never be able to leave two camera overlays active.

Reported: "Switching between drivers from imx477 to imx283 resulted in both
entries being active in config.txt and imx283 set to cam1." Investigation
(development/todo-2026-09-27/CONFIG-TXT-FINDINGS.md) found that neither
cinemate-install.sh's configure_boot_config() nor a well-formed round trip
through this module's own parse/apply pair can produce that shape on their
own -- each always leaves exactly one overlay per port. The one config.txt
shape that reliably reproduces it: two `# ---- Camera section ----` ...
`# ---- End camera section ----` marker pairs in the same managed block (a
hand-merge of two snapshots, a stray paste while editing, or a backup
restored on top of a live file). `_extract()` always resolves to the FIRST
pair, so a save only ever rewrites that one -- the second pair's dtoverlay
line stays active and is invisible to every future read, which is exactly
"both entries active" with the stale line free to be on whichever port it
already held (cam1, in the report).

This file also covers the missing-camera-section case: apply_config_txt_state
used to silently skip the entire camera rewrite when the markers were absent
while still reporting "Saved." -- the same class of "success that changed
nothing" the RP1 overclock toggle was already guarded against.
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
    CAMERA_SECTION_BEGIN,
    CAMERA_SECTION_END,
    apply_config_txt_state,
    parse_config_txt,
)


def config_txt(camera_lines: list[str], extra_tail: str = "") -> str:
    body = [
        "# >>> cinemate-install >>>",
        "# Managed by cinemate-install.sh",
        "",
        "dtparam=i2c_arm=on",
        "#dtparam=i2s=on",
        "#dtparam=spi=on",
        "dtparam=audio=on",
        "",
        *camera_lines,
        "",
        "display_auto_detect=1",
    ]
    if extra_tail:
        body.append(extra_tail)
    body.append("# <<< cinemate-install <<<")
    return "\n".join(body) + "\n"


ONE_CAMERA_SECTION = [
    CAMERA_SECTION_BEGIN,
    "",
    "camera_auto_detect=1",
    "dtoverlay=imx477,cam0",
    "",
    CAMERA_SECTION_END,
]

DUPLICATE_CAMERA_SECTIONS = [
    CAMERA_SECTION_BEGIN,
    "",
    "camera_auto_detect=1",
    "dtoverlay=imx477,cam0",
    "",
    CAMERA_SECTION_END,
    "",
    CAMERA_SECTION_BEGIN,
    "",
    "camera_auto_detect=0",
    "dtoverlay=imx283,cam1",
    "",
    CAMERA_SECTION_END,
]

SWITCH_TO_IMX283_ON_CAM0 = {
    "cam0_sensor": "imx283",
    "cam1_sensor": "none",
    "i2c": True,
    "i2s": False,
    "spi": False,
    "audio": True,
}


class DuplicateCameraSectionTests(unittest.TestCase):
    def test_a_well_formed_switch_never_leaves_two_active_overlays(self):
        """Control case: proves the normal, single-marker-pair round trip is
        not where the reported defect lives."""
        text = config_txt(ONE_CAMERA_SECTION)

        out = apply_config_txt_state(text, SWITCH_TO_IMX283_ON_CAM0)

        self.assertEqual(out.count("\ndtoverlay=imx283,cam0\n"), 1)
        self.assertNotIn("imx477", out)
        parsed = parse_config_txt(out)
        self.assertEqual(parsed["cam0_sensor"], "imx283")
        self.assertEqual(parsed["cam1_sensor"], "none")

    def test_parse_reports_a_duplicated_camera_section(self):
        text = config_txt(DUPLICATE_CAMERA_SECTIONS)

        parsed = parse_config_txt(text)

        self.assertTrue(parsed["camera_section_duplicated"])
        # The first pair is still what's reported -- imx477 on cam0 -- so an
        # operator reading only this dict has no way to see the second,
        # already-active imx283-on-cam1 line hiding further down the file.
        self.assertEqual(parsed["cam0_sensor"], "imx477")
        self.assertEqual(parsed["cam1_sensor"], "none")

    def test_a_normal_file_is_not_flagged_as_duplicated(self):
        text = config_txt(ONE_CAMERA_SECTION)

        self.assertFalse(parse_config_txt(text)["camera_section_duplicated"])

    def test_saving_over_a_duplicated_camera_section_is_refused(self):
        """This is the reproduction: without the fix, apply_config_txt_state
        rewrites only the first `# ---- Camera section ----` pair (to
        imx283,cam0, as asked) and leaves the second pair's
        `dtoverlay=imx283,cam1` completely untouched -- landing exactly on
        the reported shape, two active overlays, one of them on cam1."""
        text = config_txt(DUPLICATE_CAMERA_SECTIONS)

        with self.assertRaises(ValueError) as caught:
            apply_config_txt_state(text, SWITCH_TO_IMX283_ON_CAM0)

        message = str(caught.exception)
        self.assertIn(CAMERA_SECTION_BEGIN, message)
        self.assertIn("more than one", message)


class MissingCameraSectionTests(unittest.TestCase):
    def test_a_camera_pick_with_no_markers_is_refused_rather_than_dropped(self):
        """No `# ---- Camera section ----` / `# ---- End camera section ----`
        pair at all -- e.g. a hand-edited file, or one written by something
        that never used this module's shape. Used to fall through
        apply_config_txt_state's `if cam_section is not None:` silently,
        rewriting the toggle lines and reporting "Saved." while the camera
        pick itself never reached the file."""
        text = config_txt(["camera_auto_detect=1", "dtoverlay=imx477,cam0"])

        with self.assertRaises(ValueError) as caught:
            apply_config_txt_state(text, SWITCH_TO_IMX283_ON_CAM0)

        # Name the fix, matching the RP1-overclock refusal's shape.
        self.assertIn(CAMERA_SECTION_BEGIN, str(caught.exception))
        self.assertIn("cinemate-install.sh", str(caught.exception))

    def test_unrelated_toggles_are_not_silently_applied_either(self):
        """Before the fix, apply_config_txt_state would still flip spi on and
        report success even though the camera pick was silently dropped -- a
        save that partially succeeds with no indication which part failed is
        its own defect. Now the whole save is refused up front, so the
        caller never gets a "new" config text with only half the change."""
        text = config_txt(["camera_auto_detect=1", "dtoverlay=imx477,cam0"])
        self.assertIn("#dtparam=spi=on", text)

        with self.assertRaises(ValueError):
            apply_config_txt_state(text, {**SWITCH_TO_IMX283_ON_CAM0, "spi": True})


class DtoverlayLineToleranceTests(unittest.TestCase):
    """_DTOVERLAY_LINE_RE used to require the exact shape
    `dtoverlay=<value>` with no leading whitespace and no spaces around `=`.
    A hand-edited config.txt is not guaranteed to look like that."""

    def test_leading_whitespace_is_recognised(self):
        text = config_txt([
            CAMERA_SECTION_BEGIN, "", "camera_auto_detect=1",
            "  dtoverlay=imx477,cam0", "", CAMERA_SECTION_END,
        ])

        self.assertEqual(parse_config_txt(text)["cam0_sensor"], "imx477")

    def test_spaces_around_equals_are_recognised(self):
        text = config_txt([
            CAMERA_SECTION_BEGIN, "", "camera_auto_detect=1",
            "dtoverlay = imx477,cam0", "", CAMERA_SECTION_END,
        ])

        self.assertEqual(parse_config_txt(text)["cam0_sensor"], "imx477")

    def test_a_trailing_inline_comment_is_left_unrecognised_on_purpose(self):
        """The Raspberry Pi firmware's config.txt parser has no inline-comment
        syntax -- a line shaped like this is a broken overlay value on the
        real hardware too, not a clean one with a comment. Treating it as
        clean here would silently disagree with what actually loads at boot."""
        text = config_txt([
            CAMERA_SECTION_BEGIN, "", "camera_auto_detect=1",
            "dtoverlay=imx477,cam0  # switched from imx283", "", CAMERA_SECTION_END,
        ])

        self.assertEqual(parse_config_txt(text)["cam0_sensor"], "none")


if __name__ == "__main__":
    unittest.main()
