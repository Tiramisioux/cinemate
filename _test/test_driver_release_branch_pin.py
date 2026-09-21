"""WP-CM-13: the installer pins both sensor driver forks at their release
branch, `cinemate-modes`, not at the older lane-specific names.

Both `Tiramisioux/imx585-v4l2-driver` and `Tiramisioux/imx283-v4l2-driver`
grew a `cinemate-modes` branch that carries the aspect-ratio crop family, the
sensor-coordinate crop fix and (for imx283) the `6.12.y` merge. The old pins
(`cinemate-7modes`, `6.12.y`) still exist and still work, but a fresh install
should choose the release branch, not rediscover it by reading the script.
The default stays overridable from the environment, exactly as before.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "cinemate-install.sh"


def _default_ref(script_text: str, var_name: str) -> str:
    """The `:-default` fallback the installer assigns *var_name* from its own
    same-named environment variable, e.g. `FOO="${FOO:-bar}"` -> "bar"."""
    match = re.search(
        rf'{re.escape(var_name)}="\$\{{{re.escape(var_name)}:-([^}}]*)\}}"',
        script_text,
    )
    assert match, f"{var_name} default assignment not found in {INSTALLER}"
    return match.group(1)


class DriverReleaseBranchPinTests(unittest.TestCase):
    def setUp(self):
        self.script_text = INSTALLER.read_text()

    def test_imx585_driver_pins_the_release_branch(self):
        self.assertEqual(
            _default_ref(self.script_text, "IMX585_DRIVER_REPO_REF"),
            "cinemate-modes",
        )

    def test_imx283_driver_pins_the_release_branch(self):
        self.assertEqual(
            _default_ref(self.script_text, "IMX283_DRIVER_REPO_REF"),
            "cinemate-modes",
        )

    def test_both_pins_stay_overridable_from_the_environment(self):
        # The `:-` form only ever supplies a default when the variable is
        # unset/empty in the environment -- still true after the value
        # inside it changes.
        self.assertIn('IMX585_DRIVER_REPO_REF="${IMX585_DRIVER_REPO_REF:-',
                       self.script_text)
        self.assertIn('IMX283_DRIVER_REPO_REF="${IMX283_DRIVER_REPO_REF:-',
                       self.script_text)


if __name__ == "__main__":
    unittest.main()
