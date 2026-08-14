import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.cli_commands import CommandExecutor


def make_executor():
    controller = mock.MagicMock()
    app = mock.MagicMock()
    return CommandExecutor(controller, app), controller, app


class DispatchReturnValueTests(unittest.TestCase):
    """Phase 1: handle_received_data()/handle_rec_command() must return
    (ok, message) without changing what the bound handler is called with —
    CLI/serial callers still ignore the tuple entirely."""

    def test_blank_input_is_unknown_command_and_silent(self):
        executor, controller, _ = make_executor()
        self.assertEqual(executor.handle_received_data("   "), (False, "unknown command"))
        controller.rec.assert_not_called()

    def test_unrecognized_command(self):
        executor, _, _ = make_executor()
        self.assertEqual(executor.handle_received_data("nonsense"), (False, "unknown command"))

    def test_bare_rec_dispatches_and_returns_ok(self):
        executor, controller, _ = make_executor()
        self.assertEqual(executor.handle_received_data("rec"), (True, ""))
        controller.rec.assert_called_once_with(record_override=None)

    def test_stop_alias_dispatches_through_generic_path(self):
        executor, controller, _ = make_executor()
        self.assertEqual(executor.handle_received_data("stop"), (True, ""))
        controller.rec.assert_called_once_with()

    def test_rec_with_camera_target_and_timed_frames(self):
        executor, controller, _ = make_executor()
        self.assertEqual(executor.handle_received_data("rec cam0 f 48"), (True, ""))
        controller.rec.assert_called_once_with("f", 48, record_override="cam0")

    def test_rec_frames_missing_amount_is_missing_argument(self):
        executor, controller, _ = make_executor()
        self.assertEqual(executor.handle_received_data("rec f"), (False, "missing argument"))
        controller.rec.assert_not_called()

    def test_rec_frames_bad_amount_is_bad_argument(self):
        executor, controller, _ = make_executor()
        self.assertEqual(executor.handle_received_data("rec f notanumber"), (False, "bad argument"))
        controller.rec.assert_not_called()

    def test_rec_unknown_token_is_bad_argument(self):
        executor, controller, _ = make_executor()
        self.assertEqual(executor.handle_received_data("rec bogus"), (False, "bad argument"))
        controller.rec.assert_not_called()

    def test_set_iso_with_valid_int_dispatches_and_coerces_type(self):
        executor, controller, _ = make_executor()
        self.assertEqual(executor.handle_received_data("set iso 800"), (True, ""))
        controller.set_iso.assert_called_once_with(800)
        self.assertIsInstance(controller.set_iso.call_args[0][0], int)

    def test_set_iso_bad_argument(self):
        executor, controller, _ = make_executor()
        self.assertEqual(executor.handle_received_data("set iso notanumber"), (False, "bad argument"))
        controller.set_iso.assert_not_called()

    def test_set_iso_missing_argument(self):
        executor, controller, _ = make_executor()
        self.assertEqual(executor.handle_received_data("set iso"), (False, "missing argument"))
        controller.set_iso.assert_not_called()

    def test_inc_iso_no_argument_command_dispatches(self):
        executor, controller, _ = make_executor()
        self.assertEqual(executor.handle_received_data("inc iso"), (True, ""))
        controller.inc_iso.assert_called_once_with()

    def test_multi_type_command_bare_toggles(self):
        executor, controller, _ = make_executor()
        self.assertEqual(executor.handle_received_data("set resolution"), (True, ""))
        controller.set_resolution.assert_called_once_with()

    def test_multi_type_command_with_int_argument(self):
        executor, controller, _ = make_executor()
        self.assertEqual(executor.handle_received_data("set resolution 2"), (True, ""))
        controller.set_resolution.assert_called_once_with(2)

    def test_longest_prefix_match_wins(self):
        executor, controller, _ = make_executor()
        # "set shutter a nom" must not be shadowed by the shorter "set shutter a".
        self.assertEqual(executor.handle_received_data("set shutter a nom 172.8"), (True, ""))
        controller.set_shutter_a_nom.assert_called_once_with(172.8)
        controller.set_shutter_a.assert_not_called()


class DispatchLockTests(unittest.TestCase):
    """F13/section 7: dispatch is serialised behind a single lock, and a
    timed-out acquire must surface as ('busy'), not raise or hang."""

    def test_lock_timeout_returns_busy_without_calling_handler(self):
        executor, controller, _ = make_executor()

        class NeverAcquires:
            def acquire(self, timeout=None):
                return False

            def release(self):
                raise AssertionError("release() must not be called when acquire() failed")

        executor._dispatch_lock = NeverAcquires()
        self.assertEqual(executor.handle_received_data("rec"), (False, "busy"))
        controller.rec.assert_not_called()

    def test_lock_is_released_after_successful_dispatch(self):
        executor, controller, _ = make_executor()
        executor.handle_received_data("rec")
        # A second call must not block/deadlock if the lock was released.
        self.assertEqual(executor.handle_received_data("rec"), (True, ""))
        self.assertEqual(controller.rec.call_count, 2)

    def test_lock_is_released_even_when_command_unknown(self):
        executor, _, _ = make_executor()
        executor.handle_received_data("nonsense")
        self.assertTrue(executor._dispatch_lock.acquire(timeout=0))
        executor._dispatch_lock.release()


if __name__ == "__main__":
    unittest.main()
