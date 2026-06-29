# Recompiling cinepi-raw

For easy later rebuilding and installation of `cinepi-raw` you can create a reusable `compile-raw.sh` helper. It reuses the existing Meson build directory by default, falls back to `--wipe` only when the build directory is not reusable, and still lets you force a clean setup when you need one.

On boards with less than 4 GB RAM (1 GB / 2 GB models) the script automatically adds a temporary compressed-RAM (zram) swap for the build and removes it afterwards, so `cinepi_raw.cpp` doesn't run the compiler out of memory. It's still faster on a 4 GB+ model.

```shell
cat > /home/pi/compile-raw.sh <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

CINEPI_RAW_DIR="${CINEPI_RAW_DIR:-/home/pi/cinepi-raw}"
CPP_MJPEG_STREAMER_DIR="${CPP_MJPEG_STREAMER_DIR:-/home/pi/cpp-mjpeg-streamer}"
BUILD_JOBS="${BUILD_JOBS:-$(c=$(nproc 2>/dev/null || echo 4); mb=$(awk '/^MemTotal:/{print int($2/1024); exit}' /proc/meminfo 2>/dev/null || echo 0); j=$c; if [ "$mb" -gt 0 ] && [ "$mb" -lt 3000 ]; then j=$(( mb / 1536 )); if [ "$j" -lt 1 ]; then j=1; fi; if [ "$j" -gt "$c" ]; then j=$c; fi; fi; echo "$j")}"
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

# Temporary build swap for 1-2 GB boards: cinepi_raw.cpp needs ~2 GB at -O3 and
# OOM-kills cc1plus. Use compressed RAM (zram) -- no SD/eMMC writes -- removed on
# exit, so the running camera never swaps. Skipped when swap is already active
# or on boards with 4 GB+ RAM (>= 3000 MB).
CR_ZRAM_DEV=""
cr_cleanup_zram() {
    [[ -n "${CR_ZRAM_DEV:-}" ]] || return 0
    sudo swapoff "$CR_ZRAM_DEV" 2>/dev/null || true
    sudo zramctl --reset "$CR_ZRAM_DEV" 2>/dev/null || true
    CR_ZRAM_DEV=""
}
trap cr_cleanup_zram EXIT
cr_mem_mb=$(awk '/^MemTotal:/{print int($2/1024); exit}' /proc/meminfo 2>/dev/null || echo 0)
cr_swap_lines=$(wc -l < /proc/swaps 2>/dev/null || echo 1)
if [[ "$cr_mem_mb" -gt 0 && "$cr_mem_mb" -lt 3000 && "$cr_swap_lines" -le 1 ]]; then
    sudo modprobe zram 2>/dev/null || true
    CR_ZRAM_DEV=$(sudo zramctl --find --size 4G --algorithm zstd 2>/dev/null || sudo zramctl --find --size 4G 2>/dev/null || true)
    if [[ -n "$CR_ZRAM_DEV" ]] && sudo mkswap "$CR_ZRAM_DEV" >/dev/null 2>&1 && sudo swapon -p 100 "$CR_ZRAM_DEV" 2>/dev/null; then
        printf '[compile-raw] Low-RAM board (%s MB): added 4 GB zram build swap on %s (removed on exit)\n' "$cr_mem_mb" "$CR_ZRAM_DEV"
    else
        [[ -n "$CR_ZRAM_DEV" ]] && sudo zramctl --reset "$CR_ZRAM_DEV" 2>/dev/null || true
        CR_ZRAM_DEV=""
        printf '[compile-raw] WARNING: could not set up zram build swap; low-RAM build may OOM\n'
    fi
fi

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
