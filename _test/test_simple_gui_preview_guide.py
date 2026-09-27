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
        # aspect alone).
        #
        # The window this mode gets DID move a long way -- 1732x979 before,
        # 1732x736 after, because 1.77 x 1.33 = 2.35 is far from the raw
        # 1.77 the old code used. What barely moves is the rect this
        # function returns, because that wraps the PICTURE and not the
        # window: at 1.77 the buffer was already wider than the old window's
        # shape, so Show() letterboxed it to 1732x736 and left 243 rows of
        # the window unused. The fix removes that dead band rather than
        # enlarging the picture -- 1732x736 becomes 1730x736, off by the
        # rounding pixel the pillarbox branch now takes instead of the
        # letterbox one.
        #
        # So this golden case pins "the fix did not disturb an
        # already-width-bound mode", not "the fix does nothing". The picture
        # genuinely grows on a mode whose old window was narrower than the
        # padded area -- see test_preview_geometry.py's
        # ComputePreviewGeometryPreviewWindowAnamorphicTests, which covers a
        # 4:3 mode for exactly that reason.
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
