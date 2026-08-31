"""_publish_resolution_gui_state() must publish the hdr Redis key.

Since 87fa315 cinemate no longer writes the wide_dynamic_range subdev control,
so the hdr key IS the entire remaining contract between choosing a mode and
ClearHDR engaging: cinepi_multi reads it to decide whether the launch line
carries --hdr sensor, and _resolution_change_needs_restart() reads it to decide
whether the switch needs a relaunch at all.

This is deliberately behavioural. The first version of this guard asserted on
the *source text* of the method and passed both with the publishing lines
commented out and against the pre-removal tree -- it pinned nothing.
"""

import sys
import types
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.cinepi_controller import CinePiController
from module.redis_controller import ParameterKey

# The harness shape is shared with test_cinepi_controller_resolution_gui.py.
from test_cinepi_controller_resolution_gui import FakeRedis, FakeSensorDetect


def controller(hdr_mode: bool):
    c = CinePiController.__new__(CinePiController)
    c.redis_controller = FakeRedis()
    sd = FakeSensorDetect()
    # Mark mode 1 as a ClearHDR mode so both branches are reachable.
    sd.res_modes[1] = dict(sd.res_modes[1])
    sd.res_modes[1]["hdr"] = hdr_mode
    c.sensor_detect = sd
    c.current_sensor = "imx585"
    c.sensor_mode = 1
    c.settings = {"camera": {"cam0": {"log_encode": False}, "cam1": {}}}
    c.dynamic_resolution_enabled = False
    c.dynamic_resolution_desired_mode = 1
    c.dynamic_resolution_active = False
    c.fps_steps = [24, 25]
    c.fps_steps_dynamic = [24, 25]
    c.fps_free = False
    c.current_fps = 24
    c.fps = 24
    c.shutter_a_sync_mode = 0
    c.notifications = []
    c.cinepi = mock.Mock()
    c._is_recording = lambda: False
    c.calculate_dynamic_shutter_angles = lambda _fps: [180]
    c.initialize_fps_steps = lambda _steps: None
    c.update_steps = lambda: None
    c._notify_resolution_change = c.notifications.append
    c._resolution_switching_timer = None
    c._resolution_switch_complete_callbacks = []

    def refresh_fps_max():
        c.fps_max = 50
        return 50

    c._refresh_fps_max = refresh_fps_max
    return c


class HdrKeyPublishedTests(unittest.TestCase):
    def _published_hdr(self, hdr_mode):
        c = controller(hdr_mode)
        c._publish_resolution_gui_state(1, c.sensor_detect.res_modes[1])
        hdr_writes = [v for k, v in c.redis_controller.sets if k == ParameterKey.HDR.value]
        self.assertTrue(
            hdr_writes,
            "_publish_resolution_gui_state must publish the hdr key -- it is the "
            "only signal cinepi_multi has for --hdr sensor.",
        )
        return hdr_writes[-1]

    def test_selecting_a_clearhdr_mode_publishes_hdr_1(self):
        self.assertEqual(self._published_hdr(True), 1)

    def test_selecting_a_plain_mode_publishes_hdr_0(self):
        self.assertEqual(self._published_hdr(False), 0)

    def test_no_subprocess_is_spawned_while_publishing(self):
        """The removed writer shelled out from exactly here. Nothing should now.

        os.path.exists is forced True: the removed writer probed
        /dev/v4l-subdevN before running v4l2-ctl, and on a machine with no
        subdev nodes it returned without ever calling subprocess.run -- which
        made an unpatched version of this assertion pass against the tree that
        still had the writer. With the probe satisfied, the old code reaches
        subprocess.run and this test fails against it, as it must.
        """
        c = controller(True)
        with mock.patch("module.cinepi_controller.os.path.exists", return_value=True), \
             mock.patch("module.cinepi_controller.subprocess.run") as run:
            c._publish_resolution_gui_state(1, c.sensor_detect.res_modes[1])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
