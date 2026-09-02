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

import logging
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

    def get_space_left(self):
        return self.space_left


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


# The keys a no-camera boot must leave exactly as it found them. Acceptance
# item 6 of the C3 brief: capture before and after, diff, do not assume.
OPERATOR_STATE_KEYS = (
    ParameterKey.SENSOR_MODE,
    ParameterKey.FPS_LAST,
    ParameterKey.FPS_USER,
    ParameterKey.FPS,
    ParameterKey.FPS_MAX,
)

WARM_REDIS = {
    ParameterKey.SENSOR_MODE.value: "6",
    ParameterKey.FPS_LAST.value: "50",
    ParameterKey.FPS_USER.value: "50",
    ParameterKey.FPS.value: "50",
    ParameterKey.FPS_MAX.value: "60",
    ParameterKey.SHUTTER_A.value: "172.8",
    ParameterKey.ZOOM.value: "1.0",
    ParameterKey.DYNAMIC_RESOLUTION_DESIRED_MODE.value: "6",
}


class WarmRedisIsNotOverwrittenTests(unittest.TestCase):
    """D4: a no-camera boot must READ stored values and never WRITE derived
    ones back. With res_modes == {} every derived value is fabricated --
    sensor_mode falls back to 0, fps_max to 1, fps_steps to [1] -- and each
    of those is what the NEXT good boot reads."""

    def test_no_writes_to_operator_state_keys(self):
        redis_controller = FakeRedis(WARM_REDIS)

        build_real_controller(redis_controller=redis_controller)

        for key in OPERATOR_STATE_KEYS:
            with self.subTest(key=key.value):
                self.assertEqual(redis_controller.writes_to(key), [])

    def test_warm_redis_comes_through_byte_identical(self):
        redis_controller = FakeRedis(WARM_REDIS)
        before = dict(redis_controller.values)

        build_real_controller(redis_controller=redis_controller)

        for key in OPERATOR_STATE_KEYS:
            with self.subTest(key=key.value):
                self.assertEqual(
                    redis_controller.values[key.value], before[key.value]
                )

    def test_stored_sensor_mode_survives_a_degraded_boot(self):
        # Hardware-confirmed 2026-09-02: "Stored sensor mode 6 not available
        # -- falling back to mode 0", persisted, and the camera then came
        # back in mode 0 on the next boot with the ribbon reattached.
        redis_controller = FakeRedis(WARM_REDIS)

        controller = build_real_controller(redis_controller=redis_controller)

        self.assertEqual(redis_controller.values[ParameterKey.SENSOR_MODE.value], "6")
        self.assertEqual(controller.sensor_mode, 6)

    def test_fps_max_and_the_step_table_do_not_collapse_to_one(self):
        # Hardware-confirmed 2026-09-02: "Changed value: fps_max = 1" then
        # "Initialized fps_steps: [1]".
        redis_controller = FakeRedis(WARM_REDIS)

        controller = build_real_controller(redis_controller=redis_controller)

        self.assertEqual(redis_controller.values[ParameterKey.FPS_MAX.value], "60")
        self.assertEqual(controller.fps_max, 60)
        self.assertNotEqual(controller.fps_steps_dynamic, [1])

    def test_stored_dynamic_resolution_desired_mode_is_left_alone(self):
        redis_controller = FakeRedis(WARM_REDIS)

        build_real_controller(redis_controller=redis_controller)

        self.assertEqual(
            redis_controller.writes_to(ParameterKey.DYNAMIC_RESOLUTION_DESIRED_MODE),
            [],
        )

    def test_boot_plus_clean_shutdown_leaves_state_identical(self):
        # The shutdown half of the chain: run_application()'s cleanup writes
        # fps_last = fps (src/main.py). With fps untouched by the degraded
        # boot that is a same-value write, so the operator's frame rate
        # survives. This is the assertion that fails if any future change
        # lets fps drift during a no-camera boot.
        redis_controller = FakeRedis(WARM_REDIS)
        before = {key.value: redis_controller.values[key.value]
                  for key in OPERATOR_STATE_KEYS}

        build_real_controller(redis_controller=redis_controller)
        redis_controller.set_value(
            ParameterKey.FPS_LAST.value,
            redis_controller.get_value(ParameterKey.FPS.value),
        )

        after = {key.value: redis_controller.values[key.value]
                 for key in OPERATOR_STATE_KEYS}
        self.assertEqual(after, before)

    def test_fresh_redis_still_seeds_the_fps_defaults(self):
        # Seed-if-absent is the other half of C3.1 and must not regress into
        # "never write anything": a genuinely empty Redis still needs its
        # startup defaults.
        redis_controller = FakeRedis()

        build_real_controller(redis_controller=redis_controller)

        self.assertEqual(redis_controller.writes_to(ParameterKey.FPS_LAST), [24])
        self.assertEqual(redis_controller.writes_to(ParameterKey.FPS_USER), [24])
        # ...but nothing mode-derived, even on a fresh Redis.
        self.assertEqual(redis_controller.writes_to(ParameterKey.SENSOR_MODE), [])
        self.assertEqual(redis_controller.writes_to(ParameterKey.FPS_MAX), [])


class WhiteBalanceCurveNoCameraTests(unittest.TestCase):
    """D3: with no sensor there is no tuning file to read, but there is still
    a generic default ct_curve. An empty wb_cg_rb_array is not a fallback --
    set_wb() then misses for every temperature and writes nothing at all."""

    def test_wb_cg_rb_array_is_populated_with_no_camera(self):
        controller = build_real_controller()

        self.assertTrue(controller.wb_cg_rb_array)
        self.assertEqual(
            sorted(controller.wb_cg_rb_array), sorted(controller.wb_steps)
        )

    def test_set_wb_actually_writes_with_no_camera(self):
        redis_controller = FakeRedis()
        controller = build_real_controller(redis_controller=redis_controller)

        controller.set_wb(controller.wb_steps[0])

        self.assertTrue(redis_controller.writes_to(ParameterKey.CG_RB))
        self.assertTrue(redis_controller.writes_to(ParameterKey.WB_USER))


class PopulateValuesAgainstRealControllerTests(unittest.TestCase):
    """D1 regression, driven the way the Pi drives it: the real
    populate_values() reading the real controller."""

    def test_populate_values_does_not_raise(self):
        redis_controller = FakeRedis()
        controller = build_real_controller(redis_controller=redis_controller)
        gui = build_gui_for(controller, redis_controller)

        values = gui.populate_values()

        self.assertTrue(values["camera_missing"])
        # No badge, no placeholder: the CAMERA NOT FOUND message in the
        # preview area is the whole indicator, and the empty sensor value
        # means the CAM box isn't drawn on either surface.
        self.assertEqual(values["sensor"], "")

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


class RecordingIsRefusedWithNoCameraTests(unittest.TestCase):
    """Review item 3: `rec` gated only on the disk, never on the camera.

    With a RAW disk mounted and no camera, every input surface -- CLI, serial,
    `POST /api/v1/cmd`, a GPIO button, a tap on the web preview area -- wrote
    `is_recording = 1`, fired the rec tone and broadcast, and armed the
    RAM-buffer watchdog, with no cinepi-raw process in existence to ever clear
    it. A phantom take that cannot end.
    """

    def _controller_with_a_mounted_disk(self):
        redis_controller = FakeRedis()
        controller = build_real_controller(redis_controller=redis_controller)
        controller.ssd_monitor.is_mounted = True
        controller.ssd_monitor.space_left = 120.0
        return controller, redis_controller

    def test_start_recording_does_not_flip_is_recording(self):
        controller, redis_controller = self._controller_with_a_mounted_disk()

        controller.start_recording()

        self.assertEqual(redis_controller.writes_to(ParameterKey.IS_RECORDING), [])

    def test_start_recording_does_not_publish_a_record_gate(self):
        controller, redis_controller = self._controller_with_a_mounted_disk()

        controller.start_recording()

        self.assertEqual(redis_controller.writes_to(ParameterKey.RECORD_CAMS), [])

    def test_the_refusal_is_logged(self):
        # Fail visible, never silent: a button press that does nothing has to
        # leave a trace, or the operator is debugging a dead rec button.
        controller, _redis = self._controller_with_a_mounted_disk()

        with self.assertLogs(level=logging.INFO) as captured:
            controller.start_recording()

        self.assertTrue(
            any("no camera" in line.lower() for line in captured.output),
            captured.output,
        )


class ResolutionChangeIsRefusedWithNoCameraTests(unittest.TestCase):
    """Review item 4: `set resolution N` with no camera killed the CLI thread.

    _normalize_sensor_mode_value() maps any mode not in res_modes to 0, then
    _apply_resolution_mode() did a plain `res_modes[value]` index -- KeyError(0)
    on an empty table. Its only handler was `except ValueError`, and neither
    CommandExecutor.handle_received_data() nor the CLI read loop catches
    anything, so the KeyError unwound out of a daemon thread. Nothing restarts
    it and nothing says so: every later CLI and serial command is silently
    ignored for the rest of the session (the-traps.md #1's shape). Over the
    web API the caller just gets an unexplained 500.
    """

    def test_set_resolution_does_not_raise(self):
        controller = build_real_controller()

        self.assertFalse(controller.set_resolution(1))

    def test_apply_resolution_mode_does_not_raise(self):
        controller = build_real_controller()

        self.assertFalse(controller._apply_resolution_mode(0))

    def test_the_refusal_is_logged(self):
        controller = build_real_controller()

        with self.assertLogs(level=logging.INFO) as captured:
            controller.set_resolution(1)

        self.assertTrue(
            any("mode table" in line.lower() for line in captured.output),
            captured.output,
        )

    def test_the_switching_flag_is_cleared_rather_than_left_latched(self):
        # A latched resolution_switching turns the GUI's RES field the
        # switching colour indefinitely, for a switch that never started.
        redis_controller = FakeRedis()
        controller = build_real_controller(redis_controller=redis_controller)

        controller.set_resolution(1)

        self.assertEqual(
            redis_controller.values.get(ParameterKey.RESOLUTION_SWITCHING.value), 0
        )


class GuiReadsOnlyAttributesTheControllerAlwaysHasTests(unittest.TestCase):
    """The generalisation of D1, so it cannot come back in a new attribute.

    `file_size` reached hardware because SimpleGUI's frame path reads it
    every frame while CinePiController only assigned it on a camera-present
    path -- and the hand-written FakeController in
    test_simple_gui_no_camera.py happened to define it, so nothing caught the
    gap. This walks the GUI frame path in the source, collects every
    `self.cinepi_controller.<attr>` it reads, and checks each one against a
    controller built by the real __init__ with no camera at all.

    A new camera-only controller attribute read from the GUI fails here at a
    desk instead of killing the GUI thread on a Pi.
    """

    GUI_FRAME_METHODS = {
        "populate_values",
        "draw_gui",
        "_refresh_slow_values",
        "load_sensor_values_from_redis",
        "estimate_resolution_in_k",
        "update_smoothed_vu_levels",
    }

    def _controller_attributes_read_by_the_gui(self):
        import ast

        source = (ROOT / "src" / "module" / "simple_gui.py").read_text()
        gui_class = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.ClassDef) and node.name == "SimpleGUI"
        )
        names = set()
        for func in gui_class.body:
            if not isinstance(func, ast.FunctionDef):
                continue
            if func.name not in self.GUI_FRAME_METHODS:
                continue
            for node in ast.walk(func):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.ctx, ast.Load)
                    and isinstance(node.value, ast.Attribute)
                    and node.value.attr == "cinepi_controller"
                    and isinstance(node.value.value, ast.Name)
                    and node.value.value.id == "self"
                ):
                    names.add(node.attr)
        return names

    def test_every_gui_read_attribute_exists_on_a_no_camera_controller(self):
        names = self._controller_attributes_read_by_the_gui()
        self.assertIn("file_size", names, "the D1 attribute should still be in scope")

        controller = build_real_controller()

        for name in sorted(names):
            with self.subTest(attribute=name):
                self.assertTrue(
                    hasattr(controller, name),
                    f"SimpleGUI reads cinepi_controller.{name} every frame, but "
                    f"CinePiController.__init__ does not assign it on a "
                    f"no-camera boot -- this is the D1 failure shape.",
                )


if __name__ == "__main__":
    unittest.main()
