"""The in-app log queue must not grow forever.

QueueHandler feeds the startup-failure view. Nothing drains it -- the only
reader peeks under the mutex and takes the last 40 lines -- so an unbounded
queue grew for the whole life of the process. On a camera left running for
days that is a slow leak with no ceiling.
"""

import logging
import queue
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("termcolor", types.SimpleNamespace(colored=lambda text, *a, **k: text))

from module.logger import LOG_QUEUE_MAXSIZE, QueueHandler


def record(msg):
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)


class LogQueueBoundTests(unittest.TestCase):
    def test_the_queue_stops_growing_at_its_bound(self):
        q = queue.Queue(maxsize=10)
        handler = QueueHandler(q)
        handler.setFormatter(logging.Formatter("%(message)s"))

        for i in range(500):
            handler.emit(record(f"line {i}"))

        self.assertEqual(q.qsize(), 10)

    def test_it_keeps_the_newest_lines_not_the_oldest(self):
        q = queue.Queue(maxsize=3)
        handler = QueueHandler(q)
        handler.setFormatter(logging.Formatter("%(message)s"))

        for i in range(10):
            handler.emit(record(f"line {i}"))

        # When something has just gone wrong, the last lines are the ones worth
        # having -- the startup-failure view shows a tail, not a head.
        self.assertEqual(list(q.queue), ["line 7", "line 8", "line 9"])

    def test_emitting_never_blocks(self):
        # This runs inline on whichever thread called logging, including the
        # redis listener. A blocking put here would stall the whole system.
        q = queue.Queue(maxsize=1)
        handler = QueueHandler(q)
        handler.setFormatter(logging.Formatter("%(message)s"))

        for i in range(50):
            handler.emit(record(f"line {i}"))  # would hang if put() blocked

        self.assertEqual(q.qsize(), 1)

    def test_the_configured_bound_is_deep_enough_for_the_reader(self):
        self.assertGreaterEqual(LOG_QUEUE_MAXSIZE, 40)


if __name__ == "__main__":
    unittest.main()
