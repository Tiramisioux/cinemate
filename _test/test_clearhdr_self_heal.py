"""ClearHDR self-heal (round 8, 2026-08-29): the imx585 ClearHDR combiner can
start up latched into a flat pedestal (~4.9% of full-scale, confirmed
identical in both 12-bit CCMP and 16-bit linear ClearHDR -- see
development/mono-clearhdr-fixes/ROUND8-RESULTS.md) with every sensor register
reading correct. Confirmed recoveries: a large analogue-gain swing (tried
first -- mirrors the light-level shock, flashing a light or covering the
sensor, that has reliably cleared it by hand) and a mode bounce (tried as a
fallback -- confirmed live on 2026-08-29 to sometimes NOT clear it on its
own, hence gain-shock-first, not mode-bounce-only). This is a mitigation,
not a fix -- the underlying cause is unknown.

These tests isolate CinePiManager._clearhdr_self_heal_if_stuck(),
_shock_analog_gain(), and _preview_frame_is_degenerate() from the rest of
start_all() (sensor discovery, subprocess launch, the "ready" wait) by
calling them directly against a bare CinePiManager instance -- none of that
machinery is exercised or needed for this seam.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("psutil", types.SimpleNamespace())

from module.cinepi_multi import CinePiManager, _CLEARHDR_SELF_HEAL_MAX_ATTEMPTS
from module.redis_controller import ParameterKey


class FakeRedis:
    def __init__(self, initial=None):
        self.values = dict(initial or {})

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value


def make_manager(hdr="1", sensor_mode=3):
    redis_controller = FakeRedis({
        ParameterKey.HDR.value: hdr,
        ParameterKey.SENSOR_MODE.value: sensor_mode,
    })
    return CinePiManager(redis_controller, sensor_detect=None)


class ClearHdrSelfHealGatingTests(unittest.TestCase):
    def test_skips_entirely_when_hdr_is_not_active(self):
        mgr = make_manager(hdr="0")
        with mock.patch.object(mgr, "_preview_frame_is_degenerate") as probe, \
             mock.patch("module.cinepi_multi.time.sleep") as sleep:
            mgr._clearhdr_self_heal_if_stuck()
        probe.assert_not_called()
        sleep.assert_not_called()

    def test_does_nothing_when_the_preview_looks_healthy(self):
        mgr = make_manager(hdr="1")
        with mock.patch.object(mgr, "_preview_frame_is_degenerate", return_value=False), \
             mock.patch.object(mgr, "start_all") as start_all, \
             mock.patch("module.cinepi_multi.time.sleep"):
            mgr._clearhdr_self_heal_if_stuck()
        start_all.assert_not_called()


class ClearHdrSelfHealGainShockOrderingTests(unittest.TestCase):
    def test_tries_gain_shock_before_any_mode_bounce(self):
        mgr = make_manager(hdr="1", sensor_mode=3)
        # Degenerate initially, still degenerate right after the gain shock
        # (checked once more before falling back to a bounce), then fixed
        # by the first bounce.
        with mock.patch.object(mgr, "_preview_frame_is_degenerate", side_effect=[True, True, False]), \
             mock.patch.object(mgr, "_shock_analog_gain") as shock, \
             mock.patch.object(mgr, "start_all") as start_all, \
             mock.patch("module.cinepi_multi.time.sleep"):
            mgr._clearhdr_self_heal_if_stuck()

        shock.assert_called_once()
        self.assertEqual(start_all.call_count, 2)  # one bounce, away + back

    def test_gain_shock_alone_can_resolve_it_with_no_mode_bounce_at_all(self):
        mgr = make_manager(hdr="1", sensor_mode=3)
        with mock.patch.object(mgr, "_preview_frame_is_degenerate", side_effect=[True, False]), \
             mock.patch.object(mgr, "_shock_analog_gain") as shock, \
             mock.patch.object(mgr, "start_all") as start_all, \
             mock.patch("module.cinepi_multi.time.sleep"):
            mgr._clearhdr_self_heal_if_stuck()

        shock.assert_called_once()
        start_all.assert_not_called()

    def test_gain_shock_is_only_tried_once_not_on_every_bounce_attempt(self):
        mgr = make_manager(hdr="1", sensor_mode=3)
        with mock.patch.object(mgr, "_preview_frame_is_degenerate", return_value=True), \
             mock.patch.object(mgr, "_shock_analog_gain") as shock, \
             mock.patch.object(mgr, "start_all"), \
             mock.patch("module.cinepi_multi.time.sleep"):
            mgr._clearhdr_self_heal_if_stuck()

        shock.assert_called_once()


class ClearHdrSelfHealBounceTests(unittest.TestCase):
    def test_a_degenerate_preview_triggers_exactly_one_bounce_away_and_back(self):
        mgr = make_manager(hdr="1", sensor_mode=3)
        # Still degenerate after the gain shock, fixed by the following bounce.
        with mock.patch.object(mgr, "_preview_frame_is_degenerate", side_effect=[True, True, False]), \
             mock.patch.object(mgr, "_shock_analog_gain"), \
             mock.patch.object(mgr, "start_all") as start_all, \
             mock.patch("module.cinepi_multi.time.sleep"):
            mgr._clearhdr_self_heal_if_stuck()

        self.assertEqual(start_all.call_count, 2)
        # Away: bounced to a *different* mode. Back: restored to the stuck mode.
        away_kwargs = start_all.call_args_list[0].kwargs
        back_kwargs = start_all.call_args_list[1].kwargs
        self.assertFalse(away_kwargs["_run_self_heal"])
        self.assertFalse(back_kwargs["_run_self_heal"])
        self.assertEqual(mgr.redis_controller.get_value(ParameterKey.SENSOR_MODE.value), 3)

    def test_recursion_is_bounded_by_the_attempt_cap_not_by_nested_start_all_calls(self):
        """The bug this guards against: start_all() itself calls
        _clearhdr_self_heal_if_stuck() at its own end (see the real
        start_all(), not the mocked one here). If the bounce calls didn't
        pass _run_self_heal=False, each nested start_all() would restart its
        own attempt counter at 0, and the cap on the outer explicit
        recursion would not bound total recursion depth at all. Mocking
        start_all() as a no-op here isolates that nested self-triggering
        risk from this test -- it specifically checks that the *explicit*
        recursion this method performs stops within a fixed, small number of
        calls even when the preview never recovers.
        """
        mgr = make_manager(hdr="1", sensor_mode=3)
        with mock.patch.object(mgr, "_preview_frame_is_degenerate", return_value=True), \
             mock.patch.object(mgr, "_shock_analog_gain"), \
             mock.patch.object(mgr, "start_all") as start_all, \
             mock.patch("module.cinepi_multi.logging.warning") as warn, \
             mock.patch("module.cinepi_multi.time.sleep"):
            mgr._clearhdr_self_heal_if_stuck()

        self.assertEqual(start_all.call_count, 2 * _CLEARHDR_SELF_HEAL_MAX_ATTEMPTS)
        # One "trying a gain shock" warning, one "still stuck -- bouncing" per
        # bounce attempt, plus one final "still stuck, giving up" warning.
        self.assertEqual(warn.call_count, _CLEARHDR_SELF_HEAL_MAX_ATTEMPTS + 2)


class ShockAnalogGainTests(unittest.TestCase):
    def test_drives_gain_to_min_then_max_and_republishes_iso(self):
        mgr = make_manager()
        mgr.redis_controller.r = mock.MagicMock()

        with mock.patch("module.cinepi_multi.os.path.exists", side_effect=lambda p: p == "/dev/v4l-subdev0"), \
             mock.patch("module.cinepi_multi.subprocess.run") as run, \
             mock.patch("module.cinepi_multi.time.sleep"):
            run.return_value = mock.MagicMock(returncode=0)
            mgr._shock_analog_gain()

        gain_calls = [c for c in run.call_args_list if "analogue_gain" in c.args[0][-1]]
        self.assertEqual(len(gain_calls), 2)
        self.assertIn("analogue_gain=0", gain_calls[0].args[0][-1])
        self.assertIn("analogue_gain=80", gain_calls[1].args[0][-1])
        mgr.redis_controller.r.publish.assert_called_once_with("cp_controls", ParameterKey.ISO.value)

    def test_no_subdev_accepting_the_control_still_republishes_iso(self):
        """Fail open: if nothing accepts the control, don't leave the sensor
        without its ISO re-applied -- still hand control back."""
        mgr = make_manager()
        mgr.redis_controller.r = mock.MagicMock()

        with mock.patch("module.cinepi_multi.os.path.exists", return_value=False), \
             mock.patch("module.cinepi_multi.subprocess.run") as run, \
             mock.patch("module.cinepi_multi.time.sleep"):
            mgr._shock_analog_gain()

        run.assert_not_called()
        mgr.redis_controller.r.publish.assert_called_once_with("cp_controls", ParameterKey.ISO.value)


class PreviewFrameDegenerateTests(unittest.TestCase):
    def _fake_jpeg_bytes(self, array):
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.fromarray(array).save(buf, format="JPEG")
        return b"\xff\xd8" + buf.getvalue()[2:]  # keep it simple: real SOI, real payload

    def test_a_flat_frame_is_reported_degenerate(self):
        import numpy as np
        flat = np.full((480, 640), 40, dtype=np.uint8)
        jpeg_bytes = self._fake_jpeg_bytes(flat)

        mgr = make_manager()
        fake_response = mock.MagicMock()
        fake_response.read.return_value = jpeg_bytes
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with mock.patch("urllib.request.urlopen", return_value=fake_response):
            self.assertTrue(mgr._preview_frame_is_degenerate())

    def test_a_varied_frame_is_not_reported_degenerate(self):
        import numpy as np
        rng = np.random.default_rng(0)
        varied = rng.integers(0, 256, size=(480, 640), dtype=np.uint8)
        jpeg_bytes = self._fake_jpeg_bytes(varied)

        mgr = make_manager()
        fake_response = mock.MagicMock()
        fake_response.read.return_value = jpeg_bytes
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with mock.patch("urllib.request.urlopen", return_value=fake_response):
            self.assertFalse(mgr._preview_frame_is_degenerate())

    def test_a_fetch_failure_fails_open_not_degenerate(self):
        mgr = make_manager()
        with mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            self.assertFalse(mgr._preview_frame_is_degenerate())


if __name__ == "__main__":
    unittest.main()
