"""Phase 2: the colour-JPEG thumbnail mode and the four-way choice.

Covers what test_thumbnail_startup_values.py (the parser,
thumbnail_startup_value()) and test_frame_size_model.py
(thumbnail_plane_bytes(), _recompute_file_size()) do not: the
settings-editor-facing pieces -- thumbnail_choice_labels() (sensor_detect.py),
set_thumbnail() accepting "jpeg", and the settings-editor route actually
rendering four options with the current camera's size baked into their text.
"""

import json
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

from module.sensor_detect import (
    SensorDetect,
    _format_thumbnail_kb,
    thumbnail_choice_labels,
    thumbnail_plane_bytes,
)
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

    def test_cpu_words_rise_left_to_right(self):
        choices = dict(thumbnail_choice_labels(1280, 720, 1))
        self.assertIn("no CPU", choices["off"])
        self.assertIn("lightest CPU", choices["mono"])
        self.assertIn("moderate CPU", choices["colour"])
        self.assertIn("highest CPU", choices["jpeg"])


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


class SettingsEditorRouteRendersFourOptionsTests(unittest.TestCase):
    """The settings-editor "/" route must actually render thumbnail_choice_labels()'s
    four options, sized for the given camera -- not just that the function
    itself works (ThumbnailChoiceLabelsTests, above) or that the static
    template has the right data-path (a template-body assertion could not
    tell a Jinja-loop typo from a working one)."""

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

    def test_four_options_render_with_no_camera_attached(self):
        # CINEPI_CONTROLLER/SENSOR_DETECT absent from app.config entirely --
        # the degraded-boot case _current_thumbnail_editor_context() must
        # fall back from, at the fallback 1280x720 lores plane and the
        # shipped thumbnail_size default (1, half).
        html = self._client().get("/settings-editor/").get_data(as_text=True)
        self.assertIn('data-path="image_capture.thumbnail"', html)
        self.assertIn('data-path="image_capture.thumbnail_size"', html)
        for value in ("off", "mono", "colour", "jpeg"):
            self.assertIn(f'<option value="{value}"', html)
        # Fallback size (no camera) is still the shipped default, shift 1:
        # 640x360 -- present in both the mode select's labels and the size
        # select's own "Half" option text.
        self.assertIn("640×360", html)
        self.assertIn("Quarter 320×180", html)
        self.assertIn("Full lores 1280×720", html)
        self.assertIn("Half 640×360", html)
        self.assertNotIn("[missing text:", html)

    def test_labels_follow_a_real_cameras_clearhdr_lores_size(self):
        # A ClearHDR-mode camera (3840x2200) has a 1256-wide lores plane,
        # not the 16:9 1280 the no-camera fallback uses -- if the route
        # were still hardcoding 1280x720, this is the case that would
        # catch it (test_four_options_render_with_no_camera_attached alone
        # could not, since 1280 is also the correct answer there).
        controller = _RouteFakeController(
            sensor_mode=0,
            res_modes={0: {"width": 3840, "height": 2200, "bit_depth": 16, "hdr": True}},
        )
        html = self._client(controller=controller).get("/settings-editor/").get_data(as_text=True)
        self.assertIn("1256×720", html)
        self.assertNotIn("1280×720", html)

    def test_labels_follow_the_live_redis_thumbnail_size_over_the_settings_default(self):
        # "Redis first, settings.jsonc second" (_current_thumbnail_editor_context()'s
        # own docstring): a live thumbnail_size=0 must show the full-lores
        # dimensions in the mode labels, not the shipped shift-1 default,
        # even though settings.jsonc here says nothing at all.
        controller = _RouteFakeController(
            sensor_mode=0,
            res_modes={0: {"width": 3840, "height": 2160, "bit_depth": 12, "hdr": False}},
        )
        redis_controller = FakeRedis({ParameterKey.THUMBNAIL_SIZE.value: "0"})
        html = self._client(controller=controller, redis_controller=redis_controller).get(
            "/settings-editor/"
        ).get_data(as_text=True)
        self.assertIn("Greyscale 1280×720", html)
        self.assertNotIn("Greyscale 320×180", html)

    def test_every_offered_size_ships_its_own_label_set(self):
        # The whole point of the JSON blob: the mode labels must be able to
        # follow the size <select> without a reload, and without the byte
        # formula existing anywhere in JavaScript. The page therefore has to
        # carry a COMPLETE label set for every size it offers -- if the route
        # sent only the current one, the page script would silently leave
        # stale byte counts on screen the moment the size changed.
        controller = _RouteFakeController(
            sensor_mode=0,
            res_modes={0: {"width": 3840, "height": 2160, "bit_depth": 12, "hdr": False}},
        )
        html = self._client(controller=controller).get("/settings-editor/").get_data(as_text=True)
        blob = re.search(
            r'<script type="application/json" id="thumb-labels-by-size">(.*?)</script>',
            html, re.S)
        self.assertIsNotNone(blob, "the per-size label blob is missing from the page")
        by_size = json.loads(blob.group(1))
        self.assertEqual(sorted(by_size), ["0", "1", "2"])
        for shift, expected_dims in (("0", "1280×720"), ("1", "640×360"), ("2", "320×180")):
            with self.subTest(shift=shift):
                labels = by_size[shift]
                self.assertEqual([value for value, _ in labels],
                                 ["off", "mono", "colour", "jpeg"])
                # Every non-off label names that size's own dimensions, so a
                # set can never be mistaken for another size's.
                for value, label in labels:
                    if value != "off":
                        self.assertIn(expected_dims, label)

    def test_the_blobs_byte_figures_match_the_shipped_formula(self):
        # The labels an operator reads must come from the same function
        # file_size uses, not from anything restated in the page. Checked
        # against thumbnail_plane_bytes() directly rather than against a
        # hardcoded number, so this stays true if the formula ever changes.
        controller = _RouteFakeController(
            sensor_mode=0,
            res_modes={0: {"width": 3840, "height": 2160, "bit_depth": 12, "hdr": False}},
        )
        html = self._client(controller=controller).get("/settings-editor/").get_data(as_text=True)
        blob = re.search(
            r'<script type="application/json" id="thumb-labels-by-size">(.*?)</script>',
            html, re.S)
        by_size = json.loads(blob.group(1))
        for shift in (0, 1, 2):
            for mode_name, mode in (("mono", 1), ("colour", 2)):
                expected = thumbnail_plane_bytes(1280, 720, mode, shift)
                label = dict(by_size[str(shift)])[mode_name]
                with self.subTest(shift=shift, mode=mode_name):
                    # The label formats bytes as KB/MB; the formatter is the
                    # one sensor_detect uses, so compare through it.
                    self.assertIn(_format_thumbnail_kb(expected), label)

    def test_the_initial_options_are_the_default_sizes_set(self):
        # The rendered options and the blob must agree on load, or the first
        # size change would appear to alter labels that were already right.
        html = self._client().get("/settings-editor/").get_data(as_text=True)
        blob = re.search(
            r'<script type="application/json" id="thumb-labels-by-size">(.*?)</script>',
            html, re.S)
        by_size = json.loads(blob.group(1))
        for _, label in by_size["1"]:          # shift 1 == the shipped default
            self.assertIn(label, html)


if __name__ == "__main__":
    unittest.main()
