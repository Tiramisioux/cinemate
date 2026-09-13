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
    compute_frame_size_mb,
    thumbnail_plane_bytes,
    THUMBNAIL_JPEG_BUDGET_BYTES_PER_PIXEL,
)
from module.cinepi_controller import CinePiController
from module.redis_controller import ParameterKey


class ThumbnailPlaneBytesTests(unittest.TestCase):
    """Pins the same seven geometry cases as cinepi-raw's
    tests/dng_thumbnail_test.cpp, through the Python mirror, plus one more
    (shift-1 mono) that is not one of the compiled-in defaults on either
    side but is still worth a fixed point. NOTE the argument order here is
    (lores_w, lores_h, mode, shift) -- see thumbnail_plane_bytes()'s own
    docstring for why that is the opposite of thumbnail_geometry()'s
    (lores_w, lores_h, shift, mode) on the C++ side."""

    def test_full_lores_colour(self):
        # 16:9 lores plane, shift 0, colour -- FINDINGS.md §2's full-size cost.
        self.assertEqual(thumbnail_plane_bytes(1280, 720, 2, 0), 2764800)

    def test_clearhdr_lores_colour(self):
        # ClearHDR lores plane (1256x720), shift 0, colour -- the operator's
        # 2026-09-13 example take, exactly what dng_ifd_dump.py reported.
        self.assertEqual(thumbnail_plane_bytes(1256, 720, 2, 0), 2712960)

    def test_shift1_colour(self):
        self.assertEqual(thumbnail_plane_bytes(1280, 720, 2, 1), 691200)

    def test_shift2_colour(self):
        self.assertEqual(thumbnail_plane_bytes(1280, 720, 2, 2), 172800)

    def test_shift0_mono(self):
        # Mono: same plane, spp 1 -- a third of the colour byte count.
        self.assertEqual(thumbnail_plane_bytes(1280, 720, 1, 0), 921600)

    def test_shift1_mono(self):
        self.assertEqual(thumbnail_plane_bytes(1280, 720, 1, 1), 230400)

    def test_mode_off_is_zero_bytes(self):
        self.assertEqual(thumbnail_plane_bytes(1280, 720, 0, 3), 0)

    def test_shift12_collapses_but_never_to_zero(self):
        # The floor that keeps an over-large thumbnail_size from ever
        # producing a 0-byte-dimension thumbnail (max(1, dim >> shift)).
        self.assertEqual(thumbnail_plane_bytes(1272, 720, 2, 12), 3)

    def test_mode3_jpeg_is_the_budget_estimate_not_the_spp_formula(self):
        # Mode 3 (colour JPEG): int(w*h*BUDGET), a conservative ESTIMATE --
        # not width*height*3 the way uncompressed colour (mode 2) is. Pins
        # the same three shifts tests/dng_thumbnail_test.cpp's mode-3 cases
        # do, through THUMBNAIL_JPEG_BUDGET_BYTES_PER_PIXEL rather than
        # retyping 0.15 a second time.
        budget = THUMBNAIL_JPEG_BUDGET_BYTES_PER_PIXEL
        self.assertEqual(
            thumbnail_plane_bytes(1280, 720, 3, 0), int(1280 * 720 * budget)
        )
        self.assertEqual(
            thumbnail_plane_bytes(1280, 720, 3, 1), int(640 * 360 * budget)
        )
        self.assertEqual(
            thumbnail_plane_bytes(1280, 720, 3, 2), int(320 * 180 * budget)
        )
        # Strictly less than mode 2 (uncompressed colour) at the same
        # geometry -- the entire premise of offering JPEG as the low-cost
        # choice.
        self.assertLess(
            thumbnail_plane_bytes(1280, 720, 3, 2),
            thumbnail_plane_bytes(1280, 720, 2, 2),
        )

    def test_mode3_jpeg_floor_matches_mode2s(self):
        # Same width/height floor as every other mode (max(1, dim >> shift)).
        self.assertEqual(thumbnail_plane_bytes(1272, 720, 3, 12), int(1 * 1 * THUMBNAIL_JPEG_BUDGET_BYTES_PER_PIXEL))


class ComputeFrameSizeMbTests(unittest.TestCase):
    """compute_frame_size_mb() with and without the thumbnail_bytes term,
    against FINDINGS §2's measured files."""

    def test_without_thumbnail_term_is_far_below_a_file_that_has_one(self):
        # 4K 10-bit log frame, colour thumbnail at shift 0 (Downloads
        # 210738, 09-06): measured file size 13,135,688 B. Without the
        # term this model only sees the raw strip + flat overhead --
        # exactly the bug this fix corrects.
        without = compute_frame_size_mb(3840, 2160, 10)
        measured_mb = 13135688 / 1_000_000
        self.assertLess(without, measured_mb - 2.0)

    def test_with_thumbnail_term_matches_the_measured_colour_file(self):
        # Same frame, thumbnail_bytes supplied (1280x720 colour, shift 0):
        # matches FINDINGS §2's measured 13,135,688 B to within 0.01 MB.
        with_term = compute_frame_size_mb(3840, 2160, 10, thumbnail_bytes=2764800)
        measured_mb = 13135688 / 1_000_000
        self.assertAlmostEqual(with_term, measured_mb, delta=0.01)

    def test_matches_the_shipped_colour_default_for_a_4k_12bit_frame(self):
        # 4K 12-bit frame at the actual shipped default (colour, shift 2):
        # 12,441,600 (raw) + 172,800 (thumbnail) + 1,024 (overhead)
        # = 12,615,424 B -> 12.62 MB.
        mb = compute_frame_size_mb(3840, 2160, 12, thumbnail_bytes=172800)
        self.assertEqual(mb, 12.62)


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
    """Minimal stand-in, same shape as test_cinepi_controller_resolution_gui.py's.
    _calc_lores is NOT reimplemented here -- it delegates to the real,
    already-pure SensorDetect._calc_lores (an unbound call; the method
    never touches self) so this fixture cannot silently drift from the
    production formula."""

    def __init__(self):
        self.res_modes = {
            0: {"width": 3840, "height": 2160, "bit_depth": 12, "hdr": False},
        }

    def _calc_lores(self, sensor_w, sensor_h):
        return SensorDetect._calc_lores(None, sensor_w, sensor_h)

    def resolve_effective_bit_depth(self, _camera_name, native_bit_depth, *, log_requested=False, hdr=False):
        return native_bit_depth


class RecomputeFileSizeThumbnailTests(unittest.TestCase):
    """_recompute_file_size() with the live thumbnail/thumbnail_size keys
    set, and set_thumbnail()'s recompute-after-write. Fixture follows
    test_cinepi_controller_resolution_gui.py's ResolutionGuiStateTests.controller()."""

    def controller(self, redis_values=None, settings_image_capture=None):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = FakeRedis(redis_values)
        controller.sensor_detect = FakeSensorDetect()
        controller.current_sensor = "imx585"
        controller.sensor_mode = 0
        controller.settings = {
            "sensors": {"cam0": {"log_encode": False}, "cam1": {}},
            # Default {} on purpose: thumbnail_startup_value()/
            # thumbnail_size_startup_value() then fall through to their own
            # shipped defaults (colour, shift 2) -- the real boot path, not
            # a value hardcoded a second time here.
            "image_capture": settings_image_capture or {},
        }
        return controller

    def test_recompute_uses_live_mono_shift1_keys(self):
        controller = self.controller(
            redis_values={
                ParameterKey.THUMBNAIL.value: "1",
                ParameterKey.THUMBNAIL_SIZE.value: "1",
            }
        )
        controller._recompute_file_size(log_requested=False)
        # 4K 12-bit raw (12,441,600) + mono 640x360 thumbnail (230,400) +
        # 1,024 overhead = 12,673,024 B -> 12.67 MB.
        self.assertEqual(controller.file_size, 12.67)
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.FILE_SIZE.value),
            "12.67",
        )

    def test_recompute_uses_live_colour_shift0_keys(self):
        controller = self.controller(
            redis_values={
                ParameterKey.THUMBNAIL.value: "2",
                ParameterKey.THUMBNAIL_SIZE.value: "0",
            }
        )
        controller._recompute_file_size(log_requested=False)
        # 12,441,600 + colour 1280x720 thumbnail (2,764,800) + 1,024
        # = 15,207,424 B -> 15.21 MB.
        self.assertEqual(controller.file_size, 15.21)

    def test_recompute_uses_the_shipped_jpeg_default_when_keys_and_settings_are_absent(self):
        # No live redis keys AND no image_capture settings at all -- the
        # true fresh-boot path. Must fall back to thumbnail_startup_value()/
        # thumbnail_size_startup_value()'s own shipped default (colour,
        # shift 2, 2026-09-13 final decision), not silently treat the
        # thumbnail as absent or as some other value.
        controller = self.controller(redis_values={})
        controller._recompute_file_size(log_requested=False)
        # 12,441,600 + the JPEG BUDGET for 640x360 (0.15 B/px * 230,400 px
        # = 34,560) + 1,024 = 12,477,184 B -> 12.48 MB. The budget, not a
        # measured JPEG size: file_size must never claim more card time than
        # the operator really has, so the estimate deliberately sits above
        # what a JPEG thumbnail actually costs (measured 0.07-0.09 B/px on
        # hardware 2026-09-13).
        self.assertEqual(controller.file_size, 12.48)

    def test_recompute_honors_a_non_default_settings_choice_when_redis_is_absent(self):
        # settings.jsonc explicitly chose mono/shift-1 -- different from
        # thumbnail_startup_value()'s own built-in default (colour/shift-2)
        # -- to prove the fallback reads what settings.jsonc actually says,
        # not a value hardcoded a second time in the fallback path.
        controller = self.controller(
            redis_values={},
            settings_image_capture={"thumbnail": 1, "thumbnail_size": 1},
        )
        controller._recompute_file_size(log_requested=False)
        self.assertEqual(controller.file_size, 12.67)

    def test_set_thumbnail_recomputes_file_size(self):
        controller = self.controller(
            redis_values={
                ParameterKey.THUMBNAIL.value: "1",
                ParameterKey.THUMBNAIL_SIZE.value: "1",
            }
        )
        controller._recompute_file_size(log_requested=False)
        self.assertEqual(controller.file_size, 12.67)

        controller.set_thumbnail(2)

        self.assertEqual(controller.redis_controller.get_value(ParameterKey.THUMBNAIL.value), 2)
        # thumbnail_size is still 1 (shift 1) -- only the mode changed, to
        # colour: 12,441,600 + 691,200 + 1,024 = 13,133,824 B -> 13.13 MB.
        self.assertEqual(controller.file_size, 13.13)


if __name__ == "__main__":
    unittest.main()
