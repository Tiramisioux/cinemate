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
        self.assertEqual(
            _calculate_preview_guide_rect(
                frame_width=1920,
                frame_height=1080,
                sensor_width=3856,
                sensor_height=2180,
            ),
            [92, 48, 1827, 1030],
        )


if __name__ == "__main__":
    unittest.main()
