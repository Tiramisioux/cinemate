import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Provide lightweight stand-ins for optional system modules used by
# storage-automount so the unit tests can run in a minimal environment.
if "pyudev" not in sys.modules:
    sys.modules["pyudev"] = types.SimpleNamespace(Context=lambda: None)

if "redis" not in sys.modules:
    class _RedisStub:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("redis module unavailable – tests must patch StrictRedis")

    sys.modules["redis"] = types.SimpleNamespace(StrictRedis=_RedisStub)

if "psutil" not in sys.modules:
    sys.modules["psutil"] = types.SimpleNamespace(
        virtual_memory=lambda: types.SimpleNamespace(percent=0)
    )


def _load_storage_automount():
    module_path = REPO_ROOT / "services" / "storage-automount" / "storage-automount.py"
    spec = importlib.util.spec_from_file_location("storage_automount", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


storage_automount = _load_storage_automount()


class DummyRedisController:
    def __init__(self):
        self.values: dict[str, str] = {}
        dummy = types.SimpleNamespace(
            publish=lambda *args, **kwargs: None,
            keys=lambda pattern: [],
            delete=lambda *args, **kwargs: None,
        )
        self.r = dummy

    def set_value(self, key, value):
        name = key.value if hasattr(key, "value") else str(key)
        self.values[name] = str(value)

    def get_value(self, key, default=None):
        name = key.value if hasattr(key, "value") else str(key)
        return self.values.get(name, default)


class WarmupTests(unittest.TestCase):
    def setUp(self) -> None:
        storage_automount._warmup_tokens.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.mount_path = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_warmup_marks_device_once(self):
        fake_stat = types.SimpleNamespace(f_frsize=4096, f_bavail=1024 * 1024)
        writes: list[int] = []
        original_open = open

        class FakeFile:
            def __init__(self):
                self.bytes = 0

            def write(self, data):
                self.bytes += len(data)
                return len(data)

            def flush(self):
                pass

            def fileno(self):  # pragma: no cover - only for os.fsync signature
                return 0

            def __enter__(self):
                writes.append(self)
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def fake_open(path, mode="r", buffering=-1, *args, **kwargs):
            if str(path).endswith(".warmup") and "w" in mode:
                return FakeFile()
            return original_open(path, mode, buffering, *args, **kwargs)

        with mock.patch.object(storage_automount, "os") as os_mod:
            os_mod.statvfs.return_value = fake_stat
            os_mod.fsync.return_value = None
            os_mod.stat.return_value = types.SimpleNamespace(st_dev=42)
            os_mod.path = storage_automount.os.path
            with mock.patch("builtins.open", fake_open), \
                 mock.patch.object(storage_automount, "_mount_token", return_value="token"):
                storage_automount._maybe_warmup("/dev/test", self.mount_path, "usb_ssd")
                storage_automount._maybe_warmup("/dev/test", self.mount_path, "usb_ssd")

        self.assertEqual(len(writes), 1, "warm-up should run only once per mount")
        self.assertIn("/dev/test", storage_automount._warmup_tokens)
        self.assertTrue((self.mount_path / ".warmup.stamp").exists())


class CadenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.redis_controller = DummyRedisController()

    def test_cadence_activates_on_first_dng(self):
        from src.module.redis_controller import ParameterKey
        from src.module.redis_listener import RedisListener

        class FakeRedis:
            def __init__(self, *args, **kwargs):
                self.store = {}

            def pubsub(self):
                return types.SimpleNamespace(subscribe=lambda *a, **k: None)

        with mock.patch("src.module.redis_listener.redis.StrictRedis", FakeRedis), \
             mock.patch.object(RedisListener, "start_listeners", lambda self: None):
            listener = RedisListener(self.redis_controller, ssd_monitor=None)

        listener.framecount = 5
        listener.is_recording = True
        listener._arm_cadence()
        self.assertFalse(listener.cadence_active)

        listener._handle_first_dng("redis", "cam0:stamp")
        self.assertTrue(listener.cadence_active)
        self.assertGreater(listener.ignore_until_frame, listener.framecount)
        self.assertEqual(
            self.redis_controller.get_value(ParameterKey.CADENCE_ACTIVE.value),
            "1",
        )

        listener._reset_cadence()
        listener._arm_cadence()
        listener._handle_first_dng("redis", "0")
        self.assertFalse(listener.first_dng_seen, "Zero marker should be ignored")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
