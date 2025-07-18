#!/usr/bin/env bash

set -euo pipefail

# This script updates cinepi-raw and cinemate

# Default directories - override with CINEPI_RAW_DIR or CINEMATE_DIR env vars
CINEPI_RAW_DIR=${CINEPI_RAW_DIR:-$HOME/cinepi-raw}
CINEMATE_DIR=${CINEMATE_DIR:-$(cd "$(dirname "$0")" && pwd)}

# Helper function for updating a git repo
update_repo() {
    local dir="$1"
    local name="$2"
    echo "\n----- Checking $name -----"
    if [ ! -d "$dir/.git" ]; then
        echo "[Error] $name repo not found at $dir"
        return 1
    fi
    cd "$dir"
    local branch=$(git rev-parse --abbrev-ref HEAD)
    echo "Current branch: $branch"
    echo "Fetching latest changes..."
    git fetch
    local local_rev=$(git rev-parse @)
    local remote_rev=$(git rev-parse @{u})
    if [[ "$local_rev" == "$remote_rev" ]]; then
        echo "$name is up to date."
        REPO_UPDATED=0
    else
        echo "Updates available for $name. Pulling..."
        git pull --ff-only
        REPO_UPDATED=1
    fi
}

# Update cinepi-raw
update_repo "$CINEPI_RAW_DIR" "cinepi-raw"
if [ "$REPO_UPDATED" -eq 1 ]; then
    echo "Rebuilding cinepi-raw..."
    cd "$CINEPI_RAW_DIR"
    if [ -d build ]; then
        echo "Removing previous build directory..."
        sudo rm -rf build
    fi
    echo "Setting PKG_CONFIG_PATH for cpp-mjpeg-streamer..."
    export PKG_CONFIG_PATH=/home/pi/cpp-mjpeg-streamer/build:$PKG_CONFIG_PATH
    echo "Running meson setup..."
    sudo meson setup build
    echo "Compiling with ninja..."
    sudo ninja -C build
    echo "Installing cinepi-raw..."
    sudo meson install -C build
else
    echo "cinepi-raw already at latest version. Skipping rebuild."
fi

# Update cinemate
update_repo "$CINEMATE_DIR" "cinemate"
if [ "$REPO_UPDATED" -eq 1 ]; then
    echo "Reinstalling Cinemate..."
    cd "$CINEMATE_DIR"
    make install
else
    echo "Cinemate already at latest version."
fi

echo "\nAll done."
