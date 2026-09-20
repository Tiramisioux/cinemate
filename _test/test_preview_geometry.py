"""WP-CM-1 (findings C3, M2): one shared geometry helper for the live
preview, used by SensorDetect.get_lores_width()/get_lores_height(),
CinePiProcess._build_args() and simple_gui._calculate_preview_guide_rect(),
instead of three copies of the same arithmetic.

Before this fix, two bugs came from the duplicated math:

- C3: SensorDetect._calc_lores() hard-coded `lh = min(720, ah)` with no
  floor on the *mode's own* height, so a mode shorter than 720 rows (e.g.
  640x360) asked for a taller lores stream than the mode delivers --
  cinepi-raw's ConfigureVideo throws "Low res image larger than raw image".
- M2: CinePiProcess._build_args() computed aspect from the mode's
  *transport* width/height, which for a RAW16 ClearHDR mode includes the
  optical-black padding rows (e.g. 3840x2200 transport for a 3840x2160
  active image) -- so the preview came out slightly stretched and no
  longer excluded the padding.

Both are exercised here through the shared helper, compute_preview_geometry()
in module.sensor_detect: aspect comes from crop_width/crop_height when the
driver reported them (M2), and the lores stream is clamped to the mode's own
width/height, not just to the padded canvas (C3).
"""

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("gpiozero", types.SimpleNamespace(CPUTemperature=object))
sys.modules.setdefault("psutil", types.SimpleNamespace())

from module.sensor_detect import SensorDetect, compute_preview_geometry


# Canvas used throughout: the 1920x1080 default HDMI canvas with the
# established 94/50 padding (PREVIEW_PADDING_X/Y in simple_gui.py), matching
# every caller's own default.
CANVAS_W, CANVAS_H = 1920, 1080


class ComputePreviewGeometryLoresTests(unittest.TestCase):
    """The lores-stream half of the shared helper's contract -- the cases
    WP-CM-1 names as the specification."""

    def _lores(self, mode):
        geometry = compute_preview_geometry(mode, CANVAS_W, CANVAS_H)
        return geometry["lores_width"], geometry["lores_height"]

    def test_clearhdr_4k_uses_the_active_crop_not_the_padded_transport(self):
        # 3840x2200 transport carrying a 3840x2160 active image (M2). Using
        # the padded transport height (2200) for aspect gives 3840/2200 and
        # a lores width of 1256/1257, not the correct 16:9 1280.
        mode = {"width": 3840, "height": 2200, "crop_width": 3840, "crop_height": 2160}
        self.assertEqual(self._lores(mode), (1280, 720))

    def test_1440_clearhdr_window_uses_the_active_crop(self):
        # 1440x1100 transport carrying a 1440x1080 4:3 active image.
        mode = {"width": 1440, "height": 1100, "crop_width": 1440, "crop_height": 1080}
        self.assertEqual(self._lores(mode), (960, 720))

    def test_a_mode_shorter_than_720_rows_is_not_enlarged(self):
        # C3: this used to come back (1280, 720) -- taller AND wider than
        # the 640x360 mode itself, which cinepi-raw's ConfigureVideo refuses.
        mode = {"width": 640, "height": 360, "crop_width": 640, "crop_height": 360}
        self.assertEqual(self._lores(mode), (640, 360))

    def test_a_small_4_3_mode_is_not_enlarged(self):
        mode = {"width": 400, "height": 300, "crop_width": 400, "crop_height": 300}
        self.assertEqual(self._lores(mode), (400, 300))

    def test_stock_sensor_with_no_crop_annotation_falls_back_to_its_own_ratio(self):
        # imx477's 120fps mode: no crop annotation at all (DEC-4 -- a stock
        # sensor reports none), so aspect falls back to width/height, same
        # as before this fix (this mode is unaffected either way: it is
        # well above the 720-line/1280-wide floor in both directions).
        mode = {"width": 1332, "height": 990}
        self.assertEqual(self._lores(mode), (968, 720))

    def test_imx296_with_no_crop_annotation_falls_back_to_its_own_ratio(self):
        mode = {"width": 1456, "height": 1088}
        self.assertEqual(self._lores(mode), (963, 720))

    def test_anamorphic_factor_still_applies_before_the_clamp(self):
        mode = {"width": 1928, "height": 1090}
        geometry = compute_preview_geometry(mode, CANVAS_W, CANVAS_H, anamorphic_factor=1.33)
        # Same arithmetic _build_args()/_calculate_preview_guide_rect() used
        # before this fix (no even-rounding here -- that stays a job for
        # SensorDetect._calc_lores()'s own two callers, not this core).
        self.assertEqual(geometry["lores_width"], 1693)


class CalcLoresBackwardCompatTests(unittest.TestCase):
    """SensorDetect._calc_lores(self, sensor_w, sensor_h) is called unbound
    (self=None) from three other test files -- its signature and its
    even-rounding must not change."""

    def test_calc_lores_now_clamps_to_the_passed_in_height(self):
        # Previously (960, 720): buggy, taller than the 400x300 mode itself.
        self.assertEqual(SensorDetect._calc_lores(None, 400, 300), (400, 300))

    def test_calc_lores_unaffected_for_a_mode_already_taller_than_720(self):
        self.assertEqual(SensorDetect._calc_lores(None, 3840, 2160), (1280, 720))


if __name__ == "__main__":
    unittest.main()
