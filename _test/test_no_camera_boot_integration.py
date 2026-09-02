"""End-to-end-ish no-camera boot, through the code the Pi actually runs.

Every other no-camera test in `_test/` pokes one method on a controller built
with `CinePiController.__new__()`, or drives `SimpleGUI.populate_values()`
against a hand-written `FakeController`. Both patterns hid the same class of
bug twice on real hardware: a hand-written fake carries attributes the real
object doesn't have (`FakeController.file_size` in
test_simple_gui_no_camera.py is exactly the attribute the real controller
never assigned on a no-camera boot), and `__new__` never runs the __init__
that was supposed to assign them.

So these tests run the REAL `CinePiController.__init__` with a fake Redis and
an empty sensor mode table, and feed that real controller to the REAL
`SimpleGUI.populate_values()`. Anything __init__ forgets to assign shows up
here rather than in the GUI thread on a Pi.

`threading.Timer` is stubbed out because __init__ arms a 5 s
clear_startup_flag timer whose non-daemon thread would otherwise hold the
test process open.
"""

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

import module.cinepi_controller as cinepi_controller_module
from module.cinepi_controller import CinePiController
from module.config_loader import load_settings, DEFAULT_SETTINGS_PATH
from module.redis_controller import ParameterKey
from module.simple_gui import SimpleGUI


class FakeRedis:
    """Same contract as RedisController for the calls __init__ makes,
    including redis_controller.py's set_value(key, None) -> warn and ignore
    (that is why `sensor` keeps its previous value on a no-camera boot)."""

    def __init__(self, values=None):
        self.values = dict(values or {})
        self.sets = []
        self.redis_parameter_changed = _FakeEvent()

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value, *, force=False):
        if value is None:
            return
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value
        self.sets.append((key, value))

    def mset(self, mapping):
        for key, value in mapping.items():
            self.set_value(key, value)

    def writes_to(self, key):
        key = key.value if isinstance(key, ParameterKey) else key
        return [value for written, value in self.sets if written == key]


class _FakeEvent:
    def subscribe(self, handler):
        pass


class FakeSensorDetect:
    """No camera: camera_model is None and res_modes is {} for the whole
    session. A physically attached sensor missing from sensor_resolutions
    lands in the same state (see _apply_startup_fps's docstring)."""

    def __init__(self, res_modes=None, camera_model=None):
        self.res_modes = res_modes if res_modes is not None else {}
        self.camera_model = camera_model

    def get_gui_layout(self, camera_model, sensor_mode):
        return None

    def get_fps_max(self, camera_model, sensor_mode):
        return None

    def resolve_effective_bit_depth(self, camera, native_bit_depth, log_requested, hdr):
        return None


class FakeSSDMonitor:
    def __init__(self):
        self.mount_event = _FakeEvent()
        self.device_name = ""
        self.space_left = 120.0
        self.is_mounted = True
        self.write_speed_mb_s = 0.0

    def get_latest_recording_info(self):
        return (None, 0, 0, -1)


class _NoopTimer:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass


def build_real_controller(redis_controller=None, sensor_detect=None):
    """Construct CinePiController through its real __init__."""
    redis_controller = redis_controller if redis_controller is not None else FakeRedis()
    sensor_detect = sensor_detect if sensor_detect is not None else FakeSensorDetect()
    settings = load_settings(DEFAULT_SETTINGS_PATH)

    real_timer = cinepi_controller_module.threading.Timer
    cinepi_controller_module.threading.Timer = _NoopTimer
    try:
        controller = CinePiController(
            types.SimpleNamespace(),
            redis_controller,
            FakeSSDMonitor(),
            sensor_detect,
            iso_steps=settings["arrays"]["iso"]["steps"],
            shutter_a_steps=settings["arrays"]["shutter_a"]["steps"],
            fps_steps=settings["arrays"]["fps"]["steps"],
            wb_steps=settings["arrays"]["wb"]["steps"],
            light_hz=settings["settings"]["light_hz"],
            anamorphic_steps=settings["hdmi_display"]["preview"]["anamorphic"]["steps"],
            default_anamorphic_factor=(
                settings["hdmi_display"]["preview"]["anamorphic"]["default_factor"]
            ),
        )
    finally:
        cinepi_controller_module.threading.Timer = real_timer
    return controller


def build_gui_for(controller, redis_controller, cameras_json="[]"):
    """SimpleGUI.__new__ + the attributes populate_values() reads.

    __init__ itself is not runnable at a desk (it claims the console and
    opens the framebuffer), but populate_values() is the method that died on
    hardware, so it is the one that has to be the real one here.
    """
    gui = SimpleGUI.__new__(SimpleGUI)
    redis_controller.values.setdefault(ParameterKey.CAMERAS.value, cameras_json)
    gui.redis_controller = redis_controller
    gui.cinepi_controller = controller
    gui.ssd_monitor = controller.ssd_monitor
    gui.dmesg_monitor = types.SimpleNamespace(undervoltage_flag=False)
    gui.battery_monitor = types.SimpleNamespace(battery_level=None, charging=False)
    gui.sensor_detect = controller.sensor_detect
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


class RealInitNoCameraTests(unittest.TestCase):
    """D1: the real __init__ must leave every attribute the GUI reads
    assigned, on a boot with no camera at all."""

    def test_init_does_not_raise_with_no_camera(self):
        controller = build_real_controller()
        self.assertIsNone(controller.current_sensor)

    def test_file_size_is_assigned_and_usable(self):
        # _recompute_file_size() returns before its single assignment when
        # res_modes is empty. Without an __init__ default the attribute does
        # not exist, and populate_values() raises AttributeError on the very
        # first GUI frame (hardware-confirmed 2026-09-02).
        controller = build_real_controller()

        self.assertTrue(hasattr(controller, "file_size"))
        self.assertIsInstance(controller.file_size, (int, float))
        self.assertEqual(controller.file_size, 0)

    def test_no_camera_boot_does_not_publish_a_file_size(self):
        redis_controller = FakeRedis()

        build_real_controller(redis_controller=redis_controller)

        self.assertEqual(redis_controller.writes_to(ParameterKey.FILE_SIZE), [])


class PopulateValuesAgainstRealControllerTests(unittest.TestCase):
    """D1 regression, driven the way the Pi drives it: the real
    populate_values() reading the real controller."""

    def test_populate_values_does_not_raise(self):
        redis_controller = FakeRedis()
        controller = build_real_controller(redis_controller=redis_controller)
        gui = build_gui_for(controller, redis_controller)

        values = gui.populate_values()

        self.assertTrue(values["camera_missing"])
        self.assertEqual(values["sensor"], "NO CAM")

    def test_disk_space_shows_free_space_not_a_fabricated_duration(self):
        # With no usable frame size, a minutes-remaining figure would be a
        # ZeroDivisionError -- or, worse, a plausible duration computed from
        # a sensor that isn't attached. Show the free space itself.
        redis_controller = FakeRedis()
        controller = build_real_controller(redis_controller=redis_controller)
        gui = build_gui_for(controller, redis_controller)

        values = gui.populate_values()

        self.assertEqual(values["disk_space"], "120 GB")

    def test_disk_space_still_shows_minutes_when_a_frame_size_is_known(self):
        redis_controller = FakeRedis()
        controller = build_real_controller(redis_controller=redis_controller)
        controller.file_size = 5.0  # MB per frame, as _recompute_file_size sets it
        gui = build_gui_for(controller, redis_controller)

        values = gui.populate_values()

        self.assertTrue(values["disk_space"].endswith("MIN"))


if __name__ == "__main__":
    unittest.main()
