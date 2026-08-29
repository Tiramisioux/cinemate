#!/usr/bin/env bash
# Patch and rebuild rp1-cfe so mono 16-bit (Y16) capture works.
#
# Why: the rpi-6.12.y kernel's CFE format table gives every Bayer 16-bit
# format csi_dt=0 ("Avoid RP1 HW mismatch for 16-bit modes") but the mono
# V4L2_PIX_FMT_Y16 entry was missed and kept csi_dt=MIPI_CSI2_DT_RAW16.
# Unpatched, mono 16-bit buffers arrive as PiSP-COMP1-structured blocks in a
# buffer labeled uncompressed R16 (then further scrambled by libcamera's
# software 16-bit endian swap) — stripes on a flat scene, noise on a varying
# one. Verified root cause + fix, CineMate hardware log 2026-08-27.
#
# What it does: sparse-clones only drivers/media/platform/raspberrypi/rp1_cfe
# from raspberrypi/linux rpi-6.12.y (~3 MB), applies
# scripts/rp1-cfe-y16-csi-dt0.patch, builds the module out-of-tree against the
# running kernel's headers, backs up the stock module (first run only), and
# installs compressed-to-match over the stock path. Reboot afterwards.
#
# Idempotent: always rebuilds from fresh source + patch, so rerunning after a
# kernel package upgrade (which silently reinstalls the stock module) is the
# supported way to reapply. `--revert` restores the first-run backup.
#
# The install is PER KERNEL BUILD: an apt kernel upgrade replaces the module
# silently and a new kernel version uses a different /lib/modules tree.
# Rerun this script after any kernel update if mono 16-bit matters.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_FILE="$SCRIPT_DIR/rp1-cfe-y16-csi-dt0.patch"
SRC_DIR="${RP1_CFE_SRC_DIR:-$HOME/linux-rp1cfe-src}"
BACKUP="$HOME/rp1-cfe.ko.xz.orig-backup"
KVER="$(uname -r)"

log()  { echo "[patch-rp1-cfe] $*"; }
fail() { echo "[patch-rp1-cfe] ERROR: $*" >&2; exit 1; }

installed_module_path() {
    modinfo rp1_cfe 2>/dev/null | awk '/^filename:/{print $2}'
}

if [[ "${1:-}" == "--revert" ]]; then
    [[ -f "$BACKUP" ]] || fail "no backup at $BACKUP -- nothing to revert to"
    target="$(installed_module_path)"
    [[ -n "$target" ]] || fail "cannot resolve the installed rp1-cfe module path"
    sudo cp "$BACKUP" "$target"
    sudo depmod -a
    log "stock module restored to $target -- reboot to load it"
    exit 0
fi

[[ "$(uname -m)" == "aarch64" ]] || fail "requires a 64-bit ARM system"
[[ "$KVER" == 6.12.* ]] || fail "running kernel $KVER is not 6.12.x; the patch targets rpi-6.12.y -- re-verify before using"
[[ -f "$PATCH_FILE" ]] || fail "patch file missing: $PATCH_FILE"
[[ -d "/lib/modules/$KVER/build" ]] || fail \
    "no kernel headers at /lib/modules/$KVER/build -- install the VERSIONED package: sudo apt install linux-headers-$KVER (not the meta-package; the kernel is deliberately apt-pinned)"

target="$(installed_module_path)"
[[ -n "$target" ]] || fail "cannot resolve the installed rp1-cfe module path (is this a Pi 5/CM5?)"

# Fresh source every run: cheap (~3 MB sparse), and guarantees patch state.
rm -rf "$SRC_DIR"
log "sparse-cloning rp1_cfe from raspberrypi/linux rpi-6.12.y"
git clone --quiet --depth 1 --filter=blob:none --sparse --branch rpi-6.12.y \
    https://github.com/raspberrypi/linux.git "$SRC_DIR"
git -C "$SRC_DIR" sparse-checkout set drivers/media/platform/raspberrypi/rp1_cfe

log "applying $PATCH_FILE"
git -C "$SRC_DIR" apply --check "$PATCH_FILE"
git -C "$SRC_DIR" apply "$PATCH_FILE"
grep -q 'csi_dt = 0, /\* Avoid RP1 HW mismatch' \
    "$SRC_DIR/drivers/media/platform/raspberrypi/rp1_cfe/cfe_fmts.h" ||
    fail "patched marker not found in cfe_fmts.h after apply"

log "building rp1-cfe.ko against headers for $KVER"
make -C "/lib/modules/$KVER/build" \
    M="$SRC_DIR/drivers/media/platform/raspberrypi/rp1_cfe" modules
KO="$SRC_DIR/drivers/media/platform/raspberrypi/rp1_cfe/rp1-cfe.ko"
[[ -f "$KO" ]] || fail "build produced no rp1-cfe.ko"

# First run only: the backup must stay the true stock module.
if [[ ! -f "$BACKUP" ]]; then
    sudo cp "$target" "$BACKUP"
    log "stock module backed up to $BACKUP"
fi

# Overwrite the stock path, compressed to match, so no second candidate can
# shadow it (module search prefers whichever depmod indexed).
if [[ "$target" == *.xz ]]; then
    xz -f "$KO"
    sudo cp "$KO.xz" "$target"
else
    sudo cp "$KO" "$target"
fi
sudo depmod -a

log "patched module installed at $target"
log "reboot, then verify: cat /sys/module/rp1_cfe/srcversion  must equal"
log "  modinfo '$target' | awk '/srcversion/{print \$2}'"
