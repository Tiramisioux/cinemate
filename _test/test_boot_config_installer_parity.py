"""The installer and the settings editor must agree on what a camera section
for the same sensor looks like -- they are two writers of the same file.

They didn't: `_render_camera_section()` used to write `camera_auto_detect=1`
for every sensor, where `cinemate-install.sh`'s `resolve_sensor_overlay()`
writes 0 for imx283/imx585/imx585_mono (third-party sensors -- see
`_CAMERA_AUTO_DETECT_BY_MODEL`'s comment in boot_config.py for why). And
`overlay_line_for()` never emitted `ccmp`, which the installer always adds
for both imx585 variants (a real `imx585-overlay.dts` override gating 12-bit
CCMP ClearHDR -- see `overlay_line_for()`'s comment). An operator who
installed with one sensor and later switched sensors through the settings
editor would get a camera section shaped differently than a fresh install
with the new sensor would have produced -- silent drift between the only two
things that are ever allowed to write this file. See
development/todo-2026-09-27/CONFIG-TXT-FINDINGS.md.

The first test class pins the values directly, so a future edit to
`_CAMERA_AUTO_DETECT_BY_MODEL` or the `ccmp` rule fails loudly here even
without touching the installer. The second class is the stronger guard: it
sources the *real* cinemate-install.sh (the same way
scripts/make-release-image.sh already does, to render "the stock config.txt"
without keeping a second copy of it) and diffs its actual output against
boot_config.py's rendering for the same sensor -- so a future edit to the
installer's SENSOR_MODEL case that this module doesn't also learn about
fails here too, without anyone having to remember to update a hardcoded
table on this side.
"""

import re
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("psutil", types.SimpleNamespace())

from module.app.boot_config import _resolve_camera_auto_detect, overlay_line_for, parse_config_txt


# model -> (expected camera_auto_detect for a single sensor on its own,
# expected overlay-line suffix beyond "dtoverlay=<base>,<port>"). Mirrors
# cinemate-install.sh's resolve_sensor_overlay() case block.
INSTALLER_TABLE = {
    "imx477": {"auto_detect": "1", "extra": ""},
    "imx296": {"auto_detect": "1", "extra": ""},
    "imx283": {"auto_detect": "0", "extra": ""},
    "imx585": {"auto_detect": "0", "extra": ",ccmp"},
    "imx585_mono": {"auto_detect": "0", "extra": ",mono,ccmp"},
}

# The port cinemate-install.sh's own usage examples document for each model
# (all default to cam0 except imx585_mono, which the installer's header
# comment shows as CAM_PORT=cam1).
DOCUMENTED_PORT = {
    "imx477": "cam0",
    "imx296": "cam0",
    "imx283": "cam0",
    "imx585": "cam0",
    "imx585_mono": "cam1",
}


class OverlayLineMatchesInstallerTableTests(unittest.TestCase):
    """Direct, no-subprocess check: boot_config.py's own rendering against
    the hand-transcribed installer table above."""

    def test_overlay_line_matches_for_every_model(self):
        for model, expected in INSTALLER_TABLE.items():
            base = model[:-len("_mono")] if model.endswith("_mono") else model
            port = DOCUMENTED_PORT[model]
            with self.subTest(model=model):
                self.assertEqual(
                    overlay_line_for(model, port),
                    f"dtoverlay={base},{port}{expected['extra']}",
                )


def _run_installer_camera_section(sensor_model: str, cam_port: str, repo: Path) -> str:
    """Source the real cinemate-install.sh (guarded against running an
    install -- see the file's own closing comment) and call its
    configure_boot_config() for *sensor_model*/*cam_port*, the same
    technique scripts/make-release-image.sh uses to render "the stock
    config.txt" without keeping a second copy of it. Returns the resulting
    file's text.

    configure_boot_config() calls backup_file() (a no-op when the target
    path doesn't exist yet -- true here) and finishes with
    `sudo install -m 644 ...`; sudo is shadowed on PATH with a passthrough
    shim so this runs unprivileged, the same shape test_release_image_dry_run.py
    already uses for the same reason.
    """
    with tempfile.TemporaryDirectory() as workdir:
        work = Path(workdir)
        bin_dir = work / "bin"
        bin_dir.mkdir()
        sudo_shim = bin_dir / "sudo"
        sudo_shim.write_text("#!/bin/sh\nexec \"$@\"\n", encoding="utf-8")
        sudo_shim.chmod(0o755)

        config_out = work / "config.txt"
        script = (
            "set -Eeuo pipefail\n"
            "source ./cinemate-install.sh\n"
            "trap - EXIT\n"
            "configure_boot_config\n"
        )
        env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "SENSOR_MODEL": sensor_model,
            "CAM_PORT": cam_port,
            "CONFIG_TXT_PATH": str(config_out),
            "BACKUP_DIR": str(work / "backup"),
            "HOME": str(work),
        }
        result = subprocess.run(
            ["bash", "-c", script], cwd=str(repo), env=env,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"configure_boot_config failed for {sensor_model}/{cam_port}: "
                f"{result.stderr}"
            )
        return config_out.read_text(encoding="utf-8")


@unittest.skipUnless(sys.platform != "win32", "sources a bash script")
class InstallerVsEditorParityTests(unittest.TestCase):
    """Runs the real installer, not a copy of its logic."""

    def test_every_sensor_matches_the_real_installer(self):
        for model in INSTALLER_TABLE:
            port = DOCUMENTED_PORT[model]
            with self.subTest(model=model):
                installer_text = _run_installer_camera_section(model, port, ROOT)
                installer_state = parse_config_txt(installer_text)

                editor_port_key = f"{port}_sensor"
                self.assertEqual(
                    installer_state[editor_port_key], model,
                    f"installer's own output didn't parse back as {model} on {port} "
                    f"-- fixture/test bug, not the thing under test",
                )

                # The installer's rendered camera_auto_detect value, read
                # directly off the text (parse_config_txt doesn't track this
                # field -- it's write-only from this module's side).
                m = re.search(r"^camera_auto_detect=(\d)$", installer_text, re.MULTILINE)
                self.assertIsNotNone(m, "installer wrote no active camera_auto_detect line")
                installer_auto_detect = m.group(1)

                # The line itself: does boot_config.py write the identical
                # dtoverlay text the installer just wrote for this sensor?
                editor_line = overlay_line_for(model, port)
                self.assertIn(editor_line, installer_text)

                # And the auto-detect value the installer actually chose,
                # matched against what this module's own resolver would
                # choose for the same single-sensor state.
                resolved = _resolve_camera_auto_detect(
                    model if port == "cam0" else "none",
                    model if port == "cam1" else "none",
                )
                self.assertEqual(
                    installer_auto_detect, resolved,
                    f"installer wrote camera_auto_detect={installer_auto_detect} for "
                    f"{model}, boot_config.py's resolver would write {resolved}",
                )


if __name__ == "__main__":
    unittest.main()
