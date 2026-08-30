"""ClearHDR self-heal (round 8, 2026-08-29): the imx585 ClearHDR combiner can
start up latched into a flat pedestal (~4.9% of full-scale, confirmed
identical in both 12-bit CCMP and 16-bit linear ClearHDR -- see
development/mono-clearhdr-fixes/ROUND8-RESULTS.md) with every sensor register
reading correct. Confirmed recoveries, in the order tried: a brief shutter
kick to 1 degree and back (tried first -- a mode bounce alone was tried live
on 2026-08-29 and did NOT clear a stuck session, and neither did an earlier
analogue-gain-shock version of this self-heal; setting shutter to 1 degree
by hand did), then a mode bounce as a last-resort fallback. This is a
mitigation, not a fix -- the underlying cause is unknown.

These tests isolate CinePiManager._clearhdr_self_heal_if_stuck(),
_shock_shutter_angle(), and _preview_frame_is_degenerate() from the rest of
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


class FakeController:
    """Minimal stand-in for CinePiController -- only what
    _shock_shutter_angle() touches: set_shutter_a() and the
    clearhdr_self_heal_active flag it toggles around the kick."""

    def __init__(self, shutter_angle_nom=45.0):
        self.shutter_angle_nom = shutter_angle_nom
        self.clearhdr_self_heal_active = False
        self.set_shutter_a_calls = []

    def set_shutter_a(self, value):
        self.set_shutter_a_calls.append(value)
        self.shutter_angle_nom = value


class FakeSensorDetect:
    """Stand-in for the real sensor_detect.get_hdr(camera_model, mode) --
    a per-mode-table lookup, independent of anything in Redis."""

    def __init__(self, hdr_modes):
        self.hdr_modes = set(hdr_modes)  # set of sensor_mode ints that are HDR

    def get_hdr(self, camera_model, sensor_mode):
        return sensor_mode in self.hdr_modes


def make_manager(hdr="1", sensor_mode=3, controller=True, sensor_detect=None):
    redis_controller = FakeRedis({
        ParameterKey.HDR.value: hdr,
        ParameterKey.SENSOR_MODE.value: sensor_mode,
    })
    mgr = CinePiManager(redis_controller, sensor_detect=sensor_detect)
    if controller:
        mgr.controller = FakeController()
    return mgr


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


class ClearHdrSelfHealModeDerivedHdrCheckTests(unittest.TestCase):
    """Regression coverage for a bug caught live on hardware (2026-08-30):
    the Redis ``hdr`` key is only ever written by set_resolution()
    (cinepi_controller.py:1714), not by start_all() itself, so it can lag
    behind whichever sensor_mode was *actually* just launched. Self-heal
    fired on a plain SDR mode-0 launch because a stale hdr=1 from an earlier
    session was still sitting in Redis. These tests pin the fix: when
    camera_model/launched_mode are known, use sensor_detect's per-mode
    table, not the Redis flag."""

    def test_ignores_a_stale_redis_hdr_flag_when_the_launched_mode_is_not_hdr(self):
        # Redis says hdr=1 (stale, left over from an earlier ClearHDR
        # session) but the mode that was *actually* just launched (0) is
        # not one of the sensor's HDR modes.
        sensor_detect = FakeSensorDetect(hdr_modes={3, 4})
        mgr = make_manager(hdr="1", sensor_mode=0, sensor_detect=sensor_detect)
        with mock.patch.object(mgr, "_preview_frame_is_degenerate") as probe, \
             mock.patch("module.cinepi_multi.time.sleep") as sleep:
            mgr._clearhdr_self_heal_if_stuck(camera_model="imx585_mono", launched_mode=0)
        probe.assert_not_called()
        sleep.assert_not_called()

    def test_checks_even_if_the_stale_redis_hdr_flag_says_zero(self):
        # The inverse: Redis says hdr=0 (stale) but the launched mode (3) is
        # actually one of the sensor's HDR modes -- must still check.
        sensor_detect = FakeSensorDetect(hdr_modes={3, 4})
        mgr = make_manager(hdr="0", sensor_mode=3, sensor_detect=sensor_detect)
        with mock.patch.object(mgr, "_preview_frame_is_degenerate", return_value=False) as probe, \
             mock.patch("module.cinepi_multi.time.sleep"):
            mgr._clearhdr_self_heal_if_stuck(camera_model="imx585_mono", launched_mode=3)
        probe.assert_called_once()

    def test_falls_back_to_the_redis_flag_when_mode_info_is_not_available(self):
        """Defensive fallback for a caller that doesn't pass
        camera_model/launched_mode (or no sensor_detect at all) -- still
        checks rather than silently skipping, using the old, imperfect
        signal instead of nothing."""
        mgr = make_manager(hdr="1", sensor_mode=3, sensor_detect=None)
        with mock.patch.object(mgr, "_preview_frame_is_degenerate", return_value=False) as probe, \
             mock.patch("module.cinepi_multi.time.sleep"):
            mgr._clearhdr_self_heal_if_stuck()  # no camera_model/launched_mode
        probe.assert_called_once()


class ClearHdrSelfHealShutterKickOrderingTests(unittest.TestCase):
    def test_tries_shutter_kick_before_any_mode_bounce(self):
        mgr = make_manager(hdr="1", sensor_mode=3)
        # Degenerate initially, still degenerate right after the shutter
        # kick (checked once more before falling back to a bounce), then
        # fixed by the first bounce.
        with mock.patch.object(mgr, "_preview_frame_is_degenerate", side_effect=[True, True, False]), \
             mock.patch.object(mgr, "_shock_shutter_angle") as shock, \
             mock.patch.object(mgr, "start_all") as start_all, \
             mock.patch("module.cinepi_multi.time.sleep"):
            mgr._clearhdr_self_heal_if_stuck()

        shock.assert_called_once()
        self.assertEqual(start_all.call_count, 2)  # one bounce, away + back

    def test_shutter_kick_alone_can_resolve_it_with_no_mode_bounce_at_all(self):
        mgr = make_manager(hdr="1", sensor_mode=3)
        with mock.patch.object(mgr, "_preview_frame_is_degenerate", side_effect=[True, False]), \
             mock.patch.object(mgr, "_shock_shutter_angle") as shock, \
             mock.patch.object(mgr, "start_all") as start_all, \
             mock.patch("module.cinepi_multi.time.sleep"):
            mgr._clearhdr_self_heal_if_stuck()

        shock.assert_called_once()
        start_all.assert_not_called()

    def test_shutter_kick_is_only_tried_once_not_on_every_bounce_attempt(self):
        mgr = make_manager(hdr="1", sensor_mode=3)
        with mock.patch.object(mgr, "_preview_frame_is_degenerate", return_value=True), \
             mock.patch.object(mgr, "_shock_shutter_angle") as shock, \
             mock.patch.object(mgr, "start_all"), \
             mock.patch("module.cinepi_multi.time.sleep"):
            mgr._clearhdr_self_heal_if_stuck()

        shock.assert_called_once()


class ClearHdrSelfHealBounceTests(unittest.TestCase):
    def test_a_degenerate_preview_triggers_exactly_one_bounce_away_and_back(self):
        mgr = make_manager(hdr="1", sensor_mode=3)
        # Still degenerate after the shutter kick, fixed by the following bounce.
        with mock.patch.object(mgr, "_preview_frame_is_degenerate", side_effect=[True, True, False]), \
             mock.patch.object(mgr, "_shock_shutter_angle"), \
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
             mock.patch.object(mgr, "_shock_shutter_angle"), \
             mock.patch.object(mgr, "start_all") as start_all, \
             mock.patch("module.cinepi_multi.logging.warning") as warn, \
             mock.patch("module.cinepi_multi.time.sleep"):
            mgr._clearhdr_self_heal_if_stuck()

        self.assertEqual(start_all.call_count, 2 * _CLEARHDR_SELF_HEAL_MAX_ATTEMPTS)
        # One "trying a shutter kick" warning, one "still stuck -- bouncing"
        # per bounce attempt, plus one final "still stuck, giving up" warning.
        self.assertEqual(warn.call_count, _CLEARHDR_SELF_HEAL_MAX_ATTEMPTS + 2)


class ShockShutterAngleTests(unittest.TestCase):
    def test_kicks_to_one_degree_then_restores_the_original_angle(self):
        mgr = make_manager()
        mgr.controller = FakeController(shutter_angle_nom=45.0)

        with mock.patch("module.cinepi_multi.time.sleep"):
            mgr._shock_shutter_angle()

        self.assertEqual(mgr.controller.set_shutter_a_calls, [1.0, 45.0])

    def test_toggles_the_self_heal_active_flag_around_the_kick_not_after(self):
        """The flag (drives the GUI's green shutter/fps tint, see
        simple_gui.py) must be True while set_shutter_a(1.0) actually runs,
        not just before/after it -- otherwise the GUI could show a plain
        white "1" for the one frame that matters."""
        mgr = make_manager()
        flag_during_kick = None

        def fake_set_shutter_a(value):
            nonlocal flag_during_kick
            if value == 1.0:
                flag_during_kick = mgr.controller.clearhdr_self_heal_active

        mgr.controller.set_shutter_a = fake_set_shutter_a
        with mock.patch("module.cinepi_multi.time.sleep"):
            mgr._shock_shutter_angle()

        self.assertTrue(flag_during_kick)
        self.assertFalse(mgr.controller.clearhdr_self_heal_active)  # cleared afterward

    def test_restores_the_original_angle_even_if_the_kick_itself_raises(self):
        mgr = make_manager()
        controller = FakeController(shutter_angle_nom=180.0)
        calls = []

        def fake_set_shutter_a(value):
            calls.append(value)
            if value == 1.0:
                raise RuntimeError("simulated sensor write failure")

        controller.set_shutter_a = fake_set_shutter_a
        mgr.controller = controller

        with mock.patch("module.cinepi_multi.time.sleep"):
            with self.assertRaises(RuntimeError):
                mgr._shock_shutter_angle()

        self.assertEqual(calls, [1.0, 180.0])  # restore still ran
        self.assertFalse(controller.clearhdr_self_heal_active)  # flag still cleared

    def test_no_controller_reference_is_a_safe_no_op(self):
        mgr = make_manager(controller=False)
        self.assertIsNone(mgr.controller)
        with mock.patch("module.cinepi_multi.time.sleep") as sleep:
            mgr._shock_shutter_angle()  # must not raise
        sleep.assert_not_called()


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

    def test_the_real_multipart_stream_framing_isolates_exactly_one_frame(self):
        """Round 9, 2026-08-30: the /stream framing was captured live off the
        rig rather than inferred. cinepi-raw (not the cinemate Flask app)
        serves it on :8000 as multipart MJPEG -- each part is a
        ``--nadjiebmjpegstreamer`` boundary line plus Content-Type and
        Content-Length headers, then the JPEG payload.

        Demonstrated to fail against the pre-fix ``data.find(b"\\xff\\xd9")``:
        with a mid-frame start the old search returned end=85532 against
        start=85608, an empty slice, so the probe fell into its except branch
        and reported healthy on a flat frame.
        """
        import numpy as np
        flat = self._fake_jpeg_bytes(np.full((480, 640), 40, dtype=np.uint8))
        rng = np.random.default_rng(0)
        varied = self._fake_jpeg_bytes(
            rng.integers(0, 256, size=(480, 640), dtype=np.uint8)
        )

        def part(payload):
            return (
                b"--nadjiebmjpegstreamer\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(payload)).encode() + b"\r\n\r\n"
                + payload
            )

        # A live MJPEG read almost never lands on a part boundary -- urlopen
        # connects mid-frame, so the buffer opens with the tail of whatever
        # frame was in flight, including that frame's EOI. Searching for EOI
        # from offset 0 therefore finds an EOI that sits *before* the first
        # SOI, the slice comes out empty, PIL raises, and the probe fails open
        # -- silently never detecting anything while looking installed and
        # healthy. That is the exact "silent no-op" failure round 8 flagged as
        # the real risk of the inferred framing. Searching from SOI fixes it.
        stream = varied[len(varied) // 2:] + part(flat) + part(varied)

        mgr = make_manager()
        fake_response = mock.MagicMock()
        fake_response.read.return_value = stream
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with mock.patch("urllib.request.urlopen", return_value=fake_response):
            self.assertTrue(mgr._preview_frame_is_degenerate())
            self.assertEqual(mgr._last_preview_unique_values, 1)

    def test_a_flat_mid_row_on_an_otherwise_real_frame_is_not_degenerate(self):
        """The probe measures the body, not one row at a fixed offset.

        Measured on the rig 2026-08-30: a live preview frame whose mid row read
        1 unique value while the whole frame read 145. A single-row check calls
        that degenerate and would bounce a healthy session. Reproduced here as
        a frame that is flat across its middle band but carries real structure
        above and below it.

        Demonstrated to fail against the pre-fix single-row measure
        (``row = frame[frame.shape[0] // 2]``), which reports degenerate.
        """
        import numpy as np
        rng = np.random.default_rng(1)
        frame = rng.integers(0, 256, size=(480, 640), dtype=np.uint8)
        frame[200:280, :] = 40          # flat band straddling the mid row
        jpeg_bytes = self._fake_jpeg_bytes(frame)

        mgr = make_manager()
        fake_response = mock.MagicMock()
        fake_response.read.return_value = jpeg_bytes
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with mock.patch("urllib.request.urlopen", return_value=fake_response):
            self.assertFalse(mgr._preview_frame_is_degenerate())

    def test_the_top_osd_strip_alone_does_not_make_a_flat_frame_look_healthy(self):
        """The inverse confound: the preview's top OSD strip carries real
        variation even when every image row is a flat pedestal. Skipping the
        top 5% keeps that strip from masking a genuine fill."""
        import numpy as np
        rng = np.random.default_rng(2)
        frame = np.full((480, 640), 16, dtype=np.uint8)
        frame[:20, :] = rng.integers(0, 256, size=(20, 640), dtype=np.uint8)
        jpeg_bytes = self._fake_jpeg_bytes(frame)

        mgr = make_manager()
        fake_response = mock.MagicMock()
        fake_response.read.return_value = jpeg_bytes
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with mock.patch("urllib.request.urlopen", return_value=fake_response):
            self.assertTrue(mgr._preview_frame_is_degenerate())

    def test_the_measured_unique_count_is_recorded_for_the_warning(self):
        """The WARNING the self-heal logs quotes the figure it acted on, so
        the probe has to leave it somewhere retrievable rather than collapsing
        straight to a bool."""
        import numpy as np
        flat = self._fake_jpeg_bytes(np.full((480, 640), 40, dtype=np.uint8))

        mgr = make_manager()
        fake_response = mock.MagicMock()
        fake_response.read.return_value = flat
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with mock.patch("urllib.request.urlopen", return_value=fake_response):
            mgr._preview_frame_is_degenerate()
        self.assertEqual(mgr._last_preview_unique_values, 1)

        # A probe failure records None, not a stale count from last time.
        with mock.patch("urllib.request.urlopen", side_effect=OSError("gone")):
            mgr._preview_frame_is_degenerate()
        self.assertIsNone(mgr._last_preview_unique_values)


class ClearHdrSelfHealSettingsGateTests(unittest.TestCase):
    """Round 9, 2026-08-30: the self-heal is off unless asked for.

    It hooks into start_all(), which every cold start and every resolution
    switch runs, and none of its recovery actions is proven -- the mode bounce
    and an earlier gain shock were both live-tested and failed, and the
    shutter kick's automated form has never run on hardware.
    """

    def _manager(self, settings):
        return CinePiManager(FakeRedis(), sensor_detect=None, settings=settings)

    def test_off_when_settings_are_not_supplied_at_all(self):
        mgr = CinePiManager(FakeRedis(), sensor_detect=None)
        self.assertFalse(mgr.clearhdr_self_heal_enabled)

    def test_off_by_default_when_the_key_is_absent(self):
        mgr = self._manager({"image_capture": {"hdr": {}}})
        self.assertFalse(mgr.clearhdr_self_heal_enabled)

    def test_on_only_when_explicitly_enabled(self):
        mgr = self._manager({"image_capture": {"hdr": {"self_heal": True}}})
        self.assertTrue(mgr.clearhdr_self_heal_enabled)

    def test_the_gate_blocks_the_self_heal_when_off(self):
        mgr = self._manager({"image_capture": {"hdr": {"self_heal": False}}})
        with mock.patch.object(mgr, "_clearhdr_self_heal_if_stuck") as heal:
            mgr._maybe_clearhdr_self_heal(camera_model="imx585", launched_mode=3)
        heal.assert_not_called()

    def test_the_gate_passes_the_launched_mode_through_when_on(self):
        mgr = self._manager({"image_capture": {"hdr": {"self_heal": True}}})
        with mock.patch.object(mgr, "_clearhdr_self_heal_if_stuck") as heal:
            mgr._maybe_clearhdr_self_heal(camera_model="imx585", launched_mode=3)
        heal.assert_called_once_with(camera_model="imx585", launched_mode=3)


class ClearHdrSelfHealSettingsLoaderTests(unittest.TestCase):
    def test_default_is_false(self):
        from module.config_loader import clearhdr_self_heal_enabled
        self.assertFalse(clearhdr_self_heal_enabled({}))
        self.assertFalse(clearhdr_self_heal_enabled({"image_capture": {}}))
        self.assertFalse(clearhdr_self_heal_enabled({"image_capture": {"hdr": {}}}))

    def test_decodes_the_usual_settings_boolean_spellings(self):
        from module.config_loader import clearhdr_self_heal_enabled
        for raw, expected in (
            (True, True), (False, False),
            ("true", True), ("false", False),
            ("1", True), ("0", False),
        ):
            with self.subTest(raw=raw):
                self.assertIs(
                    clearhdr_self_heal_enabled(
                        {"image_capture": {"hdr": {"self_heal": raw}}}
                    ),
                    expected,
                )

    def test_a_non_dict_hdr_block_does_not_raise(self):
        from module.config_loader import clearhdr_self_heal_enabled
        self.assertFalse(
            clearhdr_self_heal_enabled({"image_capture": {"hdr": "nonsense"}})
        )


if __name__ == "__main__":
    unittest.main()
