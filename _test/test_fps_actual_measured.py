"""fps_actual must report the measured sensor rate, not a seeded constant.

The key was dead for the life of the system. RedisListener derived it from a
`sensorTimestamp` field in the cp_stats payload, but cinepi-raw builds that
JSON in cinepi/cinepi_controller.cpp and has never published such a key -- it
publishes `framerate` (1e9 / the gap between consecutive sensor timestamps,
computed per completed request in core/rpicam_app.cpp). So the deque feeding
the calculation stayed empty, the setter never ran, and fps_actual held the
literal 24 that cinemate-install.sh seeds at install time. A camera locked to
40 fps reported 24, and the web GUI showed that 24 as the fps on connect.

These tests pin the four properties that were wrong or at risk:
  1. a measured rate reaches the key at all;
  2. it is not biased high by averaging rates instead of intervals;
  3. dual-sensor runs report one camera, not a blend of two;
  4. drop detection keeps the *instantaneous* rate it depends on.
"""

import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from module.redis_listener import RedisListener  # noqa: E402


class _FakeRedisController:
    def __init__(self):
        self.store = {}

    def set_value(self, key, value):
        self.store[key] = value

    def get_value(self, key, default=None):
        return self.store.get(key, default)


class _Listener:
    """RedisListener's framerate surface without Redis, threads or a camera."""

    FPS_ACTUAL_WINDOW = RedisListener.FPS_ACTUAL_WINDOW
    _record_framerate_sample = RedisListener._record_framerate_sample
    _publish_measured_framerate = RedisListener._publish_measured_framerate

    def __init__(self):
        self.framerate_samples = {}
        self.redis_controller = _FakeRedisController()

    def feed(self, fps, frames, port="cam0", jitter=0.0, seed=None):
        rng = random.Random(seed)
        for _ in range(frames):
            interval = 1.0 / fps + (rng.uniform(-jitter, jitter) if jitter else 0.0)
            self._record_framerate_sample(port, 1.0 / interval)
            self._publish_measured_framerate()

    @property
    def published(self):
        return self.redis_controller.get_value("fps_actual")


def test_measured_rate_reaches_the_key():
    listener = _Listener()
    listener.feed(40.0, frames=100)
    assert listener.published == 40.0


def test_key_is_untouched_before_any_sample_arrives():
    # Nothing measured yet must not publish a fabricated value -- the caller
    # runs this on every cp_stats message, including before the first frame.
    listener = _Listener()
    listener._publish_measured_framerate()
    assert listener.published is None


def test_jittered_intervals_do_not_bias_the_reported_rate_high():
    # The regression guarded here: averaging the per-frame *rates* overstates
    # the true rate whenever the interval jitters, because mean(1/dt) >
    # 1/mean(dt). At 40 fps with +/-1.5 ms of jitter that reported ~40.25.
    for fps in (24.0, 25.0, 40.0, 50.0, 60.0):
        listener = _Listener()
        listener.feed(fps, frames=400, jitter=0.0015, seed=1)
        assert abs(listener.published - fps) / fps < 0.005, (
            f"{fps} fps reported as {listener.published}"
        )


def test_a_rate_change_converges_within_one_window():
    listener = _Listener()
    listener.feed(24.0, frames=100)
    assert listener.published == 24.0
    listener.feed(48.0, frames=RedisListener.FPS_ACTUAL_WINDOW)
    assert listener.published == 48.0


def test_window_stays_bounded():
    listener = _Listener()
    listener.feed(24.0, frames=RedisListener.FPS_ACTUAL_WINDOW * 3)
    assert len(listener.framerate_samples["cam0"]) == RedisListener.FPS_ACTUAL_WINDOW


def test_dual_sensor_reports_one_camera_rather_than_a_blend():
    # cam0 and cam1 share the cp_stats channel. Averaging both into one key
    # would report ~32 for a 24/50 pair -- a rate neither camera is running.
    listener = _Listener()
    listener.feed(24.0, frames=100, port="cam0")
    listener.feed(50.0, frames=100, port="cam1")
    assert listener.published == 24.0


def test_cam1_is_reported_when_cam0_never_publishes():
    listener = _Listener()
    listener.feed(30.0, frames=50, port="cam1")
    assert listener.published == 30.0


def test_reconfigure_clears_the_window():
    # A mode switch changes the rate; averaging across the boundary would
    # report a number from neither side of it.
    listener = _Listener()
    listener.feed(24.0, frames=100)
    listener.framerate_samples.clear()
    listener._publish_measured_framerate()
    assert listener.published == 24.0, "stale key is kept, not zeroed"
    listener.feed(48.0, frames=5)
    assert listener.published == 48.0, "post-clear samples are not blended with pre-clear ones"


def test_publishing_does_not_smooth_the_instantaneous_rate():
    # Drop detection's fallback tier compares current_framerate against the
    # requested fps to spot a single stalled frame. It must keep seeing the
    # raw per-frame value, so the smoothing added for fps_actual must not be
    # written back onto that attribute.
    listener = _Listener()
    listener.current_framerate = 12.0
    listener.feed(24.0, frames=100)
    assert listener.current_framerate == 12.0
