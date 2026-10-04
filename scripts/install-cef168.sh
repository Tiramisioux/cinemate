#!/usr/bin/env bash
# Run only the Pinefeat CEF168 kernel driver install step on a camera that is
# already installed, without re-running the full cinemate-install.sh (which
# upgrades packages, rebuilds libcamera and cinepi-raw and rewrites the
# managed config.txt block).
#
# It sources the installer as a library, the same way cinemate-update.sh and
# scripts/make-release-image.sh do, and calls install_cef168_support: DKMS
# build of the pinned cef168 driver, overlay compiled and installed but NOT
# enabled in config.txt. Safe to rerun; every step checks before it acts.
#
# SENSOR_MODEL and CAM_PORT only change the config.txt line the step prints at
# the end (imx477 on cam0 by default); nothing here writes config.txt.
#   SENSOR_MODEL=imx585 CAM_PORT=cam1 scripts/install-cef168.sh
# Same pin and overrides as the installer (CEF168_REPO_URL, CEF168_REPO_REF).

set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export INSTALL_CEF168_DRIVER=1

# shellcheck source=/dev/null
source "$repo/cinemate-install.sh"

SENSOR_MODEL="${SENSOR_MODEL,,}"
CAM_PORT="$(normalize_cam_port "$CAM_PORT")"
# Read by install_cef168_support and the helpers it calls (installer scope).
export CINEMATE_SOURCE_DIR="$repo"

bootstrap_sudo
install_cef168_support
