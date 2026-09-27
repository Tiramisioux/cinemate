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

from module.sensor_detect import SensorDetect, active_picture_size, compute_preview_geometry


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


class ComputePreviewGeometryPreviewWindowAnamorphicTests(unittest.TestCase):
    """Todo batch 2026-09-27, issue 4 ("anamorphic fills the web UI but not
    HDMI"). Before this fix the `-p` window was sized from the un-desqueezed
    `aspect` while the lores buffer it frames was already desqueezed
    (lores_w = lores_h * aspect * anamorphic_factor). DrmPreview::Show()
    (preview/drm_preview.cpp, read-only in cinepi-raw) fits that buffer into
    the window by preserving the BUFFER's own aspect -- so a window sized to
    the wrong (narrower) aspect just left the picture short of the padded
    canvas's own edges on whatever axis the buffer turned out wider than the
    window assumed, which reads as "not filling the screen". Sizing the
    window from the same desqueezed aspect the lores buffer already carries
    is the fix.
    """

    def _geometry(self, mode, anamorphic_factor=1.0):
        return compute_preview_geometry(mode, CANVAS_W, CANVAS_H, anamorphic_factor=anamorphic_factor)

    def test_preview_window_widens_to_the_desqueezed_aspect_not_the_raw_one(self):
        # A 4:3 mode (1600x1200, aspect 1.3333) with no anamorphic factor is
        # narrower than the padded canvas and the window is height-bound,
        # leaving margin left and right -- correct, nothing anamorphic here.
        mode = {"width": 1600, "height": 1200, "crop_width": 1600, "crop_height": 1200}
        unsqueezed = self._geometry(mode, anamorphic_factor=1.0)
        self.assertEqual(
            (unsqueezed["preview_width"], unsqueezed["preview_height"]),
            (1306, 980),
        )

        # The same sensor mode behind a 2x anamorphic lens desqueezes to
        # aspect 2.6667 -- wider than the canvas itself, so the window
        # should now be width-bound (full padded width) and shorter, not
        # still the narrow 1306-wide box the un-desqueezed aspect produced.
        squeezed = self._geometry(mode, anamorphic_factor=2.0)
        self.assertEqual(
            (squeezed["preview_width"], squeezed["preview_height"]),
            (1732, 649),
        )
        # The window's own aspect must now match what the lores buffer was
        # actually requested at -- not drift from it by the anamorphic
        # factor, which is exactly the bug being fixed here.
        window_aspect = squeezed["preview_width"] / squeezed["preview_height"]
        lores_aspect = squeezed["lores_width"] / squeezed["lores_height"]
        self.assertAlmostEqual(window_aspect, lores_aspect, delta=0.01)

    def test_preview_window_matches_the_lores_clamp_case(self):
        # Same 4:3 mode and 2x factor: lores_w = 720 * 1.3333 * 2 = 1920,
        # which exceeds max_lores_w = min(aw=1732, width=1600) = 1600, so
        # the C3 clamp recomputes lores_h from the divisor. This is the
        # "easiest place to introduce a silent aspect error" the prompt
        # warns about -- assert both the lores clamp AND the window still
        # agree on the same desqueezed aspect afterwards.
        mode = {"width": 1600, "height": 1200, "crop_width": 1600, "crop_height": 1200}
        geometry = self._geometry(mode, anamorphic_factor=2.0)
        self.assertEqual(geometry["lores_width"], 1600)
        self.assertEqual(geometry["lores_height"], 600)
        self.assertEqual(
            (geometry["preview_width"], geometry["preview_height"]),
            (1732, 649),
        )

    def test_preview_window_is_unchanged_at_the_default_anamorphic_factor(self):
        # anamorphic_factor=1.0 (the default -- no lens attached) must
        # reproduce the pre-fix arithmetic exactly, since
        # desqueezed_aspect == aspect in that case.
        mode = {"width": 3840, "height": 2200, "crop_width": 3840, "crop_height": 2160}
        geometry = self._geometry(mode, anamorphic_factor=1.0)
        self.assertEqual(
            (geometry["preview_width"], geometry["preview_height"]),
            (1732, 974),
        )


class ActivePictureSizeTests(unittest.TestCase):
    """The shared helper Round 2 introduced for Defect D/B2 -- one place for
    "what is the delivered active picture", in priority order: an explicit
    active-size annotation, then crop/binning, then crop alone, then the
    transport frame. See its own docstring in module.sensor_detect for the
    full rationale; this is the tier order asserted directly."""

    def test_explicit_active_annotation_is_used_as_is(self):
        # The annotation already IS the delivered picture -- never divided
        # by binning again, even though binning is also present here.
        mode = {
            "active_width": 2736, "active_height": 1824,
            "crop_width": 5472, "crop_height": 3648,
            "binning_x": 2, "binning_y": 2,
        }
        self.assertEqual(active_picture_size(mode, 2784, 1828), (2736.0, 1824.0))

    def test_crop_divided_by_binning_when_no_active_annotation(self):
        mode = {"crop_width": 5472, "crop_height": 3648, "binning_x": 2, "binning_y": 2}
        self.assertEqual(active_picture_size(mode, 0, 0), (2736.0, 1824.0))

    def test_asymmetric_binning_is_not_averaged_or_ignored(self):
        # Defect B2's root cause: hbin != vbin means the raw crop ratio
        # (5472/3648 = 1.5) is NOT the delivered picture's aspect. Dividing
        # each axis by its own binning factor is what makes this differ from
        # naively using the crop rectangle's own ratio.
        mode = {"crop_width": 5472, "crop_height": 3648, "binning_x": 2, "binning_y": 1}
        self.assertEqual(active_picture_size(mode, 0, 0), (2736.0, 3648.0))

    def test_crop_alone_when_binning_unknown(self):
        # A driver that reports crop but no binning at all: only ratio-
        # correct when the (unknown) binning is symmetric, but it is the
        # only evidence available, so it is used rather than discarded.
        mode = {"crop_width": 2664, "crop_height": 1980}
        self.assertEqual(active_picture_size(mode, 0, 0), (2664.0, 1980.0))

    def test_transport_fallback_when_no_geometry_at_all(self):
        # Defect D: a mode with no crop/active annotation at all (the
        # operator's Pi, on the 1:1 rows that showed 1.02:1) has nothing
        # better than the transport frame.
        mode = {}
        self.assertEqual(active_picture_size(mode, 3744, 3664), (3744.0, 3664.0))

    def test_zero_binning_does_not_divide_by_zero(self):
        # A stray/unset binning control (0) must not crash or be treated as
        # "no binning" in a way that divides by it.
        mode = {"crop_width": 3840, "crop_height": 2160, "binning_x": 0, "binning_y": 0}
        self.assertEqual(active_picture_size(mode, 0, 0), (3840.0, 2160.0))


class ComputePreviewGeometryActivePictureTests(unittest.TestCase):
    """Round 2, Defect B2: the -p window and the lores request must come
    from the delivered active picture, not from the sensor-window aspect
    (raw crop_width/crop_height) -- the two only coincide when
    binning_x == binning_y, which is what made this bug look like a pure
    aspect-mismatch pillarbox instead of a binning-direction bug."""

    def test_asymmetric_binning_uses_the_active_picture_aspect_not_the_crop_window(self):
        # crop 5472x3648 (aspect 1.5) at binning 2x1 delivers 2736x3648
        # (aspect 0.375) -- a portrait picture from a landscape crop window.
        # Before this fix, aspect was taken from the raw crop ratio (1.5)
        # and every output below would come out landscape instead.
        mode = {
            "width": 2736, "height": 3648,
            "crop_width": 5472, "crop_height": 3648,
            "binning_x": 2, "binning_y": 1,
        }
        geometry = compute_preview_geometry(mode, CANVAS_W, CANVAS_H)
        self.assertEqual(geometry["lores_width"], 540)
        self.assertEqual(geometry["lores_height"], 720)
        self.assertEqual(geometry["preview_width"], 735)
        self.assertEqual(geometry["preview_height"], 980)

    def test_explicit_active_annotation_is_preferred_over_crop_binning(self):
        # A future cinepi-raw build reports the active picture directly;
        # it must win even when crop/binning would suggest something else.
        mode = {
            "width": 2784, "height": 1828,
            "crop_width": 5472, "crop_height": 3648,
            "binning_x": 2, "binning_y": 2,
            "active_width": 2736, "active_height": 1824,
        }
        geometry = compute_preview_geometry(mode, CANVAS_W, CANVAS_H)
        # 2736/1824 == 1.5 exactly, same as the symmetric-binning crop
        # ratio here -- the point is that the code path used active_width/
        # active_height at all, checked by the previous test where they
        # differ from the raw crop ratio.
        self.assertEqual(geometry["lores_width"], 1080)
        self.assertEqual(geometry["lores_height"], 720)


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
