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

from module.simple_gui import _log_badge_text, LOG_BADGE_COLOR, SDR_BADGE_COLOR, HDR_BADGE_COLOR


class LogBadgeTextTests(unittest.TestCase):
    def test_off_or_missing_target_hides_the_badge(self):
        self.assertEqual(_log_badge_text(0), "")
        self.assertEqual(_log_badge_text(None), "")
        self.assertEqual(_log_badge_text(""), "")
        self.assertEqual(_log_badge_text("garbage"), "")

    def test_resolved_target_renders_log_prefixed_text(self):
        self.assertEqual(_log_badge_text(10), "LOG10")
        self.assertEqual(_log_badge_text(12), "LOG12")
        # Redis round-trips values as strings.
        self.assertEqual(_log_badge_text("10"), "LOG10")
        self.assertEqual(_log_badge_text("12"), "LOG12")

    def test_badge_colour_is_distinct_from_cam_box_grey(self):
        # (136, 136, 136) is the plain CAM-section box grey (draw_left_sections
        # BOX_COLOR) -- the badge must not blend into ordinary CAM boxes.
        self.assertNotEqual(LOG_BADGE_COLOR, (136, 136, 136))
        # And it should read as a light-grey badge like the HDR state, not
        # the darker SDR one -- matches the plan's "light grey" spec.
        self.assertEqual(LOG_BADGE_COLOR, HDR_BADGE_COLOR)
        self.assertNotEqual(LOG_BADGE_COLOR, SDR_BADGE_COLOR)


if __name__ == "__main__":
    unittest.main()
