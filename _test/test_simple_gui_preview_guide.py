import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("flask_socketio", types.SimpleNamespace(SocketIO=object))
sys.modules.setdefault("gpiozero", types.SimpleNamespace(CPUTemperature=object))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("sugarpie", types.SimpleNamespace(pisugar=types.SimpleNamespace()))

from module.simple_gui import _calculate_preview_guide_rect


class PreviewGuideGeometryTests(unittest.TestCase):
    def test_preview_guide_matches_sensor_aspect_after_resolution_switch(self):
        # Golden value taken from the current lores-fit formula (no
        # even-rounding on lw/lh -- see 1e3efb0a, which fixed this to match
        # _build_args()/DrmPreview::Show() and was verified against real
        # IMX585/IMX477 hardware). A prior version of this test hardcoded
        # the pre-fix, even-rounded value (1825) and was never updated when
        # that fix landed.
        self.assertEqual(
            _calculate_preview_guide_rect(
                frame_width=1920,
                frame_height=1080,
                sensor_width=3856,
                sensor_height=2180,
            ),
            [93, 48, 1826, 1030],
        )

    def test_preview_guide_adapts_to_anamorphic_preview_height(self):
        # Todo batch 2026-09-27, issue 4: compute_preview_geometry()'s `-p`
        # window is now sized from the same desqueezed aspect as the lores
        # buffer it frames (previously the window used the un-desqueezed
        # aspect alone). For this particular mode the un-desqueezed aspect
        # (1928/1090 ~= 1.77) is already close to the 1920x1080 canvas's own
        # padded-area ratio, so the window was already width-bound before
        # and after the fix and the visible rect barely moves -- off by a
        # rounding pixel or two, not the mode where the fix matters
        # visually (see test_preview_geometry.py's
        # ComputePreviewGeometryPreviewWindowAnamorphicTests for a mode
        # where the window was genuinely too narrow before this fix).
        self.assertEqual(
            _calculate_preview_guide_rect(
                frame_width=1920,
                frame_height=1080,
                sensor_width=1928,
                sensor_height=1090,
                anamorphic_factor=1.33,
            ),
            [93, 170, 1826, 909],
        )


if __name__ == "__main__":
    unittest.main()
