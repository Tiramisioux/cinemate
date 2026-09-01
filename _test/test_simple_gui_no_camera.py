import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("flask_socketio", types.SimpleNamespace(SocketIO=object))
sys.modules.setdefault("gpiozero", types.SimpleNamespace(CPUTemperature=object))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))
sys.modules.setdefault("sugarpie", types.SimpleNamespace(pisugar=types.SimpleNamespace()))

from module.simple_gui import SimpleGUI
from module.redis_controller import ParameterKey


class FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)


class FakeController:
    def __init__(self):
        self.exposure_time_fractions = "1/48"
        self.iso_lock = False
        self.shutter_a_nom_lock = False
        self.fps_lock = False
        self.shutter_a_sync_mode = 0
        self.parameters_lock = False
        self.file_size = 100
        self.fps = 24
        self.iso_steps = [100, 200]
        self.shutter_a_steps_dynamic = [180]
        self.shutter_a_steps = [180]
        self.fps_steps_dynamic = [24]
        self.fps_steps = [24]
        self.wb_steps = [5600]
        self.all_lock = False
        self.fps_double = False
        self.dynamic_resolution_enabled = True
        self.dynamic_resolution_active = False
        self.dynamic_resolution_desired_mode = 0
        self.sensor_mode = 0
        self.iso_free = False
        self.shutter_a_free = False
        self.fps_free = False
        self.wb_free = False
        self.hdr_threshold_low_free = False
        self.hdr_threshold_high_free = False
        self.hdr_blend_free = False
        self.hdr_gain_adder_free = False


class FakeSensorDetect:
    def __init__(self, res_modes=None, camera_model=None):
        self.res_modes = res_modes if res_modes is not None else {}
        self.camera_model = camera_model


class FakeSSDMonitor:
    def __init__(self):
        self.device_name = ""
        self.space_left = 0
        self.is_mounted = False
        self.write_speed_mb_s = 0

    def get_latest_recording_info(self):
        return (None, 0, 0, -1)


def make_gui(cameras_json="[]"):
    gui = SimpleGUI.__new__(SimpleGUI)
    gui.redis_controller = FakeRedis({ParameterKey.CAMERAS.value: cameras_json})
    gui.cinepi_controller = FakeController()
    gui.ssd_monitor = FakeSSDMonitor()
    gui.dmesg_monitor = types.SimpleNamespace(undervoltage_flag=False)
    gui.battery_monitor = types.SimpleNamespace(battery_level=None, charging=False)
    gui.sensor_detect = FakeSensorDetect(res_modes={}, camera_model=None)
    gui.redis_listener = types.SimpleNamespace(colorTemp=5600)
    gui.usb_monitor = types.SimpleNamespace(
        usb_mic=None, usb_keyboard=None, audio_monitor=None
    )
    gui.serial_handler = types.SimpleNamespace(serial_connected=False)
    gui.settings = {}
    gui._cached_cams_json = None
    gui._cached_cams = []
    gui._slow_values = {}
    gui._last_slow_refresh_ts = 0.0
    gui.slow_refresh_interval = 1.0
    gui.vu_smoothed = []
    gui.vu_peaks = []
    gui.draw_right_col = False
    gui.color_mode = "normal"
    gui.current_background_color = "black"
    gui.show_buffer_vu = True
    gui.vu_meter_hatch_lines = True
    gui._frames_off_sync_prev = False
    gui._sync_flash_until = 0.0
    gui.background_color_changed = False
    gui.disp_width = 0
    gui.disp_height = 0
    gui.fb = None
    gui._font_cache = {}
    gui.setup_resources()
    return gui


class FakeFramebuffer:
    def __init__(self, size=(1920, 1080)):
        self.size = size

    def show(self, image):
        pass


class PopulateValuesNoCameraTests(unittest.TestCase):
    """C3.3: with cameras == "[]" (the shared state signal both GUI surfaces
    ride -- start_all() writes it before aborting), populate_values() must
    flag the degraded state and never throw, even with fps_user absent from
    a fresh Redis (SimpleGUI.run() has no per-iteration exception catch)."""

    def test_sets_camera_missing_and_no_cam_sensor(self):
        gui = make_gui(cameras_json="[]")

        values = gui.populate_values()

        self.assertTrue(values["camera_missing"])
        self.assertEqual(values["sensor"], "NO CAM")

    def test_does_not_throw_with_fps_user_absent(self):
        gui = make_gui(cameras_json="[]")
        self.assertNotIn(ParameterKey.FPS_USER.value, gui.redis_controller.values)

        values = gui.populate_values()

        self.assertEqual(values["fps"], 24)

    def test_draw_gui_does_not_throw_with_width_height_unset(self):
        # Audit finding: draw_gui() re-reads WIDTH/HEIGHT straight from Redis
        # (not the already-guarded self.width/self.height populate_values()
        # just set) to get the freshest sensor resolution for the preview
        # guide rect. On a genuinely fresh Redis -- no camera has ever
        # reported these -- that used to be int(None). draw_gui() runs every
        # frame from run()'s draw loop, which has no per-iteration exception
        # catch, same risk class as the fps_user guard above.
        gui = make_gui(cameras_json="[]")
        gui.fb = FakeFramebuffer()
        gui.disp_width = 1920
        gui.disp_height = 1080

        values = gui.populate_values()
        self.assertNotIn(ParameterKey.WIDTH.value, gui.redis_controller.values)
        self.assertNotIn(ParameterKey.HEIGHT.value, gui.redis_controller.values)

        gui.draw_gui(values)  # must not raise

        self.assertEqual(gui.width, 1920)
        self.assertEqual(gui.height, 1080)

    def test_draw_no_camera_message_renders_the_power_off_warning(self):
        from PIL import Image, ImageDraw

        gui = make_gui(cameras_json="[]")
        image = Image.new("RGBA", (1920, 1080), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        rect = (94, 50, 1826, 1030)  # a realistic outline_rect

        gui._draw_no_camera_message(draw, rect, 1.0, 1.0)

        # Smoke check: something other than the black background was
        # actually painted inside the rect (not just a no-op).
        region = image.crop(rect)
        blank = Image.new(region.mode, region.size, (0, 0, 0, 255))
        self.assertNotEqual(region.tobytes(), blank.tobytes())

    def test_draw_gui_shows_no_camera_message_only_when_camera_missing(self):
        gui = make_gui(
            cameras_json='[{"port": "cam0", "model": "imx585", "mono": false}]'
        )
        gui.fb = FakeFramebuffer()
        gui.disp_width = 1920
        gui.disp_height = 1080
        calls = []
        gui._draw_no_camera_message = lambda *a, **k: calls.append(a)

        values = gui.populate_values()
        gui.draw_gui(values)

        self.assertEqual(calls, [])

    def test_camera_present_leaves_camera_missing_false(self):
        gui = make_gui(
            cameras_json='[{"port": "cam0", "model": "imx585", "mono": false}]'
        )

        values = gui.populate_values()

        self.assertFalse(values["camera_missing"])
        self.assertEqual(values["sensor"], "585")


if __name__ == "__main__":
    unittest.main()
