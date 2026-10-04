"""The Pi 4 family gets its own vc4 tuning profile; the Pi 5 family keeps pisp.

PLAN.md D19. Before it, the stock tuning path was written twice, hardcoded to
`.../ipa/rpi/pisp/data/`, in cinepi_multi.py (--tuning-file) and in
cinepi_controller.py (the white-balance ct_curve loader). On a CM4 that meant
two things at once: the launch skipped --tuning-file altogether ("VC4 uses its
built-in tuning"), so a tuning_file_override could never apply, and the
white-balance curve came from the *Pi 5* imx477 file because the source tree
holds both. tuning_files.py now decides the platform pair (data dir, expected
"target") in one place and every caller passes is_pi4 down, so none of this
needs hardware to test.

What these tests pin:
  * Pi 5 behaviour is unchanged: the stock pisp path is passed unchecked, and
    an override must be pisp -- a vc4 file degrades with the usual ERROR line.
  * Pi 4 passes its vc4 stock file only when it exists and validates as
    "bcm2835"; otherwise it launches with no --tuning-file, as before, and says
    why in one line.
  * tuning_file_override now applies on Pi 4, validated against "bcm2835"; a
    pisp file there degrades with the same ERROR line.
  * tuning_json_problem()'s default still rejects a vc4 file, because the
    settings-editor upload route calls it with no second argument.
  * The ct_curve loader reads the platform's file.

Fixtures follow test_tuning_file_override_launch.py: same sys.modules stubs,
same fake Redis and sensor detect. The fake libcamera tree lives in a tmp dir
that LIBCAMERA_DATA_DIRS is pointed at, so nothing here touches /home/pi.
"""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("psutil", types.SimpleNamespace())
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

import module.cinepi_multi as cinepi_multi  # noqa: E402
from module import tuning_files  # noqa: E402
from module.cinepi_controller import CinePiController  # noqa: E402
from module.cinepi_multi import CameraInfo, CinePiProcess  # noqa: E402
from module.tuning_files import (  # noqa: E402
    libcamera_data_dir,
    resolve_stock_tuning,
    resolve_tuning_override,
    stock_tuning_path,
    tuning_json_problem,
    tuning_target,
)

PISP_UPLOAD_MESSAGE = (
    'target is "bcm2835", expected "pisp" (a Pi 4 / vc4 tuning cannot load on a Pi 5)'
)


def tuning_json(target, ct_curve=None):
    """The smallest file tuning_json_problem() accepts. *ct_curve*, when
    given, is carried in an rpi.awb block like a real stock file's."""
    algorithms = [{"rpi.sharpen": {}}, {"rpi.hdr": {}}]
    if ct_curve is not None:
        algorithms.insert(0, {"rpi.awb": {"ct_curve": ct_curve}})
    return json.dumps({"version": 2.0, "target": target, "algorithms": algorithms})


class FakeLibcameraTree:
    """A tmp libcamera source tree with both data dirs, patched in for the
    duration of a test. Files are written per platform on demand."""

    def __init__(self, test):
        self._tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.pisp = self.root / "pisp"
        self.vc4 = self.root / "vc4"
        self.pisp.mkdir()
        self.vc4.mkdir()
        patcher = mock.patch.dict(
            tuning_files.LIBCAMERA_DATA_DIRS,
            {"pisp": str(self.pisp), "bcm2835": str(self.vc4)},
        )
        patcher.start()
        test.addCleanup(patcher.stop)

    def write(self, is_pi4, name, text):
        path = (self.vc4 if is_pi4 else self.pisp) / name
        path.write_text(text)
        return path


class FakeRedisController:
    def get_value(self, key, default=None):
        return default

    def set_value(self, key, value):
        pass


class FakeSensorDetect:
    def get_resolution_info(self, model_key, sensor_mode):
        return {"width": 1920, "height": 1080, "bit_depth": 12}

    def get_packing_for_platform(self, model_key, sensor_mode, is_pi4):
        return "U"

    def resolve_log_encode_target(self, model_key, bit_depth, requested, hdr):
        return None


def build_args(*, is_pi4, override=None, model="imx477"):
    settings = json.loads(json.dumps(cinepi_multi._settings()))
    settings.setdefault("sensors", {}).setdefault("cam0", {})[
        "tuning_file_override"
    ] = override or {"enabled": False}
    path = "i2c@1a0000" if is_pi4 else "i2c@88000"
    with mock.patch("module.cinepi_multi._settings", return_value=settings), \
         mock.patch("module.cinepi_multi._is_pi4_family", return_value=is_pi4):
        cam = CameraInfo(0, model, "RGB", path)
        proc = CinePiProcess(FakeRedisController(), FakeSensorDetect(), cam, primary=True, multi=False)
        return proc._build_args()


def tuning_arg(args):
    return args[args.index("--tuning-file") + 1] if "--tuning-file" in args else None


class PlatformResolverTests(unittest.TestCase):
    """The pure half: data dir, expected target, stock path, stock check."""

    def test_target_per_platform(self):
        self.assertEqual(tuning_target(False), "pisp")
        self.assertEqual(tuning_target(True), "bcm2835")

    def test_shipped_data_dirs_are_libcameras_source_tree(self):
        # Not patched: the real constants. These are the two paths that used
        # to be hardcoded in cinepi_multi.py and cinepi_controller.py.
        self.assertEqual(libcamera_data_dir(False), Path("/home/pi/libcamera/src/ipa/rpi/pisp/data"))
        self.assertEqual(libcamera_data_dir(True), Path("/home/pi/libcamera/src/ipa/rpi/vc4/data"))
        self.assertEqual(
            str(stock_tuning_path("imx585_mono", False)),
            "/home/pi/libcamera/src/ipa/rpi/pisp/data/imx585_mono.json",
        )
        self.assertEqual(
            str(stock_tuning_path("imx477", True)),
            "/home/pi/libcamera/src/ipa/rpi/vc4/data/imx477.json",
        )

    def test_stock_tuning_ok_on_each_platform(self):
        tree = FakeLibcameraTree(self)
        pisp = tree.write(False, "imx477.json", tuning_json("pisp"))
        vc4 = tree.write(True, "imx477.json", tuning_json("bcm2835"))
        self.assertEqual(resolve_stock_tuning("imx477", False), (pisp, "ok"))
        self.assertEqual(resolve_stock_tuning("imx477", True), (vc4, "ok"))

    def test_stock_tuning_missing(self):
        tree = FakeLibcameraTree(self)
        path, reason = resolve_stock_tuning("imx477", True)
        self.assertIsNone(path)
        self.assertEqual(reason, f"file not found: {tree.vc4 / 'imx477.json'}")

    def test_stock_tuning_wrong_target_is_refused_both_ways(self):
        tree = FakeLibcameraTree(self)
        tree.write(True, "imx477.json", tuning_json("pisp"))
        tree.write(False, "imx477.json", tuning_json("bcm2835"))
        path, reason = resolve_stock_tuning("imx477", True)
        self.assertIsNone(path)
        self.assertEqual(
            reason,
            'target is "pisp", expected "bcm2835" (a Pi 5 / PiSP tuning cannot load on a Pi 4)',
        )
        path, reason = resolve_stock_tuning("imx477", False)
        self.assertIsNone(path)
        self.assertEqual(reason, PISP_UPLOAD_MESSAGE)

    def test_stock_tuning_not_json(self):
        tree = FakeLibcameraTree(self)
        tree.write(True, "imx477.json", "{ not json")
        path, reason = resolve_stock_tuning("imx477", True)
        self.assertIsNone(path)
        self.assertTrue(reason.startswith("unreadable or not JSON:"), reason)


class TuningJsonProblemDefaultTests(unittest.TestCase):
    """The settings-editor upload route calls tuning_json_problem(data) with
    one argument and must keep rejecting a vc4 file until WP4 chooses
    otherwise. These pin that default."""

    def test_default_still_rejects_a_vc4_file_with_the_old_message(self):
        data = json.loads(tuning_json("bcm2835"))
        self.assertEqual(tuning_json_problem(data), PISP_UPLOAD_MESSAGE)

    def test_default_still_accepts_pisp(self):
        self.assertIsNone(tuning_json_problem(json.loads(tuning_json("pisp"))))

    def test_expected_target_bcm2835_accepts_vc4_and_refuses_pisp(self):
        self.assertIsNone(tuning_json_problem(json.loads(tuning_json("bcm2835")), "bcm2835"))
        self.assertIn(
            "cannot load on a Pi 4",
            tuning_json_problem(json.loads(tuning_json("pisp")), "bcm2835"),
        )

    def test_not_a_dict_names_the_missing_target(self):
        self.assertIn('target is "None"', tuning_json_problem([], "bcm2835"))

    def test_override_resolver_default_is_pisp(self):
        with tempfile.TemporaryDirectory() as tmp:
            vc4 = Path(tmp) / "vc4.json"
            vc4.write_text(tuning_json("bcm2835"))
            path, reason = resolve_tuning_override({"enabled": True, "path": str(vc4)}, ROOT)
        self.assertIsNone(path)
        self.assertEqual(reason, PISP_UPLOAD_MESSAGE)

    def test_override_resolver_accepts_a_vc4_file_for_bcm2835(self):
        with tempfile.TemporaryDirectory() as tmp:
            vc4 = Path(tmp) / "vc4.json"
            vc4.write_text(tuning_json("bcm2835"))
            path, reason = resolve_tuning_override(
                {"enabled": True, "path": str(vc4)}, ROOT, "bcm2835",
            )
        self.assertEqual((path, reason), (vc4, "ok"))


class Pi4LaunchTests(unittest.TestCase):
    """CinePiProcess._build_args() on the Pi 4 family."""

    def test_valid_vc4_stock_file_is_passed_as_tuning_file(self):
        tree = FakeLibcameraTree(self)
        vc4 = tree.write(True, "imx477.json", tuning_json("bcm2835"))
        args = build_args(is_pi4=True)
        self.assertEqual(tuning_arg(args), str(vc4))

    def test_no_stock_file_means_no_tuning_file_and_one_line_saying_why(self):
        # Regression guard: this is what every Pi 4 launch did before D19.
        tree = FakeLibcameraTree(self)
        with self.assertLogs(level="INFO") as cm:
            args = build_args(is_pi4=True)
        self.assertNotIn("--tuning-file", args)
        lines = [line for line in cm.output if "No usable bcm2835 tuning" in line]
        self.assertEqual(len(lines), 1, cm.output)
        self.assertIn(f"file not found: {tree.vc4 / 'imx477.json'}", lines[0])
        self.assertIn("launching without --tuning-file", lines[0])

    def test_stock_file_with_the_wrong_target_is_not_passed(self):
        tree = FakeLibcameraTree(self)
        tree.write(True, "imx477.json", tuning_json("pisp"))
        with self.assertLogs(level="INFO") as cm:
            args = build_args(is_pi4=True)
        self.assertNotIn("--tuning-file", args)
        warnings = [line for line in cm.output if line.startswith("WARNING") and "No usable" in line]
        self.assertEqual(len(warnings), 1, cm.output)
        self.assertIn('target is "pisp", expected "bcm2835"', warnings[0])

    def test_vc4_override_applies_on_pi4(self):
        tree = FakeLibcameraTree(self)
        tree.write(True, "imx477.json", tuning_json("bcm2835"))
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "mine.json"
            custom.write_text(tuning_json("bcm2835"))
            with self.assertLogs(level="INFO") as cm:
                args = build_args(is_pi4=True, override={"enabled": True, "path": str(custom)})
        self.assertEqual(tuning_arg(args), str(custom))
        self.assertTrue(any("Custom tuning file:" in line for line in cm.output))
        self.assertFalse(any("ignored on Pi 4" in line for line in cm.output))

    def test_vc4_override_applies_even_without_a_stock_file(self):
        FakeLibcameraTree(self)
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "mine.json"
            custom.write_text(tuning_json("bcm2835"))
            args = build_args(is_pi4=True, override={"enabled": True, "path": str(custom)})
        self.assertEqual(tuning_arg(args), str(custom))

    def test_pisp_override_on_pi4_degrades_to_the_vc4_stock_file(self):
        tree = FakeLibcameraTree(self)
        vc4 = tree.write(True, "imx477.json", tuning_json("bcm2835"))
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / "pisp.json"
            wrong.write_text(tuning_json("pisp"))
            with self.assertLogs(level="ERROR") as cm:
                args = build_args(is_pi4=True, override={"enabled": True, "path": str(wrong)})
        self.assertEqual(tuning_arg(args), str(vc4))
        joined = "\n".join(cm.output)
        self.assertIn("NOT applied", joined)
        self.assertIn('expected "bcm2835"', joined)

    def test_pisp_override_on_pi4_with_no_stock_file_launches_without_tuning(self):
        FakeLibcameraTree(self)
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / "pisp.json"
            wrong.write_text(tuning_json("pisp"))
            with self.assertLogs(level="ERROR") as cm:
                args = build_args(is_pi4=True, override={"enabled": True, "path": str(wrong)})
        self.assertNotIn("--tuning-file", args)
        joined = "\n".join(cm.output)
        self.assertIn("NOT applied", joined)
        self.assertIn("no --tuning-file", joined)

    def test_disabled_override_on_pi4_is_silent(self):
        tree = FakeLibcameraTree(self)
        tree.write(True, "imx477.json", tuning_json("bcm2835"))
        with self.assertNoLogs(level="ERROR"):
            build_args(is_pi4=True, override={"enabled": False, "path": "/nonexistent/x.json"})


class Pi5LaunchTests(unittest.TestCase):
    """Pi 5 behaviour is unchanged by D19, with the one new refusal: the
    other ISP's file."""

    def test_stock_pisp_path_is_passed_unchecked(self):
        # The file does not exist in the fake tree and the launch passes it
        # anyway, exactly as it always did on the Pi 5 family.
        tree = FakeLibcameraTree(self)
        args = build_args(is_pi4=False)
        self.assertEqual(tuning_arg(args), str(tree.pisp / "imx477.json"))

    def test_vc4_override_on_pi5_degrades_with_the_usual_error(self):
        tree = FakeLibcameraTree(self)
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / "vc4.json"
            wrong.write_text(tuning_json("bcm2835"))
            with self.assertLogs(level="ERROR") as cm:
                args = build_args(is_pi4=False, override={"enabled": True, "path": str(wrong)})
        self.assertEqual(tuning_arg(args), str(tree.pisp / "imx477.json"))
        joined = "\n".join(cm.output)
        self.assertIn("NOT applied", joined)
        self.assertIn(PISP_UPLOAD_MESSAGE, joined)

    def test_pisp_override_on_pi5_still_applies(self):
        FakeLibcameraTree(self)
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "mine.json"
            custom.write_text(tuning_json("pisp"))
            args = build_args(is_pi4=False, override={"enabled": True, "path": str(custom)})
        self.assertEqual(tuning_arg(args), str(custom))


class CtCurveLoaderTests(unittest.TestCase):
    """initialize_wb_cg_rb_array() reads the platform's stock file. The two
    files carry mirrored curves so the platform that was read is visible in
    the gains it produced."""

    # One 5000 K point. gains = (round(1/r, 1), round(1/b, 1)).
    PISP_CURVE = [5000.0, 0.25, 0.5]   # -> (4.0, 2.0)
    VC4_CURVE = [5000.0, 0.5, 0.25]    # -> (2.0, 4.0)

    def _controller(self, sensor="imx477"):
        controller = CinePiController.__new__(CinePiController)
        controller.current_sensor = sensor
        controller.wb_steps = [5000]
        controller.wb_cg_rb_array = {}
        return controller

    def _tree(self):
        tree = FakeLibcameraTree(self)
        tree.write(False, "imx477.json", tuning_json("pisp", self.PISP_CURVE))
        tree.write(True, "imx477.json", tuning_json("bcm2835", self.VC4_CURVE))
        return tree

    def test_pi5_reads_the_pisp_file(self):
        self._tree()
        controller = self._controller()
        with mock.patch("module.cinepi_controller.is_pi4_family", return_value=False):
            controller.initialize_wb_cg_rb_array()
        self.assertEqual(controller.wb_cg_rb_array[5000], (4.0, 2.0))

    def test_pi4_reads_the_vc4_file(self):
        tree = self._tree()
        controller = self._controller()
        with mock.patch("module.cinepi_controller.is_pi4_family", return_value=True), \
             self.assertLogs(level="INFO") as cm:
            controller.initialize_wb_cg_rb_array()
        self.assertEqual(controller.wb_cg_rb_array[5000], (2.0, 4.0))
        self.assertTrue(
            any(f"Loading tuning file from: {tree.vc4 / 'imx477.json'}" in line for line in cm.output),
            cm.output,
        )

    def test_pi4_without_a_vc4_file_falls_back_to_the_default_curve(self):
        # The fallback stays: a pisp file next to it must NOT be picked up.
        tree = FakeLibcameraTree(self)
        tree.write(False, "imx477.json", tuning_json("pisp", self.PISP_CURVE))
        controller = self._controller()
        with mock.patch("module.cinepi_controller.is_pi4_family", return_value=True), \
             self.assertLogs(level="WARNING") as cm:
            controller.initialize_wb_cg_rb_array()
        self.assertIn("using the default ct_curve", "\n".join(cm.output))
        self.assertEqual(sorted(controller.wb_cg_rb_array), [5000])
        self.assertNotEqual(controller.wb_cg_rb_array[5000], (4.0, 2.0))


if __name__ == "__main__":
    unittest.main()
