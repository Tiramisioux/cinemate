# Recompiling cinepi-raw

For easy later rebuilding and installation of `cinepi-raw` you can create a reusable `compile-raw.sh` helper. It reuses the existing Meson build directory by default, falls back to `--wipe` only when the build directory is not reusable, and still lets you force a clean setup when you need one.

```shell
cat > /home/pi/compile-raw.sh <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

CINEPI_RAW_DIR="${CINEPI_RAW_DIR:-/home/pi/cinepi-raw}"
CPP_MJPEG_STREAMER_DIR="${CPP_MJPEG_STREAMER_DIR:-/home/pi/cpp-mjpeg-streamer}"
BUILD_JOBS="${BUILD_JOBS:-$(nproc 2>/dev/null || printf '4')}"
BUILD_DIR="${BUILD_DIR:-$CINEPI_RAW_DIR/build}"
PKG_CONFIG_PATH="$CPP_MJPEG_STREAMER_DIR/build:${PKG_CONFIG_PATH:-}"
export PKG_CONFIG_PATH
FORCE_WIPE="${FORCE_WIPE:-0}"

is_true() {
    case "${1,,}" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
}

build_dir_has_entries() {
    [[ -d "$1" ]] || return 1
    find "$1" -mindepth 1 -maxdepth 1 -print -quit | grep -q .
}

printf '[compile-raw] Source: %s\n' "$CINEPI_RAW_DIR"
printf '[compile-raw] Build directory: %s\n' "$BUILD_DIR"
printf '[compile-raw] Using PKG_CONFIG_PATH=%s\n' "$PKG_CONFIG_PATH"
if is_true "$FORCE_WIPE"; then
    printf '[compile-raw] FORCE_WIPE requested; running meson setup --wipe\n'
    meson setup "$BUILD_DIR" "$CINEPI_RAW_DIR" --wipe
elif [[ -f "$BUILD_DIR/build.ninja" || -f "$BUILD_DIR/meson-private/coredata.dat" ]]; then
    printf '[compile-raw] Reusing existing Meson build directory with --reconfigure\n'
    if ! meson setup "$BUILD_DIR" "$CINEPI_RAW_DIR" --reconfigure; then
        printf '[compile-raw] Reconfigure failed; retrying with --wipe\n'
        meson setup "$BUILD_DIR" "$CINEPI_RAW_DIR" --wipe
    fi
elif build_dir_has_entries "$BUILD_DIR"; then
    printf '[compile-raw] Build directory is non-empty but not reusable; running meson setup --wipe\n'
    meson setup "$BUILD_DIR" "$CINEPI_RAW_DIR" --wipe
else
    printf '[compile-raw] Running initial meson setup\n'
    meson setup "$BUILD_DIR" "$CINEPI_RAW_DIR"
fi
printf '[compile-raw] Building with ninja (%s jobs)\n' "$BUILD_JOBS"
ninja -C "$BUILD_DIR" -j "$BUILD_JOBS"
printf '[compile-raw] Installing cinepi-raw\n'
sudo env PKG_CONFIG_PATH="$PKG_CONFIG_PATH" meson install -C "$BUILD_DIR"
printf '[compile-raw] Refreshing linker cache\n'
sudo ldconfig
EOF
chmod +x /home/pi/compile-raw.sh
```

Now run it:

```shell
/home/pi/compile-raw.sh
```

If you need a fully clean Meson rebuild, run:

```shell
FORCE_WIPE=1 /home/pi/compile-raw.sh
```
