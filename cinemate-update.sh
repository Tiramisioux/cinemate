#!/usr/bin/env bash

set -euo pipefail

# This script updates cinepi-raw and cinemate

# Default directories - override with CINEPI_RAW_DIR or CINEMATE_DIR env vars
CINEPI_RAW_DIR=${CINEPI_RAW_DIR:-$HOME/cinepi-raw}
CINEMATE_DIR=${CINEMATE_DIR:-$(cd "$(dirname "$0")" && pwd)}

# Optional pairing manifest (same file cinemate-install.sh reads): pins each
# repo to a specific ref. Empty/absent reproduces exactly today's behaviour of
# following whatever branch is currently checked out.
_versions_env="$(dirname "$0")/versions.env"
# shellcheck source=/dev/null
[[ -f "$_versions_env" ]] && source "$_versions_env"
CINEMATE_REPO_REF="${CINEMATE_REPO_REF:-}"
CINEPI_RAW_REPO_REF="${CINEPI_RAW_REPO_REF:-}"

# Helper function for updating a git repo
update_repo() {
    local dir="$1"
    local name="$2"
    local ref="${3:-}"
    printf '\n----- Checking %s -----\n' "$name"
    if [ ! -d "$dir/.git" ]; then
        echo "[Error] $name repo not found at $dir"
        return 1
    fi
    cd "$dir"
    local branch
    branch=$(git rev-parse --abbrev-ref HEAD)
    echo "Current branch: $branch"
    echo "Fetching latest changes..."
    git fetch
    if [[ -n "$ref" && "$branch" != "$ref" ]]; then
        echo "versions.env pins $name to $ref; checking out..."
        git checkout "$ref"
    fi
    local local_rev remote_rev
    local_rev=$(git rev-parse @)
    if [[ -n "$ref" ]]; then
        if git show-ref --verify --quiet "refs/remotes/origin/$ref"; then
            remote_rev=$(git rev-parse "origin/$ref")
        else
            # Tag or fixed commit: nothing to fast-forward to.
            remote_rev=$(git rev-parse "$ref")
        fi
    else
        # shellcheck disable=SC1083  # @{u} is git syntax for the upstream ref,
        # not brace expansion.
        remote_rev=$(git rev-parse "@{u}")
    fi
    if [[ "$local_rev" == "$remote_rev" ]]; then
        echo "$name is up to date."
        REPO_UPDATED=0
    else
        echo "Updates available for $name. Pulling..."
        if [[ -n "$ref" ]]; then
            git pull --ff-only origin "$ref"
        else
            git pull --ff-only
        fi
        REPO_UPDATED=1
    fi
}

# Update cinepi-raw
update_repo "$CINEPI_RAW_DIR" "cinepi-raw" "$CINEPI_RAW_REPO_REF"
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
update_repo "$CINEMATE_DIR" "cinemate" "$CINEMATE_REPO_REF"
if [ "$REPO_UPDATED" -eq 1 ]; then
    echo "Reinstalling Cinemate..."
    cd "$CINEMATE_DIR"
    make install
else
    echo "Cinemate already at latest version."
fi

printf '\nAll done.\n'
