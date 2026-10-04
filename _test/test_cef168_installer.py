"""Pinefeat CEF168 autofocus install step: opt-in, pinned, idempotent, warn-not-abort.

What this guards, and what it cannot:

* `install_cef168_support()` in cinemate-install.sh is run against a scratch
  tree with fake `sudo`, `dkms`, `apt`, `git`, `dtc`. That proves the step's
  *logic* -- off by default, builds once and skips on the second run, rebuilds
  when the pinned upstream commit changes, never aborts the installer, never
  enables the overlay. It does NOT prove DKMS can build cef168.c against a real
  Raspberry Pi kernel; that needs a Pi (gate G0.8/G0.9 in
  development/pinefeat-cef168/PLAN.md).
* `scripts/cef168-module-installed.sh` is the one definition of "is cef168.ko
  installed for this kernel". WP3 re-implements the same three steps in Python,
  so the cases below are the contract that Python version must also meet.
* The overlay's sensor flags and its dormant fragments are two lists that must
  agree (`imx477 = <0>, "+10"` has to enable the fragment that merges into
  `imx477@1a`). A comment cannot fail; the mapping test can. If dtc is present
  the overlay is also compiled.

The sandbox test runs under the installer's own `set -Eeuo pipefail` and calls
the step plainly, the way main() does, so an unguarded failing command would
abort the script here exactly as it would in a real install.
"""

import os
import re
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "cinemate-install.sh"
HELPER = ROOT / "scripts" / "cef168-module-installed.sh"
OVERLAY_DIR = ROOT / "resources" / "overlays" / "cef168"
OVERLAY = OVERLAY_DIR / "cef168-overlay.dts"

PINNED = "e3abfb2"
KERNEL = "6.12.96+rpt-rpi-v8"
FAKE_HEAD = PINNED + "0" * (40 - len(PINNED))


class StaticContractTests(unittest.TestCase):
    def setUp(self):
        self.installer = INSTALLER.read_text(encoding="utf-8")

    def test_off_by_default(self):
        self.assertIn('INSTALL_CEF168_AF="${INSTALL_CEF168_AF:-0}"', self.installer)

    def test_upstream_is_pinned_to_the_reviewed_commit(self):
        self.assertIn('CEF168_REPO_REF="${CEF168_REPO_REF:-' + PINNED + '}"', self.installer)
        self.assertIn('CEF168_REPO_URL="${CEF168_REPO_URL:-https://github.com/pinefeat/cef168.git}"', self.installer)

    def test_usage_header_and_summary_mention_it(self):
        header = "\n".join(self.installer.splitlines()[:20])
        self.assertIn("INSTALL_CEF168_AF=1", header)
        self.assertIn("cef168_af=$INSTALL_CEF168_AF", self.installer)

    def test_step_is_wired_into_main(self):
        self.assertRegex(self.installer, r"(?m)^    install_cef168_support$")

    def test_installer_never_edits_config_txt_for_cef168(self):
        # D3: CineMate enables the overlay itself, only when the module exists.
        body = self.installer.split("install_cef168_support() {", 1)[1].split("\ninstall_sensor_tuning_overrides()", 1)[0]
        self.assertNotIn("config.txt\"", body.replace("/boot/firmware/config.txt and reboot", ""))
        self.assertNotIn("ensure_line_in_root_file", body)
        self.assertNotIn("configure_boot_config", body)

    def test_dkms_packaging(self):
        conf = (OVERLAY_DIR / "dkms.conf").read_text(encoding="utf-8")
        self.assertIn('PACKAGE_NAME="cef168"', conf)
        self.assertRegex(conf, r'(?m)^PACKAGE_VERSION="[^"]+"$')
        self.assertIn('BUILT_MODULE_NAME[0]="cef168"', conf)
        self.assertIn('AUTOINSTALL="yes"', conf)
        kbuild = (OVERLAY_DIR / "Kbuild").read_text(encoding="utf-8")
        self.assertRegex(kbuild, r"(?m)^obj-m := cef168\.o$")

    def test_helper_is_executable(self):
        self.assertTrue(HELPER.stat().st_mode & stat.S_IXUSR)


class OverlaySourceTests(unittest.TestCase):
    """Sensor flag <-> dormant fragment mapping, read from the source text."""

    def setUp(self):
        self.src = OVERLAY.read_text(encoding="utf-8")

    def test_every_sensor_flag_enables_the_fragment_for_that_sensor(self):
        flags = dict(re.findall(r'(?m)^\t\t(imx\d+) = <0>, "\+(\d+)";$', self.src))
        # Floor: the extractor found the flags at all (a changed syntax must
        # fail here, not compare two empty sets).
        self.assertGreaterEqual(len(flags), 4, f"extractor suspect, found {flags}")
        for sensor, index in flags.items():
            with self.subTest(sensor=sensor):
                frag = re.search(
                    rf"fragment@{index} \{{.*?__dormant__ \{{\s*{sensor}@1a \{{\s*lens-focus = <&lens>;",
                    self.src,
                    re.S,
                )
                self.assertIsNotNone(frag, f"flag {sensor} -> +{index} does not enable a fragment merging into {sensor}@1a")

    def test_cam0_retargets_the_lens_and_every_sensor_fragment(self):
        fragments = re.findall(r"(?m)^\t(\w+): fragment@(?:2|1\d) \{$", self.src)
        self.assertGreaterEqual(len(fragments), 5, f"extractor suspect, found {fragments}")
        cam0 = re.search(r"cam0 = (.*?);\n", self.src, re.S).group(1)
        for label in fragments:
            with self.subTest(fragment=label):
                self.assertIn(f"<&{label}>, \"target:0=\", <&i2c_csi_dsi0>", cam0)

    def test_sensor_merge_nodes_have_no_label(self):
        # A label gives the node a phandle; the merge would then overwrite the
        # real sensor node's phandle.
        self.assertIsNone(re.search(r"\w+:\s*imx\d+@1a", self.src))

    @unittest.skipUnless(shutil.which("dtc"), "dtc not installed")
    def test_compiles_and_carries_the_lens_node(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cef168.dtbo"
            subprocess.run(
                ["dtc", "-@", "-I", "dts", "-O", "dtb", "-W", "no-unit_address_vs_reg", "-o", str(out), str(OVERLAY)],
                check=True,
                capture_output=True,
            )
            text = subprocess.run(
                ["dtc", "-I", "dtb", "-O", "dts", str(out)], check=True, capture_output=True, text=True
            ).stdout
        self.assertIn('compatible = "pinefeat,cef168"', text)
        self.assertIn("reg = <0x0d>", text)
        # Unresolved base-tree labels must be exported as fixups, not baked in.
        for symbol in ("i2c_csi_dsi", "i2c_csi_dsi0", "i2c0if", "i2c0mux"):
            self.assertIn(symbol, text)


class HelperTests(unittest.TestCase):
    """scripts/cef168-module-installed.sh: the contract for the Python port."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = Path(self._td.name)
        self.kdir = self.root / KERNEL
        (self.kdir / "kernel" / "lib").mkdir(parents=True)

    def run_helper(self, *args):
        env = dict(os.environ, CEF168_MODULES_ROOT=str(self.root))
        return subprocess.run([str(HELPER), *args], capture_output=True, text=True, env=env)

    def index(self, *lines):
        (self.kdir / "modules.dep").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def place(self, rel):
        path = self.kdir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def test_dkms_install_location(self):
        self.place("updates/dkms/cef168.ko.xz")
        self.index("kernel/lib/crc8.ko.xz:", "updates/dkms/cef168.ko.xz: kernel/lib/crc8.ko.xz")
        result = self.run_helper("-v", KERNEL)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "updates/dkms/cef168.ko.xz")

    def test_pinefeat_make_install_location_uncompressed(self):
        self.place("kernel/drivers/media/i2c/cef168.ko")
        self.index("kernel/drivers/media/i2c/cef168.ko: kernel/lib/crc8.ko.xz")
        self.assertEqual(self.run_helper(KERNEL).returncode, 0)

    def test_every_compression_suffix(self):
        for suffix in ("", ".xz", ".zst", ".gz"):
            with self.subTest(suffix=suffix):
                rel = f"updates/dkms/cef168.ko{suffix}"
                self.place(rel)
                self.index(f"{rel}:")
                self.assertEqual(self.run_helper(KERNEL).returncode, 0)

    def test_stale_index_does_not_count(self):
        # depmod has not been re-run after the file was removed.
        self.index("updates/dkms/cef168.ko.xz: kernel/lib/crc8.ko.xz")
        self.assertEqual(self.run_helper(KERNEL).returncode, 1)

    def test_file_without_an_index_entry_does_not_count(self):
        # Present on disk, never run through depmod: the kernel will not autoload it.
        self.place("updates/dkms/cef168.ko.xz")
        self.index("kernel/lib/crc8.ko.xz:")
        self.assertEqual(self.run_helper(KERNEL).returncode, 1)

    def test_other_kernel_release_does_not_count(self):
        self.place("updates/dkms/cef168.ko.xz")
        self.index("updates/dkms/cef168.ko.xz:")
        self.assertEqual(self.run_helper("6.1.21+rpt-rpi-v8").returncode, 1)

    def test_no_modules_dep(self):
        self.assertEqual(self.run_helper(KERNEL).returncode, 1)

    def test_similarly_named_module_is_not_a_match(self):
        self.place("kernel/drivers/media/i2c/cef168x.ko.xz")
        self.place("kernel/drivers/media/i2c/not_cef168.ko.xz")
        self.index("kernel/drivers/media/i2c/cef168x.ko.xz:", "kernel/drivers/media/i2c/not_cef168.ko.xz:")
        self.assertEqual(self.run_helper(KERNEL).returncode, 1)


# --- the installer step against a scratch tree -------------------------------

FAKE_TOOLS = {
    "sudo": r"""#!/bin/bash
while [[ "${1:-}" == -* ]]; do
    case "$1" in
        -u) shift 2 ;;
        --) shift; break ;;
        *) shift ;;
    esac
done
exec "$@"
""",
    "uname": r"""#!/bin/bash
[[ "${1:-}" == "-r" ]] && { echo "$FAKE_KERNEL"; exit 0; }
exec /usr/bin/uname "$@"
""",
    "apt": r"""#!/bin/bash
echo "apt $*" >> "$FAKE_STATE/calls.log"
[[ -n "${FAKE_APT_FAIL:-}" ]] && exit 100
exit 0
""",
    "dpkg": "#!/bin/bash\nexit 1\n",
    "mktemp": r"""#!/bin/bash
exec /usr/bin/mktemp "${TMPDIR:-/tmp}/cef168-test.XXXXXX"
""",
    # Not a compiler: the output is the input, so the step's compare-and-skip is exercised.
    "dtc": r"""#!/bin/bash
out=""; src=""
while (($#)); do
    case "$1" in
        -o) out="$2"; shift 2 ;;
        -*) shift ;;
        *) src="$1"; shift ;;
    esac
done
echo "dtc $src" >> "$FAKE_STATE/calls.log"
cat "$src" > "$out"
""",
    "git": r"""#!/bin/bash
if [[ "$1" == "clone" ]]; then
    dir="${@: -1}"
    mkdir -p "$dir/.git"
    printf '/* fake cef168.c */\n' > "$dir/cef168.c"
    echo "git clone $*" >> "$FAKE_STATE/calls.log"
    exit 0
fi
if [[ "$1" == "-C" ]]; then
    shift 2
    case "$1" in
        rev-parse) [[ "$*" == *--verify* ]] && exit 1; echo "$FAKE_HEAD"; exit 0 ;;
        show-ref) exit 1 ;;
        *) exit 0 ;;
    esac
fi
exit 0
""",
    "dkms": r"""#!/bin/bash
cmd="$1"; shift
echo "dkms $cmd $*" >> "$FAKE_STATE/calls.log"
kernel=""
while (($#)); do
    [[ "$1" == "-k" ]] && kernel="$2"
    shift
done
case "$cmd" in
    status)
        [[ -e "$FAKE_STATE/installed" ]] && echo "cef168/1.0, $kernel, aarch64: installed"
        exit 0 ;;
    add) exit 0 ;;
    build) [[ "${FAKE_DKMS_FAIL:-}" == build ]] && exit 10; exit 0 ;;
    install)
        mkdir -p "$CEF168_MODULES_ROOT/$kernel/updates/dkms"
        : > "$CEF168_MODULES_ROOT/$kernel/updates/dkms/cef168.ko.xz"
        echo "updates/dkms/cef168.ko.xz:" > "$CEF168_MODULES_ROOT/$kernel/modules.dep"
        : > "$FAKE_STATE/installed"
        exit 0 ;;
    remove)
        rm -f "$FAKE_STATE/installed" "$CEF168_MODULES_ROOT/$FAKE_KERNEL/updates/dkms/cef168.ko.xz"
        exit 0 ;;
esac
exit 0
""",
}


class InstallStepTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.bin = self.tmp / "bin"
        self.state = self.tmp / "state"
        self.modules = self.tmp / "modules"
        self.src_root = self.tmp / "usr-src"
        self.overlays = self.tmp / "overlays"
        self.home = self.tmp / "home"
        for d in (self.bin, self.state, self.modules, self.src_root, self.overlays, self.home):
            d.mkdir()
        for name, body in FAKE_TOOLS.items():
            path = self.bin / name
            path.write_text(body, encoding="utf-8")
            path.chmod(0o755)
        (self.modules / KERNEL / "build").mkdir(parents=True)

    def calls(self):
        log = self.state / "calls.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def count(self, prefix):
        return sum(1 for line in self.calls() if line.startswith(prefix))

    def run_step(self, **env_extra):
        env = dict(os.environ)
        env.update(
            PATH=f"{self.bin}:{env['PATH']}",
            PI_USER=subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip(),
            PI_HOME=str(self.home),
            FAKE_STATE=str(self.state),
            FAKE_KERNEL=KERNEL,
            FAKE_HEAD=FAKE_HEAD,
            CEF168_MODULES_ROOT=str(self.modules),
            CEF168_SRC_ROOT=str(self.src_root),
            CEF168_OVERLAYS_DIR=str(self.overlays),
            TMPDIR=str(self.tmp),
        )
        env.update(env_extra)
        script = textwrap.dedent(
            f"""
            source "{INSTALLER}"
            # The installer targets bash 5 (${{1,,}}); macOS ships 3.2. Same
            # truth table, so the step under test runs unmodified on both.
            if (( BASH_VERSINFO[0] < 4 )); then
                is_true() {{ case "$(printf %s "$1" | tr '[:upper:]' '[:lower:]')" in 1|true|yes|on) return 0 ;; *) return 1 ;; esac; }}
            fi
            CINEMATE_SOURCE_DIR="{ROOT}"
            install_cef168_support
            echo "STEP-RETURNED"
            """
        )
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, timeout=120)

    def assert_returned(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("STEP-RETURNED", result.stdout)

    def test_off_by_default_touches_nothing(self):
        result = self.run_step()
        self.assert_returned(result)
        self.assertEqual(self.calls(), [])
        self.assertIn("Skipping Pinefeat CEF168", result.stdout)
        self.assertEqual(list(self.overlays.iterdir()), [])

    def test_fresh_install_builds_stages_and_installs_the_overlay_disabled(self):
        result = self.run_step(INSTALL_CEF168_AF="1")
        self.assert_returned(result)
        for verb in ("add", "build", "install"):
            self.assertEqual(self.count(f"dkms {verb} -m cef168 -v 1.0"), 1, self.calls())
        self.assertIn(f"dkms build -m cef168 -v 1.0 -k {KERNEL}", self.calls())

        stage = self.src_root / "cef168-1.0"
        self.assertEqual({p.name for p in stage.iterdir()}, {"cef168.c", "Kbuild", "dkms.conf", ".cinemate-upstream-commit"})
        self.assertEqual((stage / ".cinemate-upstream-commit").read_text().strip(), FAKE_HEAD)
        self.assertEqual((stage / "Kbuild").read_text(), (OVERLAY_DIR / "Kbuild").read_text())

        self.assertEqual([p.name for p in self.overlays.iterdir()], ["cef168.dtbo"])
        self.assertIn("NOT enabled", result.stdout)
        self.assertIn("dtoverlay=cef168,cam0,imx477", result.stdout)

    def test_pinned_ref_is_what_gets_cloned(self):
        self.run_step(INSTALL_CEF168_AF="1")
        clone = [c for c in self.calls() if c.startswith("git clone")]
        self.assertEqual(len(clone), 1)
        self.assertIn("pinefeat/cef168.git", clone[0])

    def test_second_run_is_a_noop_for_dkms_and_overlay(self):
        self.assert_returned(self.run_step(INSTALL_CEF168_AF="1"))
        before = self.calls()
        result = self.run_step(INSTALL_CEF168_AF="1")
        self.assert_returned(result)
        self.assertIn("already installed by DKMS", result.stdout)
        self.assertIn("already current", result.stdout)
        new = self.calls()[len(before):]
        self.assertEqual([c for c in new if c.startswith(("dkms add", "dkms build", "dkms install", "dkms remove"))], [], new)

    def test_a_moved_pin_rebuilds(self):
        self.assert_returned(self.run_step(INSTALL_CEF168_AF="1"))
        before = len(self.calls())
        other = "e3abfb2" + "1" * 33
        result = self.run_step(INSTALL_CEF168_AF="1", FAKE_HEAD=other)
        self.assert_returned(result)
        new = self.calls()[before:]
        self.assertEqual(sum(1 for c in new if c.startswith("dkms build")), 1, new)
        stamp = self.src_root / "cef168-1.0" / ".cinemate-upstream-commit"
        self.assertEqual(stamp.read_text().strip(), other)

    def test_build_failure_warns_and_does_not_abort(self):
        result = self.run_step(INSTALL_CEF168_AF="1", FAKE_DKMS_FAIL="build")
        self.assert_returned(result)
        self.assertIn("WARN: DKMS build of cef168 failed", result.stderr)
        self.assertEqual(list(self.overlays.iterdir()), [], "overlay must not be installed without the module")

    def test_unpinned_checkout_is_never_built(self):
        result = self.run_step(INSTALL_CEF168_AF="1", FAKE_HEAD="d" * 40)
        self.assert_returned(result)
        self.assertIn("not the pinned", result.stderr)
        self.assertEqual(self.count("dkms build"), 0)

    def test_missing_headers_warn_and_skip(self):
        shutil.rmtree(self.modules / KERNEL / "build")
        result = self.run_step(INSTALL_CEF168_AF="1")
        self.assert_returned(result)
        self.assertIn(f"apt install -y linux-headers-{KERNEL}", self.calls())
        self.assertIn("No kernel headers", result.stderr)
        self.assertEqual(self.count("dkms build"), 0)

    def test_apt_failure_warns_and_does_not_abort(self):
        result = self.run_step(INSTALL_CEF168_AF="1", FAKE_APT_FAIL="1")
        self.assert_returned(result)
        self.assertIn("Could not install dkms", result.stderr)

    def test_pinefeats_own_patch_in_a_sensor_overlay_is_called_out(self):
        (self.overlays / "imx477.dtbo").write_bytes(b"\x00compatible\x00pinefeat,cef168\x00")
        (self.overlays / "imx296.dtbo").write_bytes(b"\x00compatible\x00sony,imx296\x00")
        result = self.run_step(INSTALL_CEF168_AF="1")
        self.assert_returned(result)
        self.assertIn("imx477.dtbo", result.stderr)
        self.assertNotIn("imx296.dtbo", result.stderr)
        self.assertNotIn("/cef168.dtbo (restore", result.stderr)


if __name__ == "__main__":
    unittest.main()
