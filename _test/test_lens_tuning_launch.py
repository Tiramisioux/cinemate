"""cinepi-raw is launched with the autofocus tuning exactly when it should be.

CinePiProcess._build_args() asks _autofocus_tuning() whether the AF layer
applies to this camera (PLAN.md D9, D17). When it does, the launch carries the
derived tuning (module/lens_tuning.py) and `--autofocus-mode manual`; when it
does not, or the build fails, the launch is what it was before the layer
existed. The flag is the load-bearing half (F11): with `rpi.af` in the tuning
libcamera advertises AfMode, and cinepi-raw with no --autofocus-mode picks the
maximum -- continuous AF -- so a camera that only meant to *offer* autofocus
would start hunting on its own.

The same code answers on both platforms: the base is whichever tuning
_resolve_base_tuning() settled on (stock or override; pisp on the Pi 5 family,
vc4 on the Pi 4 family), and the derived file must be valid for that platform.

Redis AF_AVAILABLE is one value for the whole rig, so in a dual-sensor setup
only the camera the lens is mounted on may write it.

Fixtures follow test_tuning_file_override_launch.py (sys.modules stubs, fake
sensor detect) with a recording fake Redis, a tmp lens database, a tmp cache
dir and a tmp libcamera tree, so nothing touches /home/pi or the repo.
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

import module.cinepi_multi as cinepi_multi  # noqa: E402
from module import lens_tuning, tuning_files  # noqa: E402
from module.cinepi_multi import CameraInfo, CinePiProcess  # noqa: E402
from module.redis_controller import ParameterKey  # noqa: E402

KEY = "sigma-18-35-f1-8"
FOCUS = {
    "calibrated_at": "2026-10-04T12:00:00Z",
    "position_min": 0,
    "position_max": 1069,
    "mfd_m": 0.28,
    "distance_encoder": False,
    "map": [0.0, 1037, 3.57, 0],
    "dioptre_min": 0.0,
    "dioptre_max": 3.57,
    "step_frames": 4,
}
ENTRY = {"name": "Sigma 18-35 f/1.8", "lens_id": 235, "focus": FOCUS}

# The Redis state under which AF is wanted on cam0 (Pi 5 family).
WANTED = {
    ParameterKey.LENS_CONTROL.value: "1",
    ParameterKey.LENS_DETECTED.value: "1",
    ParameterKey.LENS_PROVENANCE.value: "v4l2-subdev",
    ParameterKey.LENS_PORT.value: "cam0",
    ParameterKey.LENS_KEY.value: KEY,
}
AF_AVAILABLE = ParameterKey.AF_AVAILABLE.value


def tuning_json(target="pisp", marker=0):
    return json.dumps({
        "version": 2.0,
        "target": target,
        "algorithms": [{"rpi.ccm": {"marker": marker}}, {"rpi.sharpen": {}}, {"rpi.hdr": {}}],
    }, indent=4)


class FakeRedis:
    """Reads come from a dict; every write is recorded, so a test can say
    both what AF_AVAILABLE ended up as and that a camera did not touch it."""

    def __init__(self, values):
        self.values = dict(values)
        self.writes = []

    def get_value(self, key, default=None):
        return self.values.get(key, default)

    def set_value(self, key, value):
        self.writes.append((key, value))
        self.values[key] = value

    def af_writes(self):
        return [value for key, value in self.writes if key == AF_AVAILABLE]


class FakeSensorDetect:
    def get_resolution_info(self, model_key, sensor_mode):
        return {"width": 1920, "height": 1080, "bit_depth": 12}

    def get_packing_for_platform(self, model_key, sensor_mode, is_pi4):
        return "U"

    def resolve_log_encode_target(self, model_key, bit_depth, requested, hdr):
        return None


class LaunchCase(unittest.TestCase):
    """A sandbox: lens database, cache dir and libcamera tree under one tmp
    dir, with the module-level locations patched to point at them."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.cache = self.tmp / "cache"
        self.pisp = self.tmp / "pisp"
        self.vc4 = self.tmp / "vc4"
        self.pisp.mkdir()
        self.vc4.mkdir()
        self.db = self.tmp / "lenses.json"
        self.write_db({KEY: ENTRY})
        for patcher in (
            mock.patch.object(lens_tuning, "DEFAULT_CACHE_DIR", self.cache),
            mock.patch.dict(
                tuning_files.LIBCAMERA_DATA_DIRS,
                {"pisp": str(self.pisp), "bcm2835": str(self.vc4)},
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_db(self, lenses):
        self.db.write_text(json.dumps({"schema": 1, "lenses": lenses}))

    def write_tuning(self, name, target="pisp", marker=0, where=None):
        path = (where or self.tmp) / name
        path.write_text(tuning_json(target, marker))
        return path

    def launch(
        self, redis_values=WANTED, *, is_pi4=False, autofocus=True, override=None,
        port="cam0", multi=False, lens_control=None, model="imx477",
    ):
        """Run _build_args() for one camera. Returns (args, redis, logs)."""
        settings = json.loads(json.dumps(cinepi_multi._settings()))
        settings.setdefault("sensors", {}).setdefault(port, {})[
            "tuning_file_override"
        ] = override or {"enabled": False}
        if lens_control is not False:
            settings["lens_control"] = lens_control if lens_control is not None else {
                "autofocus": autofocus, "database_file": str(self.db),
            }
        path = {"cam0": "i2c@88000", "cam1": "i2c@80000"}[port]
        if is_pi4:
            path = "i2c@1a0000"
        redis = FakeRedis(redis_values)
        with mock.patch("module.cinepi_multi._settings", return_value=settings), \
             mock.patch("module.cinepi_multi._is_pi4_family", return_value=is_pi4), \
             self.assertLogs(level="DEBUG") as logs:
            cam = CameraInfo(0 if port == "cam0" else 1, model, "RGB", path)
            proc = CinePiProcess(redis, FakeSensorDetect(), cam, primary=(port == "cam0"), multi=multi)
            args = proc._build_args()
        return args, redis, logs.output

    @staticmethod
    def arg(args, flag):
        return args[args.index(flag) + 1] if flag in args else None

    def assertNoAutofocus(self, args, redis=None):
        self.assertNotIn("--autofocus-mode", args)
        if redis is not None:
            self.assertEqual(redis.af_writes()[-1:], [""], redis.writes)

    def assertManualAutofocus(self, args):
        self.assertEqual(args.count("--autofocus-mode"), 1, args)
        self.assertEqual(self.arg(args, "--autofocus-mode"), "manual")
        self.assertEqual(args.count("--tuning-file"), 1, args)

    def derived(self, args):
        path = Path(self.arg(args, "--tuning-file"))
        self.assertEqual(path.parent, self.cache, path)
        return path, json.loads(path.read_text())

    def algorithm(self, data, name):
        return next(a[name] for a in data["algorithms"] if name in a)


class Pi5AutofocusTests(LaunchCase):
    def setUp(self):
        super().setUp()
        self.base = self.write_tuning("imx477-custom.json")
        self.override = {"enabled": True, "path": str(self.base)}

    def test_wanted_launches_with_the_derived_tuning_in_manual_mode(self):
        args, redis, logs = self.launch(override=self.override)
        self.assertManualAutofocus(args)
        path, data = self.derived(args)
        self.assertRegex(path.name, r"^imx477-custom\.[0-9a-f]{12}\.json$")
        self.assertEqual(data["target"], "pisp")
        self.assertEqual(self.algorithm(data, "rpi.af")["map"], [0.0, 1037, 3.57, 0])
        self.assertEqual(redis.af_writes(), [KEY])
        self.assertEqual(
            sum(1 for line in logs if line.startswith("INFO") and "Autofocus tuning for lens" in line), 1,
        )
        self.assertFalse(any(line.startswith("ERROR") for line in logs), logs)

    def test_it_builds_on_the_stock_tuning_when_there_is_no_override(self):
        self.write_tuning("imx477.json", marker=7, where=self.pisp)
        args, redis, _ = self.launch()
        self.assertManualAutofocus(args)
        path, data = self.derived(args)
        self.assertTrue(path.name.startswith("imx477."))
        self.assertEqual(self.algorithm(data, "rpi.ccm"), {"marker": 7})
        self.assertEqual(redis.af_writes(), [KEY])

    def test_the_flag_is_never_continuous_or_auto(self):
        # ("auto" appears elsewhere: --awb auto. Only this flag's value counts.)
        args, _, _ = self.launch(override=self.override)
        self.assertEqual(self.arg(args, "--autofocus-mode"), "manual")
        self.assertNotIn("continuous", args)

    def test_relaunch_with_the_same_inputs_reuses_the_file(self):
        first, _, _ = self.launch(override=self.override)
        second, _, _ = self.launch(override=self.override)
        self.assertEqual(self.arg(first, "--tuning-file"), self.arg(second, "--tuning-file"))
        self.assertEqual(len(list(self.cache.glob("imx477-custom.*.json"))), 1)

    def test_changing_the_base_tuning_yields_a_new_derived_file(self):
        first, _, _ = self.launch(override=self.override)
        self.base.write_text(tuning_json(marker=1))
        second, _, _ = self.launch(override=self.override)
        self.assertNotEqual(self.arg(first, "--tuning-file"), self.arg(second, "--tuning-file"))
        self.assertManualAutofocus(second)

    def test_a_calibration_change_yields_a_new_derived_file(self):
        first, _, _ = self.launch(override=self.override)
        self.write_db({KEY: dict(ENTRY, focus=dict(FOCUS, step_frames=8))})
        second, _, _ = self.launch(override=self.override)
        self.assertNotEqual(self.arg(first, "--tuning-file"), self.arg(second, "--tuning-file"))

    def test_an_invalid_map_keeps_the_base_tuning_and_logs_one_error(self):
        bad = dict(FOCUS, map=[3.57, 0, 0.0, 1037])    # dioptres descending
        self.write_db({KEY: dict(ENTRY, focus=bad)})
        args, redis, logs = self.launch(override=self.override)
        self.assertNoAutofocus(args, redis)
        self.assertEqual(self.arg(args, "--tuning-file"), str(self.base))
        errors = [line for line in logs if line.startswith("ERROR")]
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("Autofocus tuning NOT applied", errors[0])
        self.assertIn("strictly ascending", errors[0])
        self.assertIn(str(self.base), errors[0])
        self.assertFalse(self.cache.exists() and list(self.cache.iterdir()))

    def test_a_base_that_does_not_exist_keeps_the_base_path_and_logs_one_error(self):
        # No override, and the stock pisp file is not in the fake tree: the
        # launch still passes that path (Pi 5 never checked it), and AF steps
        # aside rather than deriving from nothing.
        args, redis, logs = self.launch()
        self.assertNoAutofocus(args, redis)
        self.assertEqual(self.arg(args, "--tuning-file"), str(self.pisp / "imx477.json"))
        errors = [line for line in logs if line.startswith("ERROR")]
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("base tuning not found", errors[0])

    def test_an_unwritable_cache_keeps_the_base_tuning(self):
        blocker = self.tmp / "blocker"
        blocker.write_text("a file")
        with mock.patch.object(lens_tuning, "DEFAULT_CACHE_DIR", blocker / "tuning"):
            args, redis, logs = self.launch(override=self.override)
        self.assertNoAutofocus(args, redis)
        self.assertEqual(self.arg(args, "--tuning-file"), str(self.base))
        self.assertTrue(any(line.startswith("ERROR") and "tuning cache unavailable" in line for line in logs))

    def test_a_missing_lens_entry_is_an_error_and_keeps_the_base_tuning(self):
        self.write_db({})
        args, redis, logs = self.launch(override=self.override)
        self.assertNoAutofocus(args, redis)
        self.assertEqual(self.arg(args, "--tuning-file"), str(self.base))
        errors = [line for line in logs if line.startswith("ERROR")]
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(f'no lens "{KEY}"', errors[0])

    def test_a_missing_lens_database_is_an_error_too(self):
        self.db.unlink()
        args, redis, logs = self.launch(override=self.override)
        self.assertNoAutofocus(args, redis)
        self.assertTrue(any(line.startswith("ERROR") and "no lens database" in line for line in logs))

    def test_an_uncalibrated_lens_is_not_an_error(self):
        for focus in (None, "garbage"):
            with self.subTest(repr(focus)):
                self.write_db({KEY: dict(ENTRY, focus=focus)})
                args, redis, logs = self.launch(override=self.override)
                self.assertNoAutofocus(args, redis)
                self.assertEqual(self.arg(args, "--tuning-file"), str(self.base))
                self.assertFalse(any(line.startswith("ERROR") for line in logs), logs)
                self.assertTrue(any("not calibrated" in line for line in logs))

    def test_autofocus_off_is_silent_and_launches_as_before(self):
        args, redis, logs = self.launch(override=self.override, autofocus=False)
        self.assertNoAutofocus(args, redis)
        self.assertEqual(self.arg(args, "--tuning-file"), str(self.base))
        self.assertFalse(any("Autofocus" in line for line in logs), logs)
        self.assertFalse(self.cache.exists())

    def test_the_settings_block_may_be_absent_or_malformed(self):
        # lens_control is the integration branch's block; this layer must not
        # require it.
        for block in (False, [], "x", {}, {"autofocus": "yes"}, {"autofocus": None}):
            with self.subTest(repr(block)):
                args, redis, _ = self.launch(override=self.override, lens_control=block)
                self.assertNoAutofocus(args, redis)
                self.assertEqual(self.arg(args, "--tuning-file"), str(self.base))

    def test_autofocus_accepts_a_real_true_only(self):
        for value, expected in ((True, True), (1, True), (False, False), ("true", False), (0, False)):
            with self.subTest(repr(value)):
                args, _, _ = self.launch(
                    override=self.override,
                    lens_control={"autofocus": value, "database_file": str(self.db)},
                )
                self.assertEqual("--autofocus-mode" in args, expected)

    def test_each_redis_condition_is_required(self):
        cases = {
            "lens control off": (ParameterKey.LENS_CONTROL.value, "0", "lens control is off"),
            "no adapter": (ParameterKey.LENS_DETECTED.value, "0", "no adapter detected"),
            "raw backend": (ParameterKey.LENS_PROVENANCE.value, "i2c-raw", "i2c-raw"),
            "wrong port": (ParameterKey.LENS_PORT.value, "cam1", "cam1"),
            "no lens": (ParameterKey.LENS_KEY.value, "", "no lens is selected"),
        }
        for label, (key, value, fragment) in cases.items():
            with self.subTest(label):
                args, redis, logs = self.launch({**WANTED, key: value}, override=self.override)
                self.assertNoAutofocus(args)
                self.assertEqual(self.arg(args, "--tuning-file"), str(self.base))
                info = [line for line in logs if "Autofocus enabled but not applied" in line]
                self.assertEqual(len(info), 1, logs)
                self.assertIn(fragment, info[0])
                self.assertFalse(any(line.startswith("ERROR") for line in logs), logs)

    def test_state_that_was_never_written_means_not_wanted(self):
        args, redis, _ = self.launch({}, override=self.override)
        self.assertNoAutofocus(args, redis)


class AfAvailableOwnershipTests(LaunchCase):
    """One AF_AVAILABLE for the whole rig: only the lens camera speaks."""

    def setUp(self):
        super().setUp()
        self.base = self.write_tuning("imx477-custom.json")
        self.override = {"enabled": True, "path": str(self.base)}

    def test_the_other_camera_leaves_the_value_alone(self):
        # Lens on cam1. cam1 launches first and sets the key; cam0's launch
        # must not overwrite it with "".
        lens_on_cam1 = {**WANTED, ParameterKey.LENS_PORT.value: "cam1"}
        args1, redis1, _ = self.launch(lens_on_cam1, override=self.override, port="cam1", multi=True)
        self.assertManualAutofocus(args1)
        self.assertEqual(redis1.af_writes(), [KEY])

        shared = {**lens_on_cam1, AF_AVAILABLE: KEY}
        args0, redis0, _ = self.launch(shared, override=self.override, port="cam0", multi=True)
        self.assertEqual(redis0.af_writes(), [], "cam0 must not touch AF_AVAILABLE")
        self.assertEqual(redis0.values[AF_AVAILABLE], KEY)
        self.assertNotIn("--autofocus-mode", args0)
        self.assertEqual(self.arg(args0, "--tuning-file"), str(self.base))

    def test_a_failed_build_on_the_lens_camera_clears_the_value(self):
        self.write_db({KEY: dict(ENTRY, focus=dict(FOCUS, map=[0.0, 1]))})
        stale = {**WANTED, AF_AVAILABLE: KEY}
        args, redis, _ = self.launch(stale, override=self.override)
        self.assertNoAutofocus(args)
        self.assertEqual(redis.af_writes(), [""])

    def test_turning_autofocus_off_clears_a_stale_value(self):
        stale = {**WANTED, AF_AVAILABLE: KEY}
        args, redis, _ = self.launch(stale, override=self.override, autofocus=False)
        self.assertNoAutofocus(args)
        self.assertEqual(redis.af_writes(), [""])

    def test_with_no_lens_port_every_camera_may_clear_it(self):
        no_lens = {AF_AVAILABLE: KEY}
        for port in ("cam0", "cam1"):
            with self.subTest(port):
                args, redis, _ = self.launch(no_lens, override=self.override, port=port, multi=True)
                self.assertNoAutofocus(args)
                self.assertEqual(redis.af_writes(), [""])

    def test_a_lens_port_naming_another_camera_blocks_the_write_even_when_af_is_off(self):
        lens_on_cam1 = {**WANTED, ParameterKey.LENS_PORT.value: "cam1", AF_AVAILABLE: KEY}
        _, redis, _ = self.launch(lens_on_cam1, override=self.override, autofocus=False, port="cam0", multi=True)
        self.assertEqual(redis.af_writes(), [])


class Pi4AutofocusTests(LaunchCase):
    """The same layer on the Pi 4 family (CM4 with an imx477): built on the
    vc4 stock tuning, validated as bcm2835."""

    def setUp(self):
        super().setUp()
        self.stock = self.write_tuning("imx477.json", target="bcm2835", marker=4, where=self.vc4)

    def test_wanted_builds_on_the_vc4_stock_tuning(self):
        args, redis, logs = self.launch(is_pi4=True)
        self.assertManualAutofocus(args)
        path, data = self.derived(args)
        self.assertRegex(path.name, r"^imx477\.[0-9a-f]{12}\.json$")
        self.assertEqual(data["target"], "bcm2835")
        self.assertEqual(self.algorithm(data, "rpi.ccm"), {"marker": 4})
        self.assertEqual(self.algorithm(data, "rpi.af")["map"], [0.0, 1037, 3.57, 0])
        self.assertEqual(redis.af_writes(), [KEY])
        self.assertFalse(any(line.startswith("ERROR") for line in logs), logs)

    def test_the_lens_port_is_not_compared_on_a_pi4(self):
        # CineMate names every Pi 4 sensor cam0, whatever connector the lens
        # backend found the adapter behind.
        for lens_port in ("cam0", "cam1", ""):
            with self.subTest(repr(lens_port)):
                args, redis, _ = self.launch(
                    {**WANTED, ParameterKey.LENS_PORT.value: lens_port}, is_pi4=True,
                )
                self.assertManualAutofocus(args)
                self.assertEqual(redis.af_writes(), [KEY])

    def test_not_wanted_keeps_todays_launch_exactly(self):
        # Regression guard. D19 gave a Pi 4 with a valid vc4 stock file a
        # --tuning-file; without AF it is that file, no derived one, no flag.
        args, redis, _ = self.launch(is_pi4=True, autofocus=False)
        self.assertNotIn("--autofocus-mode", args)
        self.assertEqual(self.arg(args, "--tuning-file"), str(self.stock))
        self.assertEqual(redis.af_writes(), [""])
        self.assertFalse(self.cache.exists())

    def test_not_wanted_and_no_stock_file_means_no_tuning_file_at_all(self):
        self.stock.unlink()
        args, _, _ = self.launch(is_pi4=True, autofocus=False)
        self.assertNotIn("--tuning-file", args)
        self.assertNotIn("--autofocus-mode", args)

    def test_adapter_missing_on_a_pi4_is_not_wanted(self):
        args, redis, _ = self.launch({**WANTED, ParameterKey.LENS_DETECTED.value: "0"}, is_pi4=True)
        self.assertNotIn("--autofocus-mode", args)
        self.assertEqual(self.arg(args, "--tuning-file"), str(self.stock))
        self.assertEqual(redis.af_writes(), [""])

    def test_wanted_but_no_vc4_stock_file_launches_without_tuning_and_logs_an_error(self):
        self.stock.unlink()
        args, redis, logs = self.launch(is_pi4=True)
        self.assertNotIn("--tuning-file", args)
        self.assertNotIn("--autofocus-mode", args)
        self.assertEqual(redis.af_writes(), [""])
        errors = [line for line in logs if line.startswith("ERROR")]
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("no base tuning file", errors[0])
        self.assertIn("no --tuning-file", errors[0])

    def test_a_pisp_file_in_the_vc4_slot_is_never_a_base(self):
        self.write_tuning("imx477.json", target="pisp", where=self.vc4)
        args, redis, _ = self.launch(is_pi4=True)
        self.assertNotIn("--tuning-file", args)
        self.assertNotIn("--autofocus-mode", args)
        self.assertEqual(redis.af_writes(), [""])

    def test_a_vc4_override_is_the_base(self):
        custom = self.write_tuning("imx477-mine.json", target="bcm2835", marker=9)
        args, _, _ = self.launch(is_pi4=True, override={"enabled": True, "path": str(custom)})
        self.assertManualAutofocus(args)
        path, data = self.derived(args)
        self.assertTrue(path.name.startswith("imx477-mine."))
        self.assertEqual(self.algorithm(data, "rpi.ccm"), {"marker": 9})

    def test_a_pisp_override_falls_back_to_the_stock_vc4_base(self):
        wrong = self.write_tuning("imx477-pisp.json", target="pisp")
        args, redis, logs = self.launch(is_pi4=True, override={"enabled": True, "path": str(wrong)})
        self.assertManualAutofocus(args)
        path, data = self.derived(args)
        self.assertTrue(path.name.startswith("imx477."), path.name)
        self.assertEqual(data["target"], "bcm2835")
        self.assertEqual(self.algorithm(data, "rpi.ccm"), {"marker": 4})
        self.assertEqual(redis.af_writes(), [KEY])
        self.assertTrue(any(line.startswith("ERROR") and "NOT applied" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
