"""cinemate must not write the wide_dynamic_range subdev control.

cinepi-raw owns it: Options::Parse() forces it to 0, enumerates, then sets it
back to 1 for --hdr sensor and re-enumerates. Anything cinemate writes is
discarded at the next launch, and every SDR<->HDR transition is a relaunch
(_resolution_change_needs_restart), so the write bought nothing.

What it cost: it fired from _publish_resolution_gui_state() *before* that
relaunch, while the outgoing cinepi-raw still held the subdev -- round-6
hardware notes record it losing that race on effectively every resolution
change. It also fired mid-take, where _is_recording() suppresses the relaunch
but did not suppress the write. And since cinepi-raw 58cf8cc an unconfirmed
wide_dynamic_range=1 is fatal, so a second writer on that control is a
liability rather than merely dead weight.

The publishing side of the remaining contract is covered behaviourally by
_test/test_clearhdr_hdr_key_published.py.

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

CONTROL = "wide_dynamic_range"
# v4l2-ctl spells --set-ctrl and -c interchangeably; both must be caught.
SET_CTRL_FLAGS = ("--set-ctrl", "-c")
SCAN_ROOTS = ("src", "scripts", "tools")


def _module_string_constants(tree):
    """Module-level ``NAME = "literal"`` bindings, so a hoisted control name
    is still visible at the call site.

    Without this, ``CTRL = "wide_dynamic_range"`` followed by ``f"{CTRL}={v}"``
    reads as the identifier ``CTRL`` and slips the check -- verified as a real
    bypass of the earlier line-based version of this test.
    """
    consts = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                consts[target.id] = node.value.value
    return consts


def _string_parts(node, consts):
    """Every literal fragment of a call, f-strings and concatenation included.

    A line-based grep misses ``f"{CONTROL}={value}"`` and misses a call a
    formatter has wrapped across lines -- both were demonstrated to bypass the
    first version of this test. Walking the AST catches them; *consts*
    additionally resolves a name bound to a module-level string literal.
    """
    parts = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            parts.append(sub.value)
        elif isinstance(sub, ast.Name):
            parts.append(consts.get(sub.id, sub.id))
        elif isinstance(sub, ast.Attribute):
            parts.append(sub.attr)
    return parts


class NoWideDynamicRangeWriterTests(unittest.TestCase):
    def test_the_helper_is_gone(self):
        self.assertFalse(
            hasattr(CinePiController, "_set_wide_dynamic_range"),
            "cinemate must not own a wide_dynamic_range writer; cinepi-raw "
            "sets the control itself around its own camera-manager reset.",
        )

    def test_no_python_source_builds_a_set_ctrl_call_for_it(self):
        """AST-based, so a rename, an f-string or a wrapped line cannot slip past."""
        offenders = []
        for root in SCAN_ROOTS:
            for path in sorted((ROOT / root).rglob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
                consts = _module_string_constants(tree)
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    parts = _string_parts(node, consts)
                    if CONTROL not in " ".join(parts):
                        continue
                    if any(f in parts for f in SET_CTRL_FLAGS):
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}: "
                            f"v4l2-ctl set-ctrl call mentioning {CONTROL}"
                        )
        self.assertEqual(
            offenders, [],
            "cinemate must not write wide_dynamic_range -- it contends with "
            "cinepi-raw's own enable, which is fatal since 58cf8cc:\n"
            + "\n".join(offenders),
        )

    def test_no_python_source_sets_it_through_a_raw_ioctl(self):
        """The v4l2-ctl ban is pointless if the same write can go via ioctl.

        Matched on identifier references, not on file text: the comments in
        this repo discuss VIDIOC_S_CTRL by name, and a text scan flags its own
        documentation.
        """
        wanted = {"VIDIOC_S_CTRL", "VIDIOC_S_EXT_CTRLS"}
        offenders = []
        for root in SCAN_ROOTS:
            for path in sorted((ROOT / root).rglob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
                for node in ast.walk(tree):
                    name = (
                        node.id if isinstance(node, ast.Name)
                        else node.attr if isinstance(node, ast.Attribute)
                        else None
                    )
                    if name in wanted:
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: {name}")
        self.assertEqual(
            offenders, [],
            "cinemate must not program sensor controls by ioctl either:\n"
            + "\n".join(offenders),
        )

    def test_no_shell_script_sets_it(self):
        offenders = []
        for root in SCAN_ROOTS:
            for path in sorted((ROOT / root).rglob("*.sh")):
                for lineno, line in enumerate(
                    path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                ):
                    stripped = line.strip()
                    if stripped.startswith("#") or CONTROL not in stripped:
                        continue
                    if any(f in stripped for f in SET_CTRL_FLAGS):
                        offenders.append(f"{path.relative_to(ROOT)}:{lineno}")
        self.assertEqual(offenders, [], "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
