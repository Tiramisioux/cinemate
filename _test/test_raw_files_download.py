"""W9: the RAW pane's download path used to build a whole take into a temp
file on /tmp before a single byte reached the browser, with no cap on how
many downloads could run at once against the storage volume. These tests
cover the streaming replacement, the recording interlock, and the semaphore
-- none of which the existing suite touched.
"""

import io
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

_APP_PKG = types.ModuleType("module.app")
_APP_PKG.__path__ = [str(ROOT / "src" / "module" / "app")]
sys.modules.setdefault("module.app", _APP_PKG)

from flask import Flask

from module.app import raw_files
from module.app.settings_editor import settings_editor_bp
from module.redis_controller import ParameterKey


class FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)


def make_app(redis_values=None):
    app = Flask(__name__)
    app.testing = True
    app.config["REDIS_CONTROLLER"] = FakeRedis(redis_values)
    app.config["SETTINGS"] = {}
    app.register_blueprint(settings_editor_bp)
    return app


class RawFilesFixture(unittest.TestCase):
    """A real on-disk take under a temp MEDIA_ROOT, so resolve_take() and
    friends run against real Path.rglob()/stat() rather than a mock."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.media_root = Path(self._tmp.name)
        self.raw_root = self.media_root / "RAW"
        self.take_name = "A001_20260101_120000"
        self.take_dir = self.raw_root / self.take_name
        self.take_dir.mkdir(parents=True)
        self.frame_names = ["f000001.dng", "f000002.dng"]
        for n in self.frame_names:
            (self.take_dir / n).write_bytes(b"fake-dng-bytes-" + n.encode())

        self._patcher = mock.patch.object(raw_files, "MEDIA_ROOT", self.media_root)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def tearDown(self):
        # BoundedSemaphore has no reset(); tests that acquire it directly
        # release what they took so later tests in the module see it full.
        pass


class NullByteTakeNameTests(RawFilesFixture):
    def test_percent00_is_404_json_not_500(self):
        app = make_app()
        res = app.test_client().get("/settings-editor/api/raw/takes/%00abc/download")
        self.assertEqual(res.status_code, 404)
        self.assertFalse(res.get_json()["ok"])


class StreamTakeZipRoundTripTests(RawFilesFixture):
    def test_round_trip_is_byte_exact(self):
        data = b"".join(raw_files.stream_take_zip(self.take_dir))
        zf = zipfile.ZipFile(io.BytesIO(data))
        self.assertIsNone(zf.testzip())
        names = sorted(zf.namelist())
        self.assertEqual(names, sorted(f"{self.take_name}/{n}" for n in self.frame_names))
        for n in self.frame_names:
            self.assertEqual(
                zf.read(f"{self.take_name}/{n}"),
                (self.take_dir / n).read_bytes(),
            )


class RecordingInterlockTests(RawFilesFixture):
    def _recording_app(self):
        return make_app(redis_values={
            ParameterKey.IS_RECORDING.value: "1",
            ParameterKey.LAST_DNG_CAM0.value: str(self.take_dir / self.frame_names[0]),
        })

    def test_delete_refuses_active_take_with_409(self):
        app = self._recording_app()
        res = app.test_client().delete(f"/settings-editor/api/raw/takes/{self.take_name}")
        self.assertEqual(res.status_code, 409)
        self.assertTrue(self.take_dir.is_dir())

    def test_delete_allows_a_different_take(self):
        other = self.raw_root / "A001_20260101_130000"
        other.mkdir()
        (other / "f000001.dng").write_bytes(b"x")
        app = self._recording_app()
        res = app.test_client().delete("/settings-editor/api/raw/takes/A001_20260101_130000")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(other.is_dir())

    def test_bulk_delete_is_whole_request_409_and_deletes_nothing(self):
        other = self.raw_root / "A001_20260101_130000"
        other.mkdir()
        (other / "f000001.dng").write_bytes(b"x")
        app = self._recording_app()
        res = app.test_client().post(
            "/settings-editor/api/raw/bulk",
            json={"action": "delete", "names": [self.take_name, "A001_20260101_130000"]},
        )
        self.assertEqual(res.status_code, 409)
        self.assertTrue(self.take_dir.is_dir())
        self.assertTrue(other.is_dir())


class SemaphoreTests(RawFilesFixture):
    def test_third_concurrent_acquire_is_429_with_retry_after(self):
        self.assertTrue(raw_files.DOWNLOAD_SEMAPHORE.acquire(blocking=False))
        self.assertTrue(raw_files.DOWNLOAD_SEMAPHORE.acquire(blocking=False))
        try:
            app = make_app()
            res = app.test_client().get(
                f"/settings-editor/api/raw/takes/{self.take_name}/download"
            )
            self.assertEqual(res.status_code, 429)
            self.assertEqual(res.headers.get("Retry-After"), "5")
        finally:
            raw_files.DOWNLOAD_SEMAPHORE.release()
            raw_files.DOWNLOAD_SEMAPHORE.release()

    def test_permit_releases_when_generator_closes_early(self):
        # Simulate the route: it acquired one permit before handing the
        # generator to the response.
        self.assertTrue(raw_files.DOWNLOAD_SEMAPHORE.acquire(blocking=False))
        gen = raw_files.guarded_stream(raw_files.stream_take_zip(self.take_dir))
        next(gen)
        gen.close()  # GeneratorExit -> guarded_stream's finally -> sem.release()
        # If the release ran, the semaphore has its permit back.
        self.assertTrue(raw_files.DOWNLOAD_SEMAPHORE.acquire(blocking=False))
        raw_files.DOWNLOAD_SEMAPHORE.release()

    def test_head_does_not_leak_a_permit(self):
        # A HEAD response's body is never iterated by Werkzeug, so
        # guarded_stream()'s generator -- including its `finally` -- never
        # runs: the acquire() the route makes before building the Response
        # used to have no release path at all for this verb. Two curl -I
        # calls alone exhausted the two-permit cap, permanently, since
        # nothing but a restart could hand the permits back.
        #
        # `with c.head(...) as r:` matters here, not `c.head(...)` alone --
        # Response.call_on_close() fires when the WSGI layer closes the
        # response, and Flask's test client only does that within a `with`
        # block (or an explicit r.close()); a real WSGI server does it
        # unconditionally per the WSGI close() contract, so this is the test
        # client reproducing production behaviour, not a testing artifact.
        app = make_app()
        url = f"/settings-editor/api/raw/takes/{self.take_name}/download"
        with app.test_client() as c:
            with c.head(url) as r1:
                self.assertEqual(r1.status_code, 200)
            with c.head(url) as r2:
                self.assertEqual(r2.status_code, 200)

        # Both permits must be back: two independent non-blocking acquires
        # succeed, matching the fixed two-permit cap. try/finally so a
        # failure here (a partial leak) does not also corrupt every test
        # that runs after this one in the same process.
        got = []
        try:
            got.append(raw_files.DOWNLOAD_SEMAPHORE.acquire(blocking=False))
            got.append(raw_files.DOWNLOAD_SEMAPHORE.acquire(blocking=False))
        finally:
            for ok in got:
                if ok:
                    raw_files.DOWNLOAD_SEMAPHORE.release()
        self.assertEqual(got, [True, True])

    def test_permit_releases_only_once_even_if_both_paths_fire(self):
        # _Permit must not double-release: guarded_stream()'s finally and
        # Response.call_on_close() can both fire for an ordinary GET whose
        # body is fully consumed (finally on generator exhaustion,
        # call_on_close on the WSGI close() that follows). A genuine second
        # sem.release() on a BoundedSemaphore already back at its initial
        # count raises ValueError immediately -- verified in isolation
        # (threading.BoundedSemaphore(2): acquire, release, release ->
        # "Semaphore released too many times") -- so _Permit's guard is what
        # stands between a completed download and a crashed request thread.
        self.assertTrue(raw_files.DOWNLOAD_SEMAPHORE.acquire(blocking=False))
        try:
            permit = raw_files._Permit(raw_files.DOWNLOAD_SEMAPHORE)
            permit.release()
            permit.release()  # must be a silent no-op, not a second release
        except ValueError:
            self.fail("_Permit.release() called twice raised -- it must "
                       "guard the underlying semaphore, not just forward")

        # Semaphore is back at its starting count (one acquire, one real
        # release): both permits are available again.
        self.assertTrue(raw_files.DOWNLOAD_SEMAPHORE.acquire(blocking=False))
        self.assertTrue(raw_files.DOWNLOAD_SEMAPHORE.acquire(blocking=False))
        raw_files.DOWNLOAD_SEMAPHORE.release()
        raw_files.DOWNLOAD_SEMAPHORE.release()


class PerFileRouteTests(RawFilesFixture):
    def test_traversal_is_404(self):
        app = make_app()
        for bad in ("../../etc/passwd", "..%2F..%2Fetc%2Fpasswd"):
            res = app.test_client().get(
                f"/settings-editor/api/raw/takes/{self.take_name}/files/{bad}"
            )
            self.assertEqual(res.status_code, 404)

    def test_good_file_is_200(self):
        app = make_app()
        res = app.test_client().get(
            f"/settings-editor/api/raw/takes/{self.take_name}/files/{self.frame_names[0]}"
        )
        self.assertEqual(res.status_code, 200)


class ManifestTests(RawFilesFixture):
    def test_manifest_shape_matches_fixture(self):
        app = make_app()
        res = app.test_client().get(f"/settings-editor/api/raw/takes/{self.take_name}/files")
        body = res.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["file_count"], len(self.frame_names))
        self.assertEqual({f["name"] for f in body["files"]}, set(self.frame_names))
        self.assertFalse(body["recording"])

    def test_missing_take_manifest_is_404_json(self):
        app = make_app()
        res = app.test_client().get("/settings-editor/api/raw/takes/definitely-not-a-take/files")
        self.assertEqual(res.status_code, 404)
        self.assertFalse(res.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
