"""Phase 2: the colour-JPEG thumbnail mode and the four-way choice.

Covers what test_thumbnail_startup_values.py (the parser,
thumbnail_startup_value()) and test_frame_size_model.py
(thumbnail_plane_bytes(), _recompute_file_size()) do not: the
settings-editor-facing pieces -- thumbnail_choice_labels() (sensor_detect.py),
set_thumbnail() accepting "jpeg", and the settings-editor route actually
rendering four options with the current camera's size baked into their text.
"""

import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.sensor_detect import SensorDetect, thumbnail_choice_labels
from module.cinepi_controller import CinePiController
from module.redis_controller import ParameterKey


class ThumbnailChoiceLabelsTests(unittest.TestCase):
    def test_four_values_in_order(self):
        choices = thumbnail_choice_labels(1280, 720, 1)
        self.assertEqual([value for value, _ in choices], ["off", "mono", "colour", "jpeg"])

    def test_labels_carry_the_computed_byte_figures(self):
        # Shift 1 (640x360): the exact worked example the operator's brief
        # states -- mono 230 KB, jpeg "10-25 KB". If these figures ever stop
        # matching thumbnail_plane_bytes()'s own formula, this is the test
        # that catches the label silently drifting from what a take costs.
        choices = dict(thumbnail_choice_labels(1280, 720, 1))
        self.assertIn("640×360", choices["mono"])
        self.assertIn("230 KB", choices["mono"])
        self.assertIn("640×360", choices["colour"])
        self.assertIn("691 KB", choices["colour"])
        self.assertIn("640×360", choices["jpeg"])
        self.assertIn("10–25 KB", choices["jpeg"])
        self.assertIn("0 B", choices["off"])

    def test_labels_track_shift(self):
        # Same camera, different thumbnail_size -- every label's dimensions
        # and bytes must follow, not just repeat the shift-1 numbers.
        s0 = dict(thumbnail_choice_labels(1280, 720, 0))
        s2 = dict(thumbnail_choice_labels(1280, 720, 2))
        self.assertIn("1280×720", s0["mono"])
        self.assertIn("320×180", s2["mono"])
        self.assertIn("58 KB", s2["mono"])   # 320*180 = 57,600 B -> 58 KB
        self.assertIn("173 KB", s2["colour"])  # 320*180*3 = 172,800 B -> 173 KB

    def test_labels_follow_the_actual_lores_plane_not_just_1280(self):
        # ClearHDR's 1256-wide lores plane (ihe operator's own camera):
        # dimensions must reflect it, not a hardcoded 1280.
        choices = dict(thumbnail_choice_labels(1256, 720, 0))
        self.assertIn("1256×720", choices["mono"])

    def test_encode_cost_is_the_measured_figure_and_rises_left_to_right(self):
        # The labels quote the 2026-09-13 benchmark, not adjectives: an
        # operator trading CPU for bytes needs the number. Parsed back out of
        # the prose so a formatting change cannot quietly drop it.
        choices = dict(thumbnail_choice_labels(1280, 720, 1))
        self.assertIn("no extra encode time", choices["off"])
        ms = {}
        for mode in ("mono", "colour", "jpeg"):
            found = re.search(r"\+(\d+\.\d) ms per frame \(\+(\d+)%\)", choices[mode])
            self.assertIsNotNone(found, f"{mode} label carries no measured cost: {choices[mode]}")
            ms[mode] = float(found.group(1))
        self.assertLess(ms["mono"], ms["colour"])
        self.assertLess(ms["colour"], ms["jpeg"])

    def test_a_size_with_no_measurement_says_so_rather_than_inventing_one(self):
        # Shift 0 was never benchmarked. The label may fall back to the
        # nearest measured size, but it must not present that number as if it
        # had been observed at this one.
        choices = dict(thumbnail_choice_labels(1280, 720, 0))
        self.assertIn("nearest measured size", choices["jpeg"])
        # ...while a measured size states it flatly, with no hedge.
        self.assertNotIn("nearest measured size",
                         dict(thumbnail_choice_labels(1280, 720, 1))["jpeg"])


class FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value, *, force=False):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value


class FakeSensorDetect:
    def __init__(self):
        self.res_modes = {
            0: {"width": 3840, "height": 2160, "bit_depth": 12, "hdr": False},
        }

    def _calc_lores(self, sensor_w, sensor_h):
        return SensorDetect._calc_lores(None, sensor_w, sensor_h)

    def resolve_effective_bit_depth(self, _camera_name, native_bit_depth, *, log_requested=False, hdr=False):
        return native_bit_depth


class SetThumbnailAcceptsWordsTests(unittest.TestCase):
    """set_thumbnail() must go through parse_thumbnail_mode(), so it takes
    the same words settings.jsonc now does -- not just 0-2 the way it did
    before Phase 2."""

    def controller(self):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = FakeRedis()
        controller.sensor_detect = FakeSensorDetect()
        controller.current_sensor = "imx585"
        controller.sensor_mode = 0
        controller.settings = {
            "sensors": {"cam0": {"log_encode": False}, "cam1": {}},
            "image_capture": {},
        }
        return controller

    def test_set_thumbnail_jpeg_writes_3(self):
        controller = self.controller()
        controller.set_thumbnail("jpeg")
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.THUMBNAIL.value), 3
        )

    def test_set_thumbnail_accepts_case_and_whitespace(self):
        controller = self.controller()
        controller.set_thumbnail(" JPEG ")
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.THUMBNAIL.value), 3
        )

    def test_set_thumbnail_still_accepts_ints(self):
        controller = self.controller()
        controller.set_thumbnail(2)
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.THUMBNAIL.value), 2
        )

    def test_set_thumbnail_rejects_garbage_without_writing(self):
        controller = self.controller()
        with mock.patch("module.cinepi_controller.logging.error") as log_error:
            controller.set_thumbnail("banana")
        log_error.assert_called_once()
        self.assertIsNone(
            controller.redis_controller.get_value(ParameterKey.THUMBNAIL.value)
        )

    def test_set_thumbnail_jpeg_recomputes_file_size_with_mode_3(self):
        controller = self.controller()
        controller.redis_controller = FakeRedis({
            ParameterKey.THUMBNAIL_SIZE.value: "1",
        })
        controller.set_thumbnail("jpeg")
        # 4K 12-bit raw (12,441,600) + jpeg budget at 640x360
        # (int(640*360*0.15) = 34,560) + 1,024 overhead = 12,477,184 B.
        expected_mb = round((12441600 + 34560 + 1024) / 1_000_000, 2)
        self.assertEqual(controller.file_size, expected_mb)


class _RouteFakeSensorDetect:
    """Just enough of SensorDetect for _current_thumbnail_editor_context()
    (settings_editor.py): res_modes and the real, unstubbed _calc_lores()."""

    def __init__(self, res_modes):
        self.res_modes = res_modes

    def _calc_lores(self, sensor_w, sensor_h):
        return SensorDetect._calc_lores(None, sensor_w, sensor_h)


class _RouteFakeController:
    def __init__(self, sensor_mode, res_modes):
        self.sensor_mode = sensor_mode
        self.sensor_detect = _RouteFakeSensorDetect(res_modes)


class SettingsEditorThumbnailToggleTests(unittest.TestCase):
    """The settings-editor "/" route renders ONE on/off toggle over
    image_capture.thumbnail (operator decision 2026-09-13), plus the hidden
    inputs that actually carry both thumbnail keys into a save.

    What these cover that a template-body assertion could not: that the cost
    line really comes from thumbnail_choice_labels() sized for THIS camera
    (a Jinja typo or a hardcoded string would pass a static check), and that
    thumbnail_size is still carried -- a key the form drops is a key deleted
    from settings.jsonc on the next save, taking every comment in the file
    with it (B-2)."""

    def _client(self, *, controller=None, redis_controller=None):
        # Same minimal-app pattern as test_settings_editor_sensor_db.py.
        _APP_PKG = types.ModuleType("module.app")
        _APP_PKG.__path__ = [str(ROOT / "src" / "module" / "app")]
        sys.modules.setdefault("module.app", _APP_PKG)

        from flask import Flask
        from module.app.settings_editor import settings_editor_bp

        app = Flask(__name__)
        app.config["SETTINGS"] = {"image_capture": {}}
        if controller is not None:
            app.config["CINEPI_CONTROLLER"] = controller
        if redis_controller is not None:
            app.config["REDIS_CONTROLLER"] = redis_controller
        app.register_blueprint(settings_editor_bp)
        return app.test_client()

    def test_the_card_is_a_toggle_and_both_keys_are_still_carried(self):
        html = self._client().get("/settings-editor/").get_data(as_text=True)
        # The toggle itself carries no data-path -- buildState() must not see
        # it, or a boolean would land in settings.jsonc where a word belongs.
        self.assertIn('id="f-thumb-toggle"', html)
        self.assertNotIn('class="toggle" id="f-thumb-toggle" role="switch" data-path', html)
        # Both keys reach a save through hidden inputs.
        self.assertIn('data-path="image_capture.thumbnail"', html)
        self.assertIn('data-path="image_capture.thumbnail_size"', html)
        # And the mode picker is gone: no per-mode <option> anywhere.
        for value in ("mono", "colour", "jpeg"):
            self.assertNotIn(f'<option value="{value}"', html)
        self.assertNotIn("[missing text:", html)

    def test_the_cost_line_is_this_cameras_own_number(self):
        # A ClearHDR camera (3840x2200) has a 1256-wide lores plane, so at the
        # shipped half size the thumbnail is 628x360 -- not the 640x360 the
        # no-camera fallback would produce. A hardcoded cost string, or a route
        # still using the fallback plane, fails exactly here.
        controller = _RouteFakeController(
            sensor_mode=0,
            res_modes={0: {"width": 3840, "height": 2200, "bit_depth": 16, "hdr": True}},
        )
        html = self._client(controller=controller).get("/settings-editor/").get_data(as_text=True)
        self.assertIn("628×360", html)
        self.assertNotIn("640×360", html)

    def test_the_cost_line_follows_the_live_thumbnail_size(self):
        # "Redis first, settings.jsonc second": a live thumbnail_size=0 must
        # show the full-lores cost, even though the shipped default is 1.
        controller = _RouteFakeController(
            sensor_mode=0,
            res_modes={0: {"width": 3840, "height": 2160, "bit_depth": 12, "hdr": False}},
        )
        redis_controller = FakeRedis({ParameterKey.THUMBNAIL_SIZE.value: "0"})
        html = self._client(controller=controller, redis_controller=redis_controller).get(
            "/settings-editor/"
        ).get_data(as_text=True)
        self.assertIn("1280×720", html)
        self.assertNotIn("640×360", html)


if __name__ == "__main__":
    unittest.main()