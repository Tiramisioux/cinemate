"""A bad custom tuning file must degrade the picture, never black the camera.

FINDINGS.md S1 traces the mechanism end to end: CinePiProcess._build_args()
used to hand `tuning_file_override["path"]` straight to `--tuning-file` with
no existence check, no path resolution, and no JSON/target check (S1 steps
1-2). From there libcamera treats the env override as authoritative --
ipa_proxy.cpp's configurationFile() never stat()s it, so a path that cannot
be opened fails camera *registration* outright (S1 steps 4-8), while
cinepi_multi.py's own camera *discovery* had already succeeded because it
runs `cinepi-raw --list-cameras` without the flag -- so the launch is
attempted, times out waiting for cinepi_ready_cam0, and CineMate comes up
with the GUI alive and HDMI black (S1 step 9). FINDINGS.md S2 is the second,
less likely path to the same ending: a file whose "target" is "bcm2835" (a
Pi 4 / vc4 tuning) opens fine but fails libcamera's platform check the same
way.

resolve_tuning_override() (module.tuning_files, PLAN.md S1.1) is the fix:
_build_args() now resolves the path against the repo root, requires it to
exist, parses as JSON, and requires "target": "pisp" and an "algorithms"
list, *before* deciding whether to pass --tuning-file at all. Anything that
fails falls back to the auto-detected tuning with exactly one ERROR log line
naming the path and the reason.

Fixtures copied from test_cinepi_multi_mono_awb.py: same sys.modules stubs,
same FakeRedisController/FakeSensorDetect, same imx585 CameraInfo. None of
_build_args()'s other reads (storage profiles, CineMate Log, dual-HDMI) are
touched here, so a failure in this file can only be the tuning-override
guard.
"""

import copy
import json
import os
import shutil
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
from module.cinepi_multi import CameraInfo, CinePiProcess  # noqa: E402

DEFAULT_TUNE = "/home/pi/libcamera/src/ipa/rpi/pisp/data/imx585.json"
SHIPPED_IMX585_TUNING = ROOT / "resources/tuning_files/imx585.json"


class FakeRedisController:
    """get_value returns whatever default the caller asks for; nothing in
    _build_args needs a real, moving value for this test."""

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


def _settings_with_override(override):
    """A deep copy of the repo's own settings.jsonc with cam0's
    tuning_file_override replaced -- proves the rest of _build_args() still
    reads real, shipped settings (same premise test_cinepi_multi_mono_awb.py
    relies on), while this one key is under the test's control."""
    settings = copy.deepcopy(cinepi_multi._settings())
    settings.setdefault("sensors", {}).setdefault("cam0", {})["tuning_file_override"] = override
    return settings


def _build_args_with_override(override):
    """Construct a CinePiProcess with cam0's override set to *override* and
    return the args list _build_args() produces. Patches _settings() (so the
    override is exactly what the test asked for) and _is_pi4_family() (so
    --tuning-file is always in play, regardless of what this desk machine's
    own, irrelevant detection would say)."""
    settings = _settings_with_override(override)
    with mock.patch("module.cinepi_multi._settings", return_value=settings), \
         mock.patch("module.cinepi_multi._is_pi4_family", return_value=False):
        cam = CameraInfo(0, "imx585", "RGB", "i2c@88000")
        proc = CinePiProcess(FakeRedisController(), FakeSensorDetect(), cam, primary=True, multi=False)
        return proc._build_args()


class TuningOverrideLaunchGuardTests(unittest.TestCase):
    """CinePiProcess._build_args() must never hand a bad override straight
    to --tuning-file (FINDINGS.md S1, S2)."""

    def test_missing_file_falls_back_to_auto_detected_tuning(self):
        override = {"enabled": True, "path": "/nonexistent/x.json"}
        with self.assertLogs(level="ERROR") as cm:
            args = _build_args_with_override(override)
        self.assertEqual(args[args.index("--tuning-file") + 1], DEFAULT_TUNE)
        joined = "\n".join(cm.output)
        self.assertIn("NOT applied", joined)
        self.assertIn("file not found", joined)

    def test_relative_path_resolves_against_repo_root_not_cwd(self):
        override = {"enabled": True, "path": "resources/tuning_files/imx585.json"}
        expected = str(ROOT / "resources/tuning_files/imx585.json")
        tmpdir = tempfile.mkdtemp()
        cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            args = _build_args_with_override(override)
        finally:
            os.chdir(cwd)
            shutil.rmtree(tmpdir, ignore_errors=True)
        self.assertEqual(args[args.index("--tuning-file") + 1], expected)

    def test_wrong_target_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bcm2835.json"
            bad.write_text(json.dumps({"target": "bcm2835", "algorithms": []}))
            override = {"enabled": True, "path": str(bad)}
            with self.assertLogs(level="ERROR") as cm:
                args = _build_args_with_override(override)
        self.assertEqual(args[args.index("--tuning-file") + 1], DEFAULT_TUNE)
        self.assertIn("bcm2835", "\n".join(cm.output))

    def test_not_json_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "notjson.json"
            bad.write_text("not json")
            override = {"enabled": True, "path": str(bad)}
            with self.assertLogs(level="ERROR") as cm:
                args = _build_args_with_override(override)
        self.assertEqual(args[args.index("--tuning-file") + 1], DEFAULT_TUNE)
        self.assertIn("not JSON", "\n".join(cm.output))

    def test_enabled_with_empty_path_is_reported(self):
        override = {"enabled": True, "path": ""}
        with self.assertLogs(level="ERROR") as cm:
            args = _build_args_with_override(override)
        self.assertEqual(args[args.index("--tuning-file") + 1], DEFAULT_TUNE)
        self.assertIn("no path set", "\n".join(cm.output))

    def test_valid_absolute_file_passes_through(self):
        # Regression guard: an override that already worked (a real, shipped
        # pisp file at an absolute path) must keep working. PLAN.md S4.1
        # labels this a regression guard for the arg-forwarding half; the
        # INFO log is new behaviour this change adds, and does not exist on
        # dev today, so the whole method is not expected to be green there
        # (see the handoff report's red-run tail).
        with tempfile.TemporaryDirectory() as tmp:
            copy_path = Path(tmp) / "imx585.json"
            shutil.copy(SHIPPED_IMX585_TUNING, copy_path)
            override = {"enabled": True, "path": str(copy_path)}
            with self.assertLogs(level="INFO") as cm:
                args = _build_args_with_override(override)
        self.assertEqual(args[args.index("--tuning-file") + 1], str(copy_path))
        self.assertTrue(any("Custom tuning file:" in line for line in cm.output))

    def test_disabled_is_untouched(self):
        # Regression guard: disabled means disabled, exactly as today.
        override = {"enabled": False, "path": "/nonexistent/x.json"}
        with self.assertNoLogs(level="ERROR"):
            args = _build_args_with_override(override)
        self.assertEqual(args[args.index("--tuning-file") + 1], DEFAULT_TUNE)


class ResolveTuningOverrideUnitTests(unittest.TestCase):
    """resolve_tuning_override() itself, isolated from CinePiProcess. Pure:
    no logging, no Redis, no globals (PLAN.md S1.1) -- every reason string
    it can return, exercised directly."""

    def test_disabled(self):
        from module.tuning_files import resolve_tuning_override
        path, reason = resolve_tuning_override({"enabled": False}, ROOT)
        self.assertIsNone(path)
        self.assertEqual(reason, "disabled")

    def test_missing_path(self):
        from module.tuning_files import resolve_tuning_override
        path, reason = resolve_tuning_override({"enabled": True}, ROOT)
        self.assertIsNone(path)
        self.assertEqual(reason, "enabled but no path set")

    def test_empty_path(self):
        from module.tuning_files import resolve_tuning_override
        path, reason = resolve_tuning_override({"enabled": True, "path": ""}, ROOT)
        self.assertIsNone(path)
        self.assertEqual(reason, "enabled but no path set")

    def test_file_not_found(self):
        from module.tuning_files import resolve_tuning_override
        path, reason = resolve_tuning_override(
            {"enabled": True, "path": "resources/tuning_files/does_not_exist.json"}, ROOT
        )
        self.assertIsNone(path)
        self.assertEqual(reason, f"file not found: {ROOT / 'resources/tuning_files/does_not_exist.json'}")

    def test_unreadable_or_not_json(self):
        from module.tuning_files import resolve_tuning_override
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("not json")
            path, reason = resolve_tuning_override({"enabled": True, "path": str(bad)}, ROOT)
        self.assertIsNone(path)
        self.assertTrue(reason.startswith("unreadable or not JSON:"), reason)

    def test_wrong_target(self):
        from module.tuning_files import resolve_tuning_override
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bcm2835.json"
            bad.write_text(json.dumps({"target": "bcm2835", "algorithms": []}))
            path, reason = resolve_tuning_override({"enabled": True, "path": str(bad)}, ROOT)
        self.assertIsNone(path)
        self.assertEqual(
            reason,
            'target is "bcm2835", expected "pisp" (a Pi 4 / vc4 tuning cannot load on a Pi 5)',
        )

    def test_missing_algorithms_list(self):
        from module.tuning_files import resolve_tuning_override
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "noalgo.json"
            bad.write_text(json.dumps({"target": "pisp"}))
            path, reason = resolve_tuning_override({"enabled": True, "path": str(bad)}, ROOT)
        self.assertIsNone(path)
        self.assertEqual(reason, 'no "algorithms" list (not a version 2 tuning file)')

    def test_valid_file_resolves_ok(self):
        from module.tuning_files import resolve_tuning_override
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.json"
            shutil.copy(SHIPPED_IMX585_TUNING, good)
            path, reason = resolve_tuning_override({"enabled": True, "path": str(good)}, ROOT)
        self.assertEqual(path, good)
        self.assertEqual(reason, "ok")

    def test_relative_path_resolves_against_the_given_repo_root(self):
        from module.tuning_files import resolve_tuning_override
        path, reason = resolve_tuning_override(
            {"enabled": True, "path": "resources/tuning_files/imx585.json"}, ROOT
        )
        self.assertEqual(path, ROOT / "resources/tuning_files/imx585.json")
        self.assertEqual(reason, "ok")


if __name__ == "__main__":
    unittest.main()
