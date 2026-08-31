"""cinemate must not write the wide_dynamic_range subdev control.

cinepi-raw owns it end to end: Options::Parse() forces it to 0, enumerates,
then sets it back to 1 for --hdr sensor and re-enumerates. Anything cinemate
writes is discarded at the next launch, and every SDR<->HDR transition is a
relaunch (_resolution_change_needs_restart), so the write bought nothing.

What it cost: it fired from set_resolution() *before* that relaunch, while
the outgoing cinepi-raw still held the subdev. Round-6 hardware notes record
it losing that race on effectively every resolution change all session. Since
cinepi-raw 58cf8cc an unconfirmed wide_dynamic_range=1 is fatal -- cinepi-raw
throws rather than launch against a combiner that is off -- so a second writer
on that control can take ClearHDR down entirely.

See dev-track/C9-clearhdr-12bit-restore/PLAN.md section R.
"""

import ast
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.cinepi_controller import CinePiController

CONTROLLER_SRC = ROOT / "src" / "module" / "cinepi_controller.py"
SRC_DIR = ROOT / "src"


class NoWideDynamicRangeWriterTests(unittest.TestCase):
    def test_the_helper_is_gone(self):
        self.assertFalse(
            hasattr(CinePiController, "_set_wide_dynamic_range"),
            "cinemate must not own a wide_dynamic_range writer; cinepi-raw "
            "sets the control itself around its own camera-manager reset.",
        )

    def test_no_module_shells_out_to_set_the_control(self):
        """No cinemate source may build a `--set-ctrl wide_dynamic_range=` call.

        Checked as text across src/ rather than by mocking one call path: the
        point is that *no* module acquires this writer again, whether from
        set_resolution, a GUI handler or a future autodetect path.
        """
        offenders = []
        for path in sorted(SRC_DIR.rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue          # comments explaining the removal are fine
                if "set-ctrl" in line and "wide_dynamic_range" in line:
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {stripped}")

        self.assertEqual(
            offenders, [],
            "cinemate must not write wide_dynamic_range -- it contends with "
            "cinepi-raw's own enable, which is fatal since 58cf8cc:\n"
            + "\n".join(offenders),
        )

    def test_the_hdr_redis_key_is_still_published_on_a_mode_change(self):
        """The removal must not take the launch-line signal with it.

        cinepi-raw decides --hdr sensor from the hdr Redis key, so
        _publish_resolution_gui_state() setting it is the whole remaining
        contract between a mode choice and ClearHDR actually engaging.
        """
        src = CONTROLLER_SRC.read_text(encoding="utf-8")
        func = next(
            n for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef)
            and n.name == "_publish_resolution_gui_state"
        )
        segment = ast.get_source_segment(src, func) or ""
        self.assertIn("ParameterKey.HDR.value", segment)
        self.assertIn("resolution_info.get('hdr'", segment)


if __name__ == "__main__":
    unittest.main()
