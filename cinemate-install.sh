#!/usr/bin/env bash

set -Eeuo pipefail
trap 'printf "[cinemate-install] ERROR: line %s while running: %s\n" "$LINENO" "$BASH_COMMAND" >&2' ERR

# Edit these defaults once, or override them inline:
# Default hardware profile: IMX477 on cam0 and HDMI-A-1.
#   SENSOR_MODEL=imx296 CAM_PORT=cam0 ./cinemate-install.sh
#   SENSOR_MODEL=imx283 CAM_PORT=cam0 ./cinemate-install.sh
#   SENSOR_MODEL=imx585 CAM_PORT=cam0 ./cinemate-install.sh
#   SENSOR_MODEL=imx585_mono CAM_PORT=cam1 ./cinemate-install.sh

PI_USER="${PI_USER:-pi}"
PI_GROUP="${PI_GROUP:-$PI_USER}"
PI_HOME="${PI_HOME:-/home/$PI_USER}"

TARGET_HOSTNAME="${TARGET_HOSTNAME:-cinepi}"

SENSOR_MODEL="${SENSOR_MODEL:-imx477}"      # imx477 | imx296 | imx283 | imx585 | imx585_mono
CAM_PORT="${CAM_PORT:-cam0}"               # cam0 | cam1 | 0 | 1
HDMI_BOOT_PORT="${HDMI_BOOT_PORT:-0}"      # 0 => HDMI-A-1, 1 => HDMI-A-2
HDMI_MODE="${HDMI_MODE:-1920x1080M@60D}"
HDMI_PORT_CAM0="${HDMI_PORT_CAM0:-0}"
HDMI_PORT_CAM1="${HDMI_PORT_CAM1:-1}"

HOTSPOT_NAME="${HOTSPOT_NAME:-CinePi}"
HOTSPOT_PASSWORD="${HOTSPOT_PASSWORD:-11111111}"
HOTSPOT_ENABLED="${HOTSPOT_ENABLED:-1}"

AUDIO_CARD_24="${AUDIO_CARD_24:-NTG}"
AUDIO_CARD_16="${AUDIO_CARD_16:-Device}"

ENABLE_CFE_HAT_PCIE="${ENABLE_CFE_HAT_PCIE:-1}"
BT_OVERLAY="${BT_OVERLAY:-disable-bt}"     # disable-bt | miniuart-bt

INSTALL_ALT_GPIO_BACKEND="${INSTALL_ALT_GPIO_BACKEND:-1}"
INSTALL_CONSOLE_FONT="${INSTALL_CONSOLE_FONT:-1}"
INSTALL_PISHRINK="${INSTALL_PISHRINK:-1}"
INSTALL_PLYMOUTH="${INSTALL_PLYMOUTH:-1}"
INSTALL_IMX283_DRIVER="${INSTALL_IMX283_DRIVER:-1}"
INSTALL_IMX585_DRIVER="${INSTALL_IMX585_DRIVER:-1}"
INSTALL_IR_FILTER_HELPER="${INSTALL_IR_FILTER_HELPER:-auto}"
ENABLE_CONSOLE_AUTOLOGIN="${ENABLE_CONSOLE_AUTOLOGIN:-1}"

ENABLE_SUPPORT_SERVICES="${ENABLE_SUPPORT_SERVICES:-1}"
ENABLE_STORAGE_AUTOMOUNT_SERVICE="${ENABLE_STORAGE_AUTOMOUNT_SERVICE:-1}"
ENABLE_WIFI_HOTSPOT_SERVICE="${ENABLE_WIFI_HOTSPOT_SERVICE:-1}"
ENABLE_REDIS_LOG_MAINTENANCE_SERVICE="${ENABLE_REDIS_LOG_MAINTENANCE_SERVICE:-1}"
ENABLE_AUTOSTART="${ENABLE_AUTOSTART:-1}"
START_AUTOSTART_NOW="${START_AUTOSTART_NOW:-0}"
RUN_REBOOT="${RUN_REBOOT:-0}"
UPDATE_EXISTING_REPOS="${UPDATE_EXISTING_REPOS:-1}"
SUPPORTED_OS_CODENAME="${SUPPORTED_OS_CODENAME:-bookworm}"
ALLOW_UNSUPPORTED_OS="${ALLOW_UNSUPPORTED_OS:-0}"

CINEMATE_DIR="${CINEMATE_DIR:-$PI_HOME/cinemate}"
CINEPI_RAW_DIR="${CINEPI_RAW_DIR:-$PI_HOME/cinepi-raw}"
LIBCAMERA_DIR="${LIBCAMERA_DIR:-$PI_HOME/libcamera}"
CPP_MJPEG_STREAMER_DIR="${CPP_MJPEG_STREAMER_DIR:-$PI_HOME/cpp-mjpeg-streamer}"
REDIS_PLUS_PLUS_DIR="${REDIS_PLUS_PLUS_DIR:-$PI_HOME/redis-plus-plus}"
LGPIO_DIR="${LGPIO_DIR:-$PI_HOME/lg}"
IMX283_DRIVER_DIR="${IMX283_DRIVER_DIR:-$PI_HOME/imx283-v4l2-driver}"
IMX585_DRIVER_DIR="${IMX585_DRIVER_DIR:-$PI_HOME/imx585-v4l2-driver}"
VENV_DIR="${VENV_DIR:-$PI_HOME/.cinemate-env}"

CINEMATE_REPO_URL="${CINEMATE_REPO_URL:-https://github.com/Tiramisioux/cinemate.git}"
CINEMATE_REPO_REF="${CINEMATE_REPO_REF:-}"
CINEPI_RAW_REPO_URL="${CINEPI_RAW_REPO_URL:-https://github.com/Tiramisioux/cinepi-raw.git}"
CINEPI_RAW_REPO_REF="${CINEPI_RAW_REPO_REF:-}"
LIBCAMERA_REPO_URL="${LIBCAMERA_REPO_URL:-https://github.com/Tiramisioux/libcamera.git}"
LIBCAMERA_REPO_REF="${LIBCAMERA_REPO_REF:-cinemate}"
# Patches cherry-picked on top of LIBCAMERA_REPO_REF (space-separated commit hashes, applied in order)
# Default: none — build as-is. Tracks the Tiramisioux/libcamera `cinemate`
# branch tip: Will Whang's IMX585 fork (9d0cdfe5), mirrored here so the build
# does not depend on the upstream commit staying available, plus gcc-12 build
# fixes (Pi 4 / Bookworm -Werror=restrict in the apps; verified 251/251 on Pi 4).
# Set REF to a commit SHA instead (e.g. ff24737b6) for a pinned, reproducible build.
LIBCAMERA_PATCHES="${LIBCAMERA_PATCHES:-}"
CPP_MJPEG_STREAMER_REPO_URL="${CPP_MJPEG_STREAMER_REPO_URL:-https://github.com/nadjieb/cpp-mjpeg-streamer.git}"
CPP_MJPEG_STREAMER_REPO_REF="${CPP_MJPEG_STREAMER_REPO_REF:-}"
REDIS_PLUS_PLUS_REPO_URL="${REDIS_PLUS_PLUS_REPO_URL:-https://github.com/sewenew/redis-plus-plus.git}"
REDIS_PLUS_PLUS_REPO_REF="${REDIS_PLUS_PLUS_REPO_REF:-}"
LGPIO_REPO_URL="${LGPIO_REPO_URL:-https://github.com/joan2937/lg.git}"
LGPIO_REPO_REF="${LGPIO_REPO_REF:-}"
IMX283_DRIVER_REPO_URL="${IMX283_DRIVER_REPO_URL:-https://github.com/will127534/imx283-v4l2-driver.git}"
IMX283_DRIVER_REPO_REF="${IMX283_DRIVER_REPO_REF:-6.12.y}"
IMX585_DRIVER_REPO_URL="${IMX585_DRIVER_REPO_URL:-https://github.com/will127534/imx585-v4l2-driver.git}"
IMX585_DRIVER_REPO_REF="${IMX585_DRIVER_REPO_REF:-6.12.y}"
IR_FILTER_URL="${IR_FILTER_URL:-https://raw.githubusercontent.com/will127534/StarlightEye/master/software/IRFilter}"
PISHRINK_URL="${PISHRINK_URL:-https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh}"
KERNEL_BASELINE_ABI_2712="${KERNEL_BASELINE_ABI_2712:-6.12.25+rpt-rpi-2712}"
KERNEL_BASELINE_DEB_VERSION_2712="${KERNEL_BASELINE_DEB_VERSION_2712:-6.12.25-1+rpt1}"
KERNEL_BASELINE_SUPPORT_PKG_2712="${KERNEL_BASELINE_SUPPORT_PKG_2712:-linux-support-6.12.25+rpt}"
KERNEL_BASELINE_IMAGE_REAL_PKG_2712="${KERNEL_BASELINE_IMAGE_REAL_PKG_2712:-linux-image-6.12.25+rpt-rpi-2712}"
KERNEL_BASELINE_IMAGE_META_PKG_2712="${KERNEL_BASELINE_IMAGE_META_PKG_2712:-linux-image-rpi-2712}"
KERNEL_BASELINE_HEADERS_REAL_PKG_2712="${KERNEL_BASELINE_HEADERS_REAL_PKG_2712:-linux-headers-6.12.25+rpt-rpi-2712}"
KERNEL_BASELINE_HEADERS_META_PKG_2712="${KERNEL_BASELINE_HEADERS_META_PKG_2712:-linux-headers-rpi-2712}"
RASPI_FIRMWARE_VERSION_2712="${RASPI_FIRMWARE_VERSION_2712:-1.20250430-1}"
KERNEL_ROLLBACK_DIR="${KERNEL_ROLLBACK_DIR:-/var/tmp/cinemate-kernel-baseline}"

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly MANAGED_BEGIN="# >>> cinemate-install >>>"
readonly MANAGED_END="# <<< cinemate-install <<<"
# Parallel build jobs. On boards with < 4 GB RAM (1 GB / 2 GB models) heavy
# translation units (cinepi_raw.cpp, the IPAs) can use >1.5 GB each at -O3 and
# OOM-kill cc1plus ("Killed signal terminated program cc1plus"), so cap to ~1 job
# per 1.5 GB (i.e. -j1 on 2 GB) — these boards also get a build-time zram swap
# (see ensure_build_zram). Boards with >= 4 GB RAM use all CPUs. Override: BUILD_JOBS=N.
readonly BUILD_JOBS="${BUILD_JOBS:-$(c=$(nproc 2>/dev/null || echo 4); mb=$(awk '/^MemTotal:/{print int($2/1024); exit}' /proc/meminfo 2>/dev/null || echo 0); j=$c; if [ "$mb" -gt 0 ] && [ "$mb" -lt 3000 ]; then j=$(( mb / 1536 )); if [ "$j" -lt 1 ]; then j=1; fi; if [ "$j" -gt "$c" ]; then j=$c; fi; fi; echo "$j")}"

BACKUP_DIR=""
CINEMATE_SOURCE_DIR=""
STEP_COUNTER=0
KERNEL_ALIGNMENT_REQUIRED_REBOOT=0

log() {
    printf '[cinemate-install] %s\n' "$*"
}

section() {
    STEP_COUNTER=$((STEP_COUNTER + 1))
    printf '\n[cinemate-install] [%02d] %s\n' "$STEP_COUNTER" "$*"
}

detail() {
    printf '[cinemate-install]      %s\n' "$*"
}

warn() {
    printf '[cinemate-install] WARN: %s\n' "$*" >&2
}

die() {
    printf '[cinemate-install] ERROR: %s\n' "$*" >&2
    exit 1
}

is_true() {
    case "${1,,}" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
}

normalize_cam_port() {
    case "${1,,}" in
        0|cam0) printf 'cam0' ;;
        1|cam1) printf 'cam1' ;;
        *) die "Unsupported CAM_PORT: $1" ;;
    esac
}

normalize_hdmi_port() {
    case "${1,,}" in
        0|hdmi-a-1|hdmi0) printf '0' ;;
        1|hdmi-a-2|hdmi1) printf '1' ;;
        *) die "Unsupported HDMI port value: $1" ;;
    esac
}

run_as_pi() {
    if [[ "$(id -un)" == "$PI_USER" ]]; then
        "$@"
    else
        detail "Running as $PI_USER: $*"
        sudo -u "$PI_USER" -- "$@"
    fi
}

run_as_pi_clean_shell() {
    local script="$1"
    local path_env="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

    if [[ "$(id -un)" == "$PI_USER" ]]; then
        env -i \
            HOME="$PI_HOME" \
            USER="$PI_USER" \
            LOGNAME="$PI_USER" \
            PATH="$path_env" \
            bash --noprofile --norc -ec "$script"
    else
        detail "Running clean shell as $PI_USER: $script"
        sudo -H -u "$PI_USER" env -i \
            HOME="$PI_HOME" \
            USER="$PI_USER" \
            LOGNAME="$PI_USER" \
            PATH="$path_env" \
            bash --noprofile --norc -ec "$script"
    fi
}

bootstrap_sudo() {
    detail "Validating sudo access"
    command -v sudo >/dev/null 2>&1 || die "sudo is required"
    sudo -v
}

validate_supported_os() {
    local os_release=/etc/os-release
    local pretty_name="unknown"
    local version_codename="unknown"

    [[ -r "$os_release" ]] || die "Could not read $os_release to verify the supported OS"
    # shellcheck disable=SC1090
    source "$os_release"
    pretty_name="${PRETTY_NAME:-$pretty_name}"
    version_codename="${VERSION_CODENAME:-$version_codename}"

    detail "Detected OS: $pretty_name"
    if [[ "$version_codename" != "$SUPPORTED_OS_CODENAME" ]] && ! is_true "$ALLOW_UNSUPPORTED_OS"; then
        die "Unsupported OS codename '$version_codename'. Cinemate currently targets Raspberry Pi OS Lite (Bookworm). Reimage to Bookworm before running this installer, or set ALLOW_UNSUPPORTED_OS=1 only if you are intentionally testing an unsupported release."
    fi

    if [[ "$version_codename" != "$SUPPORTED_OS_CODENAME" ]]; then
        warn "Continuing on unsupported OS codename '$version_codename' because ALLOW_UNSUPPORTED_OS=1 was set"
    fi
}

current_tty() {
    tty 2>/dev/null || true
}

write_root_file() {
    local path="$1"
    local mode="$2"
    local temp
    temp="$(mktemp)"
    cat >"$temp"
    if sudo test -f "$path" && sudo cmp -s "$temp" "$path" && [[ "$(sudo stat -c '%a' "$path")" == "$mode" ]]; then
        detail "No change needed for $path"
        rm -f "$temp"
        return 0
    fi
    detail "Writing $path"
    sudo install -m "$mode" "$temp" "$path"
    rm -f "$temp"
}

write_user_file() {
    local path="$1"
    local mode="$2"
    local temp
    temp="$(mktemp)"
    cat >"$temp"
    if [[ -f "$path" ]] && cmp -s "$temp" "$path" && [[ "$(stat -c '%U:%G %a' "$path")" == "$PI_USER:$PI_GROUP $mode" ]]; then
        detail "No change needed for $path"
        rm -f "$temp"
        return 0
    fi
    detail "Writing $path"
    sudo install -o "$PI_USER" -g "$PI_GROUP" -m "$mode" "$temp" "$path"
    rm -f "$temp"
}

backup_file() {
    local path="$1"
    local relative
    local target

    [[ -e "$path" ]] || return 0
    relative="${path#/}"
    target="$BACKUP_DIR/$relative"
    sudo mkdir -p "$(dirname "$target")"
    detail "Backing up $path -> $target"
    sudo cp -a "$path" "$target"
}

ensure_line_in_root_file() {
    local path="$1"
    local line="$2"
    local mode="${3:-644}"
    local temp
    local existing=""

    if sudo test -f "$path"; then
        existing="$(sudo cat "$path")"
    fi

    if printf '%s\n' "$existing" | grep -Fqx "$line"; then
        detail "$path already contains: $line"
        return 0
    fi

    backup_file "$path"
    temp="$(mktemp)"
    if [[ -n "$existing" ]]; then
        printf '%s\n' "$existing" >"$temp"
    fi
    printf '%s\n' "$line" >>"$temp"
    detail "Adding '$line' to $path"
    sudo install -m "$mode" "$temp" "$path"
    rm -f "$temp"
}

print_configuration_summary() {
    log "Install profile summary:"
    detail "User: $PI_USER ($PI_HOME)"
    detail "Sensor: $SENSOR_MODEL on $CAM_PORT"
    case "$SENSOR_MODEL" in
        imx296)
            detail "One-click profile: Raspberry Pi GS camera; no extra DKMS sensor driver required"
            ;;
        imx283)
            detail "One-click profile: OneInchEye; Cinemate installs the IMX283 DKMS driver and tuning override automatically"
            ;;
    esac
    if [[ "$SENSOR_MODEL" == "imx296" || "$SENSOR_MODEL" == "imx477" ]]; then
        detail "Pi 4 raw mode: Cinemate will use packed cinepi-raw modes for this sensor; Pi 5 stays unpacked"
    fi
    detail "Boot HDMI: HDMI-A-$((HDMI_BOOT_PORT + 1)) at $HDMI_MODE"
    detail "Runtime HDMI ports: cam0->$HDMI_PORT_CAM0 cam1->$HDMI_PORT_CAM1"
    detail "Libcamera: $LIBCAMERA_REPO_URL @ $LIBCAMERA_REPO_REF"
    detail "Hotspot: $HOTSPOT_NAME (enabled=$HOTSPOT_ENABLED)"
    detail "Optional features: lgpio=$INSTALL_ALT_GPIO_BACKEND console_font=$INSTALL_CONSOLE_FONT console_autologin=$ENABLE_CONSOLE_AUTOLOGIN pishrink=$INSTALL_PISHRINK plymouth=$INSTALL_PLYMOUTH imx283_driver=$INSTALL_IMX283_DRIVER imx585_driver=$INSTALL_IMX585_DRIVER ir_filter=$INSTALL_IR_FILTER_HELPER"
    detail "Services: support=$ENABLE_SUPPORT_SERVICES storage=$ENABLE_STORAGE_AUTOMOUNT_SERVICE wifi=$ENABLE_WIFI_HOTSPOT_SERVICE redis_log=$ENABLE_REDIS_LOG_MAINTENANCE_SERVICE autostart=$ENABLE_AUTOSTART start_now=$START_AUTOSTART_NOW"
}

is_commitish_ref() {
    [[ "$1" =~ ^[0-9a-fA-F]{7,40}$ ]]
}

ensure_repo() {
    local dir="$1"
    local url="$2"
    local ref="${3:-}"
    local ref_kind="branch"

    if [[ -d "$dir/.git" ]]; then
        log "Using existing repo: $dir"
        if is_true "$UPDATE_EXISTING_REPOS"; then
            detail "Fetching latest refs for $dir"
            run_as_pi git -C "$dir" fetch --tags --prune
            if [[ -n "$ref" ]]; then
                if run_as_pi git -C "$dir" rev-parse -q --verify "refs/tags/$ref^{tag}" >/dev/null 2>&1 || \
                   run_as_pi git -C "$dir" rev-parse -q --verify "refs/tags/$ref^{}" >/dev/null 2>&1; then
                    ref_kind="tag"
                elif run_as_pi git -C "$dir" show-ref --verify --quiet "refs/remotes/origin/$ref"; then
                    ref_kind="branch"
                else
                    ref_kind="commitish"
                fi
                detail "Checking out $ref in $dir"
                run_as_pi git -C "$dir" checkout "$ref"
                if [[ "$ref_kind" == "branch" ]]; then
                    run_as_pi git -C "$dir" pull --ff-only origin "$ref"
                else
                    detail "Pinned $dir to $ref ($ref_kind); skipping pull"
                fi
            else
                detail "Fast-forwarding current branch in $dir when possible"
                run_as_pi git -C "$dir" pull --ff-only || warn "Could not fast-forward $dir; leaving current checkout as-is"
            fi
        else
            detail "Leaving existing checkout untouched: $dir"
        fi
        return 0
    fi

    run_as_pi mkdir -p "$(dirname "$dir")"
    detail "Cloning $url into $dir"
    if [[ -n "$ref" ]]; then
        if is_commitish_ref "$ref"; then
            run_as_pi git clone "$url" "$dir"
            detail "Checking out $ref in $dir"
            run_as_pi git -C "$dir" checkout "$ref"
        else
            run_as_pi git clone --branch "$ref" "$url" "$dir"
        fi
    else
        run_as_pi git clone "$url" "$dir"
    fi
}

configure_repo_source() {
    CINEMATE_SOURCE_DIR="$SCRIPT_DIR"

    if [[ ! -f "$CINEMATE_SOURCE_DIR/src/main.py" ]]; then
        ensure_repo "$CINEMATE_DIR" "$CINEMATE_REPO_URL" "$CINEMATE_REPO_REF"
        CINEMATE_SOURCE_DIR="$CINEMATE_DIR"
    fi

    [[ -f "$CINEMATE_SOURCE_DIR/src/main.py" ]] || die "Could not find Cinemate source tree"

    if [[ "$CINEMATE_SOURCE_DIR" != "$CINEMATE_DIR" ]]; then
        if [[ -L "$CINEMATE_DIR" || ! -e "$CINEMATE_DIR" ]]; then
            log "Pointing $CINEMATE_DIR at $CINEMATE_SOURCE_DIR"
            sudo rm -f "$CINEMATE_DIR"
            sudo ln -s "$CINEMATE_SOURCE_DIR" "$CINEMATE_DIR"
        else
            warn "$CINEMATE_DIR already exists and is not a symlink; service files will keep using that runtime path"
            CINEMATE_SOURCE_DIR="$CINEMATE_DIR"
        fi
    fi
}

bootstrap_base_tools() {
    log "Updating apt metadata"
    sudo apt update -y
    sudo apt upgrade -y
    detail "Installing base shell/bootstrap tools"
    sudo apt install -y git curl wget python3 python3-pip python3-venv rsync
}

is_rpi2712_platform() {
    grep -aq "bcm2712" /proc/device-tree/compatible 2>/dev/null
}

align_pi5_kernel_baseline() {
    if ! is_rpi2712_platform; then
        detail "Skipping Pi 5 kernel alignment on non-2712 hardware"
        return 0
    fi

    log "Aligning Raspberry Pi 5 kernel baseline"
    detail "Target kernel: $KERNEL_BASELINE_ABI_2712 with raspi-firmware $RASPI_FIRMWARE_VERSION_2712"

    local current_image_version
    local current_fw_version
    current_image_version="$(dpkg-query -W -f='${Version}' "$KERNEL_BASELINE_IMAGE_META_PKG_2712" 2>/dev/null || true)"
    current_fw_version="$(dpkg-query -W -f='${Version}' raspi-firmware 2>/dev/null || true)"

    local kernel_pool_url="https://archive.raspberrypi.com/debian/pool/main/l/linux"
    local firmware_pool_url="https://archive.raspberrypi.com/debian/pool/untested/r/raspi-firmware"
    local -a urls=(
        "$kernel_pool_url/${KERNEL_BASELINE_SUPPORT_PKG_2712}_${KERNEL_BASELINE_DEB_VERSION_2712}_all.deb"
        "$kernel_pool_url/${KERNEL_BASELINE_IMAGE_REAL_PKG_2712}_${KERNEL_BASELINE_DEB_VERSION_2712}_arm64.deb"
        "$kernel_pool_url/${KERNEL_BASELINE_IMAGE_META_PKG_2712}_${KERNEL_BASELINE_DEB_VERSION_2712}_arm64.deb"
        "$kernel_pool_url/${KERNEL_BASELINE_HEADERS_REAL_PKG_2712}_${KERNEL_BASELINE_DEB_VERSION_2712}_arm64.deb"
        "$kernel_pool_url/${KERNEL_BASELINE_HEADERS_META_PKG_2712}_${KERNEL_BASELINE_DEB_VERSION_2712}_arm64.deb"
        "$firmware_pool_url/raspi-firmware_${RASPI_FIRMWARE_VERSION_2712}_all.deb"
    )
    local -a debs=()
    local url=""
    local file=""

    sudo install -d -m 755 "$KERNEL_ROLLBACK_DIR"

    for url in "${urls[@]}"; do
        file="$KERNEL_ROLLBACK_DIR/${url##*/}"
        debs+=("$file")
        if [[ -f "$file" ]]; then
            detail "Reusing cached $(basename "$file")"
            continue
        fi
        detail "Downloading $(basename "$file")"
        sudo curl -fsSL "$url" -o "$file"
        sudo chmod 644 "$file"
    done

    if [[ "$current_image_version" != "1:$KERNEL_BASELINE_DEB_VERSION_2712" || "$current_fw_version" != "1:$RASPI_FIRMWARE_VERSION_2712" ]]; then
        detail "Installing pinned Pi 5 kernel packages from the Raspberry Pi archive"
        sudo apt install -y --allow-downgrades "${debs[@]}"
    else
        detail "Pinned Pi 5 kernel packages already installed"
    fi

    detail "Refreshing initramfs and copying Pi 5 boot files into /boot/firmware"
    refresh_pi5_boot_handoff

    detail "Holding Pi 5 baseline kernel packages so apt upgrade does not move them forward"
    sudo apt-mark hold \
        raspi-firmware \
        "$KERNEL_BASELINE_SUPPORT_PKG_2712" \
        "$KERNEL_BASELINE_IMAGE_REAL_PKG_2712" \
        "$KERNEL_BASELINE_IMAGE_META_PKG_2712" \
        "$KERNEL_BASELINE_HEADERS_REAL_PKG_2712" \
        "$KERNEL_BASELINE_HEADERS_META_PKG_2712" >/dev/null

    KERNEL_ALIGNMENT_REQUIRED_REBOOT=1
}

refresh_pi5_boot_handoff() {
    if ! is_rpi2712_platform; then
        return 0
    fi

    sudo update-initramfs -u -k "$KERNEL_BASELINE_ABI_2712"
    sudo cp "/boot/vmlinuz-$KERNEL_BASELINE_ABI_2712" /boot/firmware/kernel_2712.img
    sudo cp "/boot/initrd.img-$KERNEL_BASELINE_ABI_2712" /boot/firmware/initramfs_2712
    sync
}

install_apt_packages() {
    local -a camera_stack_packages
    local -a libcamera_packages
    local -a cpp_mjpeg_streamer_packages
    local -a cinemate_packages
    local -a optional_packages=()

    camera_stack_packages=(
        python3-jinja2 python3-ply python3-yaml ffmpeg
        cmake build-essential meson ninja-build
        libboost-dev libboost-program-options-dev libdrm-dev libepoxy-dev libexif-dev
        libcamera-dev libjpeg-dev libtiff5-dev libpng-dev libhiredis-dev libasound2-dev
        libjsoncpp-dev libavcodec-dev libavdevice-dev libavformat-dev libswresample-dev
        redis-server
    )

    libcamera_packages=(
        libgnutls28-dev openssl pybind11-dev qtbase5-dev libqt5core5a
        libglib2.0-dev libgstreamer-plugins-base1.0-dev libgstreamer1.0-dev libavdevice59
        libyaml-dev
    )

    cpp_mjpeg_streamer_packages=(
        libspdlog-dev libjsoncpp-dev
    )

    cinemate_packages=(
        build-essential python3-dev python3-pip python3-venv
        i2c-tools python3-smbus python3-pyudev
        libgpiod-dev libgpiod2 python3-libgpiod gpiod
        portaudio19-dev python3-systemd
        e2fsprogs ntfs-3g exfatprogs
        console-terminus swig
    )

    if should_install_imx283_driver || should_install_imx585_driver; then
        optional_packages+=(dkms)
    fi
    if is_true "$INSTALL_CONSOLE_FONT"; then
        optional_packages+=(console-setup kbd)
    fi
    if is_true "$INSTALL_PLYMOUTH"; then
        optional_packages+=(plymouth plymouth-themes plymouth-label)
    fi

    log "Installing apt dependencies to match the manual guide"

    detail "Manual step: shared camera stack dependencies"
    sudo apt install -y "${camera_stack_packages[@]}"

    detail "Manual step: libcamera build dependencies"
    sudo apt install -y "${libcamera_packages[@]}"

    detail "Manual step: cpp-mjpeg-streamer dependencies"
    sudo apt install -y "${cpp_mjpeg_streamer_packages[@]}"

    detail "Manual step: Cinemate system packages"
    sudo apt install -y "${cinemate_packages[@]}"

    if ((${#optional_packages[@]} > 0)); then
        detail "Optional manual-step packages"
        sudo apt install -y "${optional_packages[@]}"
    else
        detail "No optional apt packages requested"
    fi
}

should_install_imx585_driver() {
    if [[ "${INSTALL_IMX585_DRIVER,,}" == "auto" ]]; then
        [[ "$SENSOR_MODEL" == "imx585" || "$SENSOR_MODEL" == "imx585_mono" ]]
        return
    fi
    is_true "$INSTALL_IMX585_DRIVER"
}

should_install_imx283_driver() {
    if [[ "${INSTALL_IMX283_DRIVER,,}" == "auto" ]]; then
        [[ "$SENSOR_MODEL" == "imx283" ]]
        return
    fi
    is_true "$INSTALL_IMX283_DRIVER"
}

should_install_ir_filter_helper() {
    if [[ "${INSTALL_IR_FILTER_HELPER,,}" == "auto" ]]; then
        [[ "$SENSOR_MODEL" == "imx585" ]]
        return
    fi
    is_true "$INSTALL_IR_FILTER_HELPER"
}

prepare_libtiff_link() {
    log "Refreshing libtiff development link"
    sudo apt-get install --reinstall -y libtiff5-dev
    local libtiff_path
    libtiff_path="$(find /usr/lib -name 'libtiff.so' | head -n 1 || true)"
    [[ -n "$libtiff_path" ]] || die "Could not locate libtiff.so"
    detail "Linking /usr/lib/aarch64-linux-gnu/libtiff.so.5 -> $libtiff_path"
    sudo ln -sfn "$libtiff_path" /usr/lib/aarch64-linux-gnu/libtiff.so.5
    sudo ldconfig
}

build_redis_plus_plus() {
    ensure_repo "$REDIS_PLUS_PLUS_DIR" "$REDIS_PLUS_PLUS_REPO_URL" "$REDIS_PLUS_PLUS_REPO_REF"

    log "Building redis-plus-plus"
    detail "Source: $REDIS_PLUS_PLUS_DIR"
    run_as_pi_clean_shell "cd '$REDIS_PLUS_PLUS_DIR' && cmake -S . -B build && cmake --build build -j '$BUILD_JOBS'"
    sudo cmake --build "$REDIS_PLUS_PLUS_DIR/build" --target install
    sudo ldconfig
}

# --- build-time zram swap (low-RAM boards only) -----------------------------
# Heavy translation units (cinepi_raw.cpp at -O3 needs ~2 GB) OOM-kill cc1plus
# and can freeze a 2 GB board. On boards with < 4 GB RAM we add a *compressed
# RAM* swap device (zram) for the build only — no writes to the SD/eMMC — and
# remove it afterwards, so the running camera never swaps (swapping during a
# recording would drop frames). ENABLE_BUILD_ZRAM: auto (default; < 4 GB only),
# or 1/0 to force on/off.
ENABLE_BUILD_ZRAM="${ENABLE_BUILD_ZRAM:-auto}"
BUILD_ZRAM_DEV=""

ensure_build_zram() {
    if [[ -n "${BUILD_ZRAM_DEV:-}" ]]; then return 0; fi
    local mb dev
    mb="$(awk '/^MemTotal:/{print int($2/1024); exit}' /proc/meminfo 2>/dev/null || echo 0)"
    case "${ENABLE_BUILD_ZRAM,,}" in
        auto)
            # Only boards with < 4 GB RAM (they report < 3 GB MemTotal).
            if [[ "$mb" -le 0 || "$mb" -ge 3000 ]]; then return 0; fi
            ;;
        1|true|yes|on) : ;;
        *) return 0 ;;
    esac
    sudo modprobe zram 2>/dev/null || true
    dev="$(sudo zramctl --find --size 4G --algorithm zstd 2>/dev/null || true)"
    if [[ -z "$dev" ]]; then
        dev="$(sudo zramctl --find --size 4G 2>/dev/null || true)"
    fi
    if [[ -z "$dev" ]]; then
        warn "Could not create a zram device (zram/zramctl missing?); low-RAM build may OOM-kill cc1plus"
        return 0
    fi
    if ! sudo mkswap "$dev" >/dev/null 2>&1 || ! sudo swapon -p 100 "$dev" 2>/dev/null; then
        sudo zramctl --reset "$dev" 2>/dev/null || true
        warn "Could not enable zram swap on $dev; low-RAM build may OOM"
        return 0
    fi
    BUILD_ZRAM_DEV="$dev"
    log "Low-RAM board (${mb} MB): added 4 GB zram build swap on $dev (compressed RAM, removed after build)"
}

remove_build_zram() {
    if [[ -z "${BUILD_ZRAM_DEV:-}" ]]; then return 0; fi
    sudo swapoff "$BUILD_ZRAM_DEV" 2>/dev/null || true
    sudo zramctl --reset "$BUILD_ZRAM_DEV" 2>/dev/null || true
    detail "Removed build zram swap ($BUILD_ZRAM_DEV)"
    BUILD_ZRAM_DEV=""
}
trap remove_build_zram EXIT

build_libcamera() {
    # The build step below runs chmod +x on every .py/.sh file.  On Linux,
    # git tracks permission bits, so those mode changes show up as dirty and
    # block any subsequent git checkout.  Setting core.fileMode false tells
    # git to ignore executable-bit changes in this repo.  We also stash any
    # remaining real content changes (e.g. tuning JSONs) so the checkout
    # cannot be blocked on a re-run or upgrade.
    if [[ -d "$LIBCAMERA_DIR/.git" ]]; then
        run_as_pi git -C "$LIBCAMERA_DIR" config core.fileMode false
        run_as_pi git -C "$LIBCAMERA_DIR" stash 2>/dev/null || true
    fi

    ensure_repo "$LIBCAMERA_DIR" "$LIBCAMERA_REPO_URL" "$LIBCAMERA_REPO_REF"

    # Set core.fileMode false on a fresh clone too, so the first chmod+x
    # pass below does not dirty the tree on the next installer run.
    run_as_pi git -C "$LIBCAMERA_DIR" config core.fileMode false

    # Apply cherry-pick patches on top of the base ref.  A dedicated branch
    # (cinemate-patches) is created or reset each time so this step is
    # idempotent: re-running the installer cleanly re-applies the patches.
    if [[ -n "${LIBCAMERA_PATCHES:-}" ]]; then
        log "Applying libcamera patches on top of $LIBCAMERA_REPO_REF"
        run_as_pi git -C "$LIBCAMERA_DIR" checkout -B cinemate-patches "$LIBCAMERA_REPO_REF"
        for patch in $LIBCAMERA_PATCHES; do
            detail "Cherry-picking $patch"
            # -X theirs auto-resolves modify/delete conflicts (e.g. a file
            # that was added in an intermediate commit and is absent from
            # the base ref) by accepting the patch's version of the file.
            run_as_pi git -C "$LIBCAMERA_DIR" cherry-pick -X theirs "$patch"
        done
    fi

    log "Building libcamera"
    detail "Source: $LIBCAMERA_DIR"
    run_as_pi find "$LIBCAMERA_DIR" -type f \( -name '*.py' -o -name '*.sh' \) -exec chmod +x {} +
    run_as_pi chmod +x "$LIBCAMERA_DIR/src/ipa/ipa-sign.sh"
    # pycamera (the libcamera Python bindings) is disabled: nothing in the
    # CineMate stack imports it, and its generated py_controls_generated.cpp is a
    # pybind11 unit needing >1.5 GB to compile at -O3, which OOM-kills cc1plus on
    # 2 GB boards (e.g. a CM5). Disabling it also speeds the build up everywhere.
    run_as_pi_clean_shell "cd '$LIBCAMERA_DIR' && meson setup build --wipe --buildtype=release \
        -Dpipelines=rpi/vc4,rpi/pisp \
        -Dipas=rpi/vc4,rpi/pisp \
        -Dv4l2=true \
        -Dgstreamer=enabled \
        -Dtest=false \
        -Dlc-compliance=disabled \
        -Dcam=disabled \
        -Dqcam=disabled \
        -Ddocumentation=disabled \
        -Dpycamera=disabled"
    run_as_pi_clean_shell "ninja -C '$LIBCAMERA_DIR/build' -j '$BUILD_JOBS'"
    sudo ninja -C "$LIBCAMERA_DIR/build" install
    sudo ldconfig
}

build_cpp_mjpeg_streamer() {
    ensure_repo "$CPP_MJPEG_STREAMER_DIR" "$CPP_MJPEG_STREAMER_REPO_URL" "$CPP_MJPEG_STREAMER_REPO_REF"

    log "Building cpp-mjpeg-streamer"
    detail "Source: $CPP_MJPEG_STREAMER_DIR"
    run_as_pi_clean_shell "cd '$CPP_MJPEG_STREAMER_DIR' && cmake -S . -B build && cmake --build build -j '$BUILD_JOBS'"
    sudo cmake --build "$CPP_MJPEG_STREAMER_DIR/build" --target install
    sudo ldconfig
}

write_compile_raw_script() {
    log "Writing $PI_HOME/compile-raw.sh"
    write_user_file "$PI_HOME/compile-raw.sh" 755 <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail

CINEPI_RAW_DIR="\${CINEPI_RAW_DIR:-$CINEPI_RAW_DIR}"
CPP_MJPEG_STREAMER_DIR="\${CPP_MJPEG_STREAMER_DIR:-$CPP_MJPEG_STREAMER_DIR}"
BUILD_JOBS="\${BUILD_JOBS:-$BUILD_JOBS}"
BUILD_DIR="\${BUILD_DIR:-\$CINEPI_RAW_DIR/build}"
PKG_CONFIG_PATH="\$CPP_MJPEG_STREAMER_DIR/build:\${PKG_CONFIG_PATH:-}"
export PKG_CONFIG_PATH
FORCE_WIPE="\${FORCE_WIPE:-0}"

is_true() {
    case "\${1,,}" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
}

build_dir_has_entries() {
    [[ -d "\$1" ]] || return 1
    find "\$1" -mindepth 1 -maxdepth 1 -print -quit | grep -q .
}

# Temporary build swap for 1-2 GB boards: cinepi_raw.cpp needs ~2 GB at -O3 and
# OOM-kills cc1plus. Use compressed RAM (zram) -- no SD/eMMC writes -- removed on
# exit, so the running camera never swaps. Skipped when swap is already active
# (e.g. the installer set it up) or on boards with 4 GB+ RAM (>= 3000 MB).
CR_ZRAM_DEV=""
cr_cleanup_zram() {
    [[ -n "\${CR_ZRAM_DEV:-}" ]] || return 0
    sudo swapoff "\$CR_ZRAM_DEV" 2>/dev/null || true
    sudo zramctl --reset "\$CR_ZRAM_DEV" 2>/dev/null || true
    CR_ZRAM_DEV=""
}
trap cr_cleanup_zram EXIT
cr_mem_mb=\$(awk '/^MemTotal:/{print int(\$2/1024); exit}' /proc/meminfo 2>/dev/null || echo 0)
cr_swap_lines=\$(wc -l < /proc/swaps 2>/dev/null || echo 1)
if [[ "\$cr_mem_mb" -gt 0 && "\$cr_mem_mb" -lt 3000 && "\$cr_swap_lines" -le 1 ]]; then
    sudo modprobe zram 2>/dev/null || true
    CR_ZRAM_DEV=\$(sudo zramctl --find --size 4G --algorithm zstd 2>/dev/null || sudo zramctl --find --size 4G 2>/dev/null || true)
    if [[ -n "\$CR_ZRAM_DEV" ]] && sudo mkswap "\$CR_ZRAM_DEV" >/dev/null 2>&1 && sudo swapon -p 100 "\$CR_ZRAM_DEV" 2>/dev/null; then
        printf '[compile-raw] Low-RAM board (%s MB): added 4 GB zram build swap on %s (removed on exit)\n' "\$cr_mem_mb" "\$CR_ZRAM_DEV"
    else
        [[ -n "\$CR_ZRAM_DEV" ]] && sudo zramctl --reset "\$CR_ZRAM_DEV" 2>/dev/null || true
        CR_ZRAM_DEV=""
        printf '[compile-raw] WARNING: could not set up zram build swap; low-RAM build may OOM\n'
    fi
fi

printf '[compile-raw] Source: %s\n' "\$CINEPI_RAW_DIR"
printf '[compile-raw] Build directory: %s\n' "\$BUILD_DIR"
printf '[compile-raw] Using PKG_CONFIG_PATH=%s\n' "\$PKG_CONFIG_PATH"
if is_true "\$FORCE_WIPE"; then
    printf '[compile-raw] FORCE_WIPE requested; running meson setup --wipe\n'
    meson setup "\$BUILD_DIR" "\$CINEPI_RAW_DIR" --wipe
elif [[ -f "\$BUILD_DIR/build.ninja" || -f "\$BUILD_DIR/meson-private/coredata.dat" ]]; then
    printf '[compile-raw] Reusing existing Meson build directory with --reconfigure\n'
    if ! meson setup "\$BUILD_DIR" "\$CINEPI_RAW_DIR" --reconfigure; then
        printf '[compile-raw] Reconfigure failed; retrying with --wipe\n'
        meson setup "\$BUILD_DIR" "\$CINEPI_RAW_DIR" --wipe
    fi
elif build_dir_has_entries "\$BUILD_DIR"; then
    printf '[compile-raw] Build directory is non-empty but not reusable; running meson setup --wipe\n'
    meson setup "\$BUILD_DIR" "\$CINEPI_RAW_DIR" --wipe
else
    printf '[compile-raw] Running initial meson setup\n'
    meson setup "\$BUILD_DIR" "\$CINEPI_RAW_DIR"
fi
printf '[compile-raw] Building with ninja (%s jobs)\n' "\$BUILD_JOBS"
ninja -C "\$BUILD_DIR" -j "\$BUILD_JOBS"
printf '[compile-raw] Installing cinepi-raw\n'
sudo env PKG_CONFIG_PATH="\$PKG_CONFIG_PATH" meson install -C "\$BUILD_DIR"
printf '[compile-raw] Refreshing linker cache\n'
sudo ldconfig
EOF
}

build_cinepi_raw() {
    ensure_repo "$CINEPI_RAW_DIR" "$CINEPI_RAW_REPO_URL" "$CINEPI_RAW_REPO_REF"
    write_compile_raw_script

    log "Building cinepi-raw"
    detail "Source: $CINEPI_RAW_DIR"
    detail "Using helper script: $PI_HOME/compile-raw.sh"
    run_as_pi env BUILD_JOBS="$BUILD_JOBS" \
        CINEPI_RAW_DIR="$CINEPI_RAW_DIR" \
        CPP_MJPEG_STREAMER_DIR="$CPP_MJPEG_STREAMER_DIR" \
        "$PI_HOME/compile-raw.sh"
}

seed_cinepi_raw_white_balance() {
    log "Seeding initial CinePi-RAW white-balance defaults"
    detail "Setting cg_rb to 3.5,1.5 so CLI camera tests start with the same baseline as the manual flow"
    run_as_pi redis-cli SET cg_rb 3.5,1.5 >/dev/null
    run_as_pi redis-cli PUBLISH cp_controls cg_rb >/dev/null || true
}

install_lgpio_backend() {
    if ! is_true "$INSTALL_ALT_GPIO_BACKEND"; then
        detail "Skipping lgpio backend"
        return 0
    fi

    ensure_repo "$LGPIO_DIR" "$LGPIO_REPO_URL" "$LGPIO_REPO_REF"
    log "Building lgpio backend"
    run_as_pi make -C "$LGPIO_DIR" -j "$BUILD_JOBS"
    sudo make -C "$LGPIO_DIR" install
}

install_python_environment() {
    log "Creating Cinemate virtualenv"
    if [[ ! -d "$VENV_DIR" ]]; then
        detail "Creating new virtualenv at $VENV_DIR"
        run_as_pi python3 -m venv "$VENV_DIR"
    else
        detail "Reusing existing virtualenv at $VENV_DIR"
    fi

    sudo chown -R "$PI_USER:$PI_GROUP" "$VENV_DIR"

    local pip_cmd="$VENV_DIR/bin/pip"
    detail "Upgrading pip tooling"
    run_as_pi "$pip_cmd" install --upgrade pip setuptools wheel
    run_as_pi "$pip_cmd" uninstall -y board >/dev/null 2>&1 || true
    detail "Installing Cinemate Python packages"
    run_as_pi "$pip_cmd" install \
        gpiozero \
        adafruit-blinka adafruit-circuitpython-ssd1306 adafruit-circuitpython-seesaw \
        luma.oled grove.py pigpio-encoder smbus2 rpi_hardware_pwm \
        watchdog psutil pillow redis keyboard pyudev numpy termcolor sounddevice \
        evdev inotify_simple sysv_ipc flask_socketio sugarpie

    if is_true "$INSTALL_ALT_GPIO_BACKEND"; then
        detail "Installing lgpio Python package"
        run_as_pi "$pip_cmd" install lgpio
    fi
}

configure_loader_paths() {
    log "Configuring ld.so loader paths"
    backup_file /etc/ld.so.conf.d/cinepi-raw.conf
    write_root_file /etc/ld.so.conf.d/cinepi-raw.conf 644 <<EOF
$CINEPI_RAW_DIR/build
/usr/lib/aarch64-linux-gnu
/usr/local/lib/aarch64-linux-gnu
EOF
    sudo ldconfig
}

resolve_sensor_overlay() {
    local cam_port="$1"

    case "$SENSOR_MODEL" in
        imx477|imx296)
            CAMERA_AUTO_DETECT=1
            DTO_OVERLAY="${SENSOR_MODEL},${cam_port}"
            ;;
        imx283|imx585)
            CAMERA_AUTO_DETECT=0
            DTO_OVERLAY="${SENSOR_MODEL},${cam_port}"
            ;;
        imx585_mono)
            CAMERA_AUTO_DETECT=0
            DTO_OVERLAY="imx585,${cam_port},mono"
            ;;
        *)
            die "Unsupported SENSOR_MODEL: $SENSOR_MODEL"
            ;;
    esac
}

configure_boot_config() {
    local config_txt=/boot/firmware/config.txt
    local temp

    resolve_sensor_overlay "$CAM_PORT"
    detail "Configuring $config_txt for $DTO_OVERLAY"
    backup_file "$config_txt"
    temp="$(mktemp)"

    python3 - "$temp" "$MANAGED_BEGIN" "$MANAGED_END" "$DTO_OVERLAY" "$CAMERA_AUTO_DETECT" "$BT_OVERLAY" "$ENABLE_CFE_HAT_PCIE" "$SENSOR_MODEL" <<'PY'
import pathlib
import sys

dst = pathlib.Path(sys.argv[1])
begin = sys.argv[2]
end = sys.argv[3]
overlay = sys.argv[4]
camera_auto_detect = sys.argv[5]
bt_overlay = sys.argv[6]
enable_pcie = sys.argv[7].lower() in {"1", "true", "yes", "on"}
sensor_model = sys.argv[8]

def camera_section(label, key, default_auto_detect, default_overlay):
    active = key == sensor_model
    line_prefix = "" if active else "#"
    auto_detect = camera_auto_detect if active else default_auto_detect
    dtoverlay = overlay if active else default_overlay
    return [
        f"# {label}",
        f"{line_prefix}camera_auto_detect={auto_detect}",
        f"{line_prefix}dtoverlay={dtoverlay}",
        "",
    ]


block = [
    begin,
    "# Managed by cinemate-install.sh",
    "# For more options and information see",
    "# http://rptl.io/configtxt",
    "# Some settings may impact device functionality. See link above for details",
    "",
    "# Uncomment some or all of these to enable the optional hardware interfaces",
    "dtparam=i2c_arm=on",
    "#dtparam=i2s=on",
    "#dtparam=spi=on",
    "",
    "# Enable audio (loads snd_bcm2835)",
    "dtparam=audio=on",
    "",
    "# ---- Camera section ----",
    "",
]

block += camera_section(
    "Raspberry Pi HQ camera (IMX477, clean-install default on cam0)",
    "imx477",
    "1",
    "imx477,cam0",
)
block += camera_section(
    "Raspberry Pi GS camera (IMX296, 10-bit RAW)",
    "imx296",
    "1",
    "imx296,cam0",
)
block += camera_section(
    "OneInchEye (IMX283)",
    "imx283",
    "0",
    "imx283,cam0",
)
block += camera_section(
    "StarlightEye color (IMX585)",
    "imx585",
    "0",
    "imx585,cam0",
)
block += camera_section(
    "StarlightEye Mono (IMX585 mono)",
    "imx585_mono",
    "0",
    "imx585,cam1,mono",
)

block += [
    "# ---- End camera section ----",
    "",
    "# Automatically load overlays for detected DSI displays",
    "display_auto_detect=1",
    "",
    "# Automatically load initramfs files, if found",
    "auto_initramfs=1",
    "",
    "# Enable DRM VC4 V3D driver",
    "dtoverlay=vc4-kms-v3d",
    "max_framebuffers=2",
    "",
    "# Don't have the firmware create an initial video= setting in cmdline.txt.",
    "# Use the kernel's default instead.",
    "disable_fw_kms_setup=1",
    "",
    "# Run in 64-bit mode",
    "arm_64bit=1",
    "",
    "# Disable compensation for displays with overscan",
    "disable_overscan=1",
    "",
    "# Run as fast as firmware / board allows",
    "arm_boost=1",
    "",
    "[cm4]",
    "# Enable host mode on the 2711 built-in XHCI USB controller.",
    "# This line should be removed if the legacy DWC2 controller is required",
    "# (e.g. for USB device mode) or if USB support is not required.",
    "otg_mode=1",
    "",
    "[cm5]",
    "dtoverlay=dwc2,dr_mode=host",
]

if enable_pcie:
    block += [
        "",
        "# CFE Hat PCIe 3.0",
        "dtparam=pciex1",
        "dtparam=pciex1_gen=3",
    ]

block += [
    "",
    "[all]",
    "auto_initramfs=1",
    "avoid_warnings=1",
    "disable_splash=1",
    "hdmi_ignore_cec_init=1",
    "dtparam=i2c1=on",
    f"dtoverlay={bt_overlay}",
    end,
]

dst.write_text("\n".join(block) + "\n")
PY

    sudo install -m 644 "$temp" "$config_txt"
    rm -f "$temp"
}

configure_cmdline() {
    local cmdline=/boot/firmware/cmdline.txt
    local temp
    local connector="HDMI-A-$((HDMI_BOOT_PORT + 1))"
    local video_token="video=${connector}:${HDMI_MODE}"
    local -a extra_tokens=()

    if is_true "$INSTALL_PLYMOUTH"; then
        extra_tokens=(quiet splash loglevel=1 plymouth.ignore-serial-consoles vt.global_cursor_default=0 logo.nologo)
    fi

    # ── Audio-core CPU isolation (real-time audio capture) ───────────────
    # cinepi-audio-capture pins itself to the last core at SCHED_FIFO 80.
    # CPU affinity alone does not stop kernel threads, the timer tick, RCU
    # callbacks and device IRQs from sharing that core and jittering ALSA
    # capture. On the 4-core Pi 4/5, dedicate the last core (CPU 3) to audio
    # and keep IRQs + housekeeping on CPUs 0-2. isolcpus / rcu_nocbs /
    # irqaffinity take effect on stock kernels; nohz_full needs a NO_HZ_FULL
    # (RT) kernel and is harmless otherwise. Revert with `editcmdline` (delete
    # these tokens) or restore the cmdline.txt.bak backup, then reboot.
    local ncores audio_core house
    ncores="$(nproc 2>/dev/null || echo 0)"
    if [ "$ncores" = "4" ]; then
        audio_core=$((ncores - 1))
        house="0-$((audio_core - 1))"
        extra_tokens+=(
            "isolcpus=managed_irq,domain,${audio_core}"
            "nohz_full=${audio_core}"
            "rcu_nocbs=${audio_core}"
            "irqaffinity=${house}"
        )
        detail "Audio-core isolation: reserving CPU ${audio_core} for capture (IRQs/housekeeping on ${house})"
    fi

    # ── Boot time: skip redundant fsck on every clean boot ───────────────
    extra_tokens+=("fsck.mode=skip")

    detail "Ensuring $cmdline contains $video_token"
    backup_file "$cmdline"
    temp="$(mktemp)"

    python3 - "$cmdline" "$temp" "$video_token" "${extra_tokens[@]}" <<'PY'
import pathlib
import sys

src = pathlib.Path(sys.argv[1])
dst = pathlib.Path(sys.argv[2])
video_token = sys.argv[3]
extra = sys.argv[4:]

tokens = src.read_text().strip().split() if src.exists() else []
# Always re-manage the video= token. Re-manage the CPU-isolation tokens only
# when we are (re)adding them, so a changed core count can't leave a stale
# isolcpus=...,N behind, and a non-isolation run never strips a user's own.
managed = ["video=HDMI-A-", "fsck.mode="]
if any(t.startswith("isolcpus=") for t in extra):
    managed += ["isolcpus=", "nohz_full=", "rcu_nocbs=", "irqaffinity="]
tokens = [tok for tok in tokens if not tok.startswith(tuple(managed))]

for tok in extra + [video_token]:
    if tok not in tokens:
        tokens.append(tok)

dst.write_text(" ".join(tokens).strip() + "\n")
PY

    sudo install -m 644 "$temp" "$cmdline"
    rm -f "$temp"
}

configure_asound() {
    log "Writing /etc/asound.conf"
    detail "24-bit card: $AUDIO_CARD_24, 16-bit card: $AUDIO_CARD_16"
    backup_file /etc/asound.conf
    write_root_file /etc/asound.conf 644 <<EOF
# RODE NTG path (24-bit stereo)
pcm.mic_dsnoop_24 {
  type dsnoop
  ipc_key 5978
  ipc_perm 0666
  ipc_key_add_uid false
  slave {
    pcm "hw:CARD=${AUDIO_CARD_24},DEV=0"
    format S24_3LE
    rate 48000
    channels 2
  }
  bindings.0 0
  bindings.1 1
}

# Cheap USB path (16-bit mono)
pcm.mic_dsnoop_16 {
  type dsnoop
  ipc_key 5979
  ipc_perm 0666
  ipc_key_add_uid false
  slave {
    pcm "hw:CARD=${AUDIO_CARD_16},DEV=0"
    format S16_LE
    rate 48000
    channels 1
  }
  bindings.0 0
}

pcm.mic_24bit { type plug; slave.pcm "mic_dsnoop_24" }
pcm.mic_16bit { type plug; slave.pcm "mic_dsnoop_16" }
EOF
}

configure_post_processing() {
    log "Writing post-processing JSON files"
    write_user_file "$PI_HOME/post-processing.json" 644 <<'EOF'
{
  "sharedContext": {},
  "mjpegPreview": {
    "port": 8000
  }
}
EOF
    write_user_file "$PI_HOME/post-processing0.json" 644 <<'EOF'
{
  "sharedContext": {},
  "mjpegPreview": {
    "port": 8000
  }
}
EOF
    write_user_file "$PI_HOME/post-processing1.json" 644 <<'EOF'
{
  "sharedContext": {},
  "mjpegPreview": {
    "port": 8001
  }
}
EOF
}

configure_hostname_and_i2c() {
    log "Enabling I2C and setting hostname"
    detail "Target hostname: $TARGET_HOSTNAME"
    sudo raspi-config nonint do_i2c 0 || warn "raspi-config could not enable I2C automatically"
    sudo hostnamectl set-hostname "$TARGET_HOSTNAME"
    sudo usermod -aG i2c "$PI_USER"
    sudo modprobe i2c-dev || true
    ensure_line_in_root_file /etc/modules 'i2c-dev'
}

configure_console_font() {
    if ! is_true "$INSTALL_CONSOLE_FONT"; then
        detail "Skipping console font setup"
        return 0
    fi

    log "Configuring console font"
    backup_file /etc/default/console-setup
    sudo bash "$CINEMATE_SOURCE_DIR/services/console-setup/setup-console-font.sh"
    sudo systemctl enable console-setup.service
    sudo systemctl start console-setup.service
}

configure_console_autologin() {
    if ! is_true "$ENABLE_CONSOLE_AUTOLOGIN"; then
        detail "Skipping console auto-login setup"
        return 0
    fi

    local dropin_dir="/etc/systemd/system/getty@tty1.service.d"
    local override="$dropin_dir/autologin.conf"

    log "Configuring tty1 console auto-login"
    detail "Auto-login user: $PI_USER"
    sudo install -d -m 755 "$dropin_dir"
    backup_file "$override"
    write_root_file "$override" 644 <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $PI_USER --noclear %I \$TERM
EOF
    sudo systemctl daemon-reload
    detail "Console auto-login will apply on the next tty1 restart or reboot"
}

configure_pishrink() {
    if ! is_true "$INSTALL_PISHRINK"; then
        detail "Skipping PiShrink install"
        return 0
    fi

    log "Installing PiShrink"
    sudo wget -qO /usr/local/bin/pishrink.sh "$PISHRINK_URL"
    sudo chmod 755 /usr/local/bin/pishrink.sh
}

configure_plymouth() {
    if ! is_true "$INSTALL_PLYMOUTH"; then
        detail "Skipping Plymouth setup"
        return 0
    fi

    log "Configuring Plymouth boot spinner"
    local theme_name="cinemate"
    local theme_source_dir="$CINEMATE_SOURCE_DIR/resources/plymouth/$theme_name"
    local theme_target_dir="/usr/share/plymouth/themes/$theme_name"

    [[ -f "$theme_source_dir/$theme_name.plymouth" ]] || die "Missing Plymouth theme file: $theme_source_dir/$theme_name.plymouth"
    [[ -f "$theme_source_dir/$theme_name.script" ]] || die "Missing Plymouth theme script: $theme_source_dir/$theme_name.script"

    detail "Installing Cinemate Plymouth theme to $theme_target_dir"
    sudo install -d -m 755 "$theme_target_dir"
    sudo install -m 644 "$theme_source_dir/$theme_name.plymouth" "$theme_target_dir/$theme_name.plymouth"
    sudo install -m 644 "$theme_source_dir/$theme_name.script" "$theme_target_dir/$theme_name.script"

    backup_file /etc/plymouth/plymouthd.conf
    write_root_file /etc/plymouth/plymouthd.conf 644 <<EOF
[Daemon]
Theme=$theme_name
DeviceScale=4
EOF
    sudo plymouth-set-default-theme "$theme_name"
    sudo update-initramfs -u
}

install_imx585_support() {
    if ! should_install_imx585_driver; then
        detail "Skipping IMX585 driver support"
        return 0
    fi

    ensure_repo "$IMX585_DRIVER_DIR" "$IMX585_DRIVER_REPO_URL" "$IMX585_DRIVER_REPO_REF"
    log "Installing IMX585 driver"
    run_as_pi_clean_shell "cd '$IMX585_DRIVER_DIR' && ./setup.sh"
    if is_rpi2712_platform; then
        detail "Ensuring DKMS builds IMX585 for the pinned Pi 5 kernel baseline"
        sudo dkms autoinstall -k "$KERNEL_BASELINE_ABI_2712"
    fi
}

install_imx283_support() {
    if ! should_install_imx283_driver; then
        detail "Skipping IMX283 driver support"
        return 0
    fi

    ensure_repo "$IMX283_DRIVER_DIR" "$IMX283_DRIVER_REPO_URL" "$IMX283_DRIVER_REPO_REF"
    log "Installing IMX283 driver"
    run_as_pi_clean_shell "cd '$IMX283_DRIVER_DIR' && ./setup.sh"
    if is_rpi2712_platform; then
        detail "Ensuring DKMS builds IMX283 for the pinned Pi 5 kernel baseline"
        sudo dkms autoinstall -k "$KERNEL_BASELINE_ABI_2712"
    fi
}

install_sensor_tuning_overrides() {
    log "Installing Cinemate sensor tuning overrides"
    local local_tuning_dir="$CINEMATE_SOURCE_DIR/resources/tuning_files"
    # All current Cinemate tuning overrides are pisp-target (Pi 5 / PiSP ISP),
    # so they are installed ONLY into the pisp data dirs. libcamera matches a
    # tuning file's "target" against the active pipeline; dropping a pisp tuning
    # into the vc4 (Pi 4) data dir applies the wrong hardware config and also
    # clobbers the stock bcm2835-target imx283.json that Pi 4 needs. (imx585 has
    # no vc4 cam_helper either, so it never runs on Pi 4 regardless.) If a
    # bcm2835-target override is added later, install it into the vc4 dirs here.
    local -a tuning_files=(
        imx283.json
        imx585.json
        imx585_mono.json
    )
    local source_pisp_dir="$LIBCAMERA_DIR/src/ipa/rpi/pisp/data"
    local install_pisp_dir="/usr/local/share/libcamera/ipa/rpi/pisp"
    local tuning_file=""

    [[ -d "$local_tuning_dir" ]] || die "Missing tuning files in $local_tuning_dir"
    run_as_pi install -d -m 755 "$source_pisp_dir"
    sudo install -d -m 755 "$install_pisp_dir"
    for tuning_file in "${tuning_files[@]}"; do
        run_as_pi install -m 644 "$local_tuning_dir/$tuning_file" "$source_pisp_dir/$tuning_file"
        sudo install -m 644 "$local_tuning_dir/$tuning_file" "$install_pisp_dir/$tuning_file"
    done
}

install_ir_filter_helper() {
    if ! should_install_ir_filter_helper; then
        detail "Skipping IRFilter helper"
        return 0
    fi

    log "Installing IRFilter helper"
    sudo wget -qO /usr/local/bin/IRFilter "$IR_FILTER_URL"
    sudo chmod 755 /usr/local/bin/IRFilter
}

configure_services_base() {
    log "Enabling Redis and NetworkManager"
    sudo systemctl enable --now redis-server
    sudo systemctl enable --now NetworkManager
    detail "redis-server and NetworkManager are enabled"
}

configure_boot_optimizations() {
    log "Disabling unused background services and timers"

    local -a boot_units=(
        NetworkManager-wait-online.service
        dphys-swapfile.service
        triggerhappy.service
        ModemManager.service
        systemd-rfkill.service
        man-db.timer
        apt-daily.timer
        apt-daily-upgrade.timer
        e2scrub_all.timer
    )

    for unit in "${boot_units[@]}"; do
        if sudo systemctl list-unit-files "$unit" 2>/dev/null | grep -q "$unit"; then
            detail "Disabling $unit"
            sudo systemctl disable --now "$unit" 2>/dev/null || true
        else
            detail "Skipping $unit (not installed)"
        fi
    done
}

configure_logrotate() {
    log "Writing logrotate rule"
    backup_file /etc/logrotate.d/general_logs
    write_root_file /etc/logrotate.d/general_logs 644 <<'EOF'
/var/log/*.log {
   size 100M
   rotate 5
   compress
   missingok
   notifempty
}
EOF
}

configure_run_wrapper() {
    log "Writing run_cinemate.sh wrapper"
    write_user_file "$PI_HOME/run_cinemate.sh" 755 <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
exec "$VENV_DIR/bin/python3" "$CINEMATE_DIR/src/main.py" "\$@"
EOF
}

configure_audio_rtprio() {
    log "Granting real-time scheduling priority to @audio group"
    # cinepi-audio-capture uses SCHED_FIFO to stay ahead of DNG-writer I/O.
    # Without this, sched_setscheduler(SCHED_FIFO) returns EPERM for the pi
    # user when cinemate runs outside of systemd (manual / dev runs).
    # The cinemate-autostart.service unit already carries LimitRTPRIO=30,
    # but this limits.d drop-in extends the same right to shell sessions so
    # that manual cinemate runs benefit from the same drift protection.
    backup_file /etc/security/limits.d/cinemate-audio.conf
    write_root_file /etc/security/limits.d/cinemate-audio.conf 644 <<EOF
# Allow the audio group to use real-time scheduling (SCHED_FIFO).
# Required by cinepi-audio-capture (cinepi-raw) for xrun-resistant
# 24-bit audio capture alongside heavy DNG write I/O.
@audio - rtprio 80
@audio - memlock unlimited
EOF
    sudo usermod -aG audio "$PI_USER"
    detail "Added $PI_USER to audio group; re-login required for limits to take effect"
}

configure_sudoers() {
    log "Writing sudoers drop-ins"
    backup_file /etc/sudoers.d/cinemate-env
    backup_file /etc/sudoers.d/pi_cinemate
    write_root_file /etc/sudoers.d/cinemate-env 440 <<EOF
$PI_USER ALL=(ALL) NOPASSWD: $VENV_DIR/bin/*
EOF
    write_root_file /etc/sudoers.d/pi_cinemate 440 <<EOF
$PI_USER ALL=(ALL) NOPASSWD: $PI_HOME/run_cinemate.sh
$PI_USER ALL=(ALL) NOPASSWD: $CINEMATE_DIR/src/main.py
$PI_USER ALL=(ALL) NOPASSWD: /bin/mount, /bin/umount, /usr/bin/ntfs-3g
$PI_USER ALL=(ALL) NOPASSWD: /sbin/mount.ext4
EOF
    sudo visudo -cf /etc/sudoers.d/cinemate-env >/dev/null
    sudo visudo -cf /etc/sudoers.d/pi_cinemate >/dev/null
    detail "sudoers validation passed"
}

configure_bashrc() {
    local bashrc="$PI_HOME/.bashrc"
    local temp
    local existing=""

    log "Updating .bashrc helpers"
    temp="$(mktemp)"

    if [[ -f "$bashrc" ]]; then
        backup_file "$bashrc"
        existing="$(cat "$bashrc")"
    fi

    detail "Replacing managed block in $bashrc without duplicating aliases"
    printf '%s\n' "$existing" | sed "/^${MANAGED_BEGIN//\//\\/}\$/,/^${MANAGED_END//\//\\/}\$/d" >"$temp"
    cat >>"$temp" <<EOF

$MANAGED_BEGIN
source "$VENV_DIR/bin/activate"
alias cinemate-env='source "$VENV_DIR/bin/activate"'
alias cinemate='$PI_HOME/run_cinemate.sh'
alias editboot='sudo nano /boot/firmware/config.txt'
alias editcmdline='sudo nano /boot/firmware/cmdline.txt'
alias editsettings='sudo nano $CINEMATE_DIR/src/settings.json'
$MANAGED_END
EOF

    sudo install -o "$PI_USER" -g "$PI_GROUP" -m 644 "$temp" "$bashrc"
    rm -f "$temp"
}

print_post_install_notes() {
    section "Post-install notes"
    log "Cinemate virtualenv: $VENV_DIR"
    detail "cinepi-raw rebuild helper: $PI_HOME/compile-raw.sh"
    detail "Matching rpicam utilities are installed via the cinepi-raw build under /usr/local/bin"
    detail "New interactive shells will auto-activate the Cinemate virtualenv from $PI_HOME/.bashrc"
    detail "If you are staying in this shell, run 'source ~/.bashrc' once to load the aliases now"
    detail "If you ever run 'deactivate', use 'cinemate-env' to reactivate the virtualenv in the current shell"
    if ((KERNEL_ALIGNMENT_REQUIRED_REBOOT)); then
        detail "Pi 5 kernel baseline was aligned to $KERNEL_BASELINE_ABI_2712; reboot once before camera testing if you did not run the installer with RUN_REBOOT=1"
    fi
    detail "Use 'cinemate' to launch the runtime wrapper manually"
}

configure_settings_json() {
    local settings_json="$CINEMATE_DIR/src/settings.json"
    local hotspot_enabled_json=false

    [[ -f "$settings_json" ]] || die "Missing settings.json at $settings_json"
    is_true "$HOTSPOT_ENABLED" && hotspot_enabled_json=true

    log "Patching settings.json"
    detail "Applying hotspot + HDMI defaults to $settings_json"
    backup_file "$settings_json"
    run_as_pi python3 - "$settings_json" "$HOTSPOT_NAME" "$HOTSPOT_PASSWORD" "$hotspot_enabled_json" "$HDMI_PORT_CAM0" "$HDMI_PORT_CAM1" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
ssid = sys.argv[2]
password = sys.argv[3]
enabled = sys.argv[4].lower() == "true"
hdmi0 = int(sys.argv[5])
hdmi1 = int(sys.argv[6])

data = json.loads(path.read_text())
system_cfg = data.setdefault("system", {})
wifi_cfg = system_cfg.setdefault("wifi_hotspot", {})
wifi_cfg["name"] = ssid
wifi_cfg["password"] = password
wifi_cfg["enabled"] = enabled

output_cfg = data.setdefault("output", {})
output_cfg.setdefault("cam0", {})["hdmi_port"] = hdmi0
output_cfg.setdefault("cam1", {})["hdmi_port"] = hdmi1

hdmi_display = data.setdefault("hdmi_display", {})
hdmi_display.setdefault("width", 1920)
hdmi_display.setdefault("height", 1080)

path.write_text(json.dumps(data, indent=2) + "\n")
PY
}

seed_redis_defaults() {
    log "Seeding Redis defaults"
    detail "Writing default runtime keys and white-balance defaults"
    run_as_pi redis-cli MSET \
        anamorphic_factor 0 bit_depth 0 buffer 0 buffer_size 0 cam_init 0 cameras 0 cg_rb 3.5,1.5 \
        file_size 0 fps 24 fps_actual 24 fps_last 24 fps_max 1 fps_user 24 framecount 0 \
        gui_layout 0 height 0 ir_filter 0 is_buffering 0 is_mounted 0 is_recording 0 \
        is_writing 0 is_writing_buf 0 tc_cam0 0 tc_cam1 0 iso 100 lores_height 0 lores_width 0 \
        pi_model 0 rec 0 sensor 0 shutter_a 0 space_left 0 storage_type 0 \
        wb 5600 wb_user 5600 width 0 memory_alert 0 \
        shutter_a_sync_mode 0 shutter_angle_nom 0 shutter_angle_actual 0 shutter_angle_transient 0 \
        exposure_time 0 last_dng_cam1 0 last_dng_cam0 0 \
        zoom 0 write_speed_to_drive 0 recording_time 0 >/dev/null
    run_as_pi redis-cli SETNX sensor_mode 0 >/dev/null
    run_as_pi redis-cli SET cg_rb 3.5,1.5 >/dev/null
    run_as_pi redis-cli PUBLISH cp_controls cg_rb >/dev/null || true
}

configure_media_permissions() {
    log "Ensuring /media permissions"
    sudo mkdir -p /media
    sudo chown -R "$PI_USER:$PI_GROUP" /media
    sudo chmod 755 /media
    detail "/media is owned by $PI_USER:$PI_GROUP"
}

install_cinemate_services() {
    if is_true "$ENABLE_SUPPORT_SERVICES"; then
        if is_true "$ENABLE_STORAGE_AUTOMOUNT_SERVICE"; then
            log "Installing and enabling storage-automount.service"
            sudo make -C "$CINEMATE_SOURCE_DIR/services" enable-storage-automount
        else
            detail "Skipping storage-automount.service"
        fi

        if is_true "$ENABLE_WIFI_HOTSPOT_SERVICE"; then
            log "Installing and enabling wifi-hotspot.service"
            sudo make -C "$CINEMATE_SOURCE_DIR/services" enable-wifi-hotspot
        else
            detail "Skipping wifi-hotspot.service"
        fi

        if is_true "$ENABLE_REDIS_LOG_MAINTENANCE_SERVICE"; then
            log "Installing and enabling redis-log-maintenance.timer"
            sudo make -C "$CINEMATE_SOURCE_DIR/services" enable-redis-log-maintenance
            detail "Running one redis-log-maintenance pass now to match the manual service flow"
            sudo make -C "$CINEMATE_SOURCE_DIR/services" start-redis-log-maintenance
        else
            detail "Skipping redis-log-maintenance.timer"
        fi
    else
        detail "Skipping support services"
    fi

    if is_true "$ENABLE_AUTOSTART"; then
        log "Installing Cinemate autostart service"
        sudo make -C "$CINEMATE_SOURCE_DIR" install
        sudo make -C "$CINEMATE_SOURCE_DIR" enable
        if is_true "$START_AUTOSTART_NOW"; then
            local active_tty
            active_tty="$(current_tty)"
            if [[ "$active_tty" == "/dev/tty1" ]]; then
                warn "Skipping immediate cinemate-autostart start because the installer is running on tty1 and the service takes over tty1. Reboot or run 'sudo systemctl start cinemate-autostart' from SSH after the installer exits."
            else
                detail "Starting cinemate-autostart.service now"
                if ! sudo make -C "$CINEMATE_SOURCE_DIR" start; then
                    warn "Could not start cinemate-autostart.service immediately. The service is still installed and enabled for next boot."
                fi
            fi
        else
            detail "Autostart enabled for next boot; not starting during installer"
        fi
    else
        detail "Skipping Cinemate autostart service"
    fi
}

main() {
    id "$PI_USER" >/dev/null 2>&1 || die "User $PI_USER does not exist"

    SENSOR_MODEL="${SENSOR_MODEL,,}"
    CAM_PORT="$(normalize_cam_port "$CAM_PORT")"
    HDMI_BOOT_PORT="$(normalize_hdmi_port "$HDMI_BOOT_PORT")"
    HDMI_PORT_CAM0="$(normalize_hdmi_port "$HDMI_PORT_CAM0")"
    HDMI_PORT_CAM1="$(normalize_hdmi_port "$HDMI_PORT_CAM1")"
    [[ ${#HOTSPOT_PASSWORD} -ge 8 ]] || die "HOTSPOT_PASSWORD must be at least 8 characters"
    [[ "$BT_OVERLAY" == "disable-bt" || "$BT_OVERLAY" == "miniuart-bt" ]] || die "BT_OVERLAY must be disable-bt or miniuart-bt"

    section "Validating environment and installer configuration"
    bootstrap_sudo
    validate_supported_os
    print_configuration_summary

    section "Installing bootstrap tools"
    bootstrap_base_tools
    section "Aligning the Pi 5 kernel baseline"
    align_pi5_kernel_baseline

    section "Locating the Cinemate source tree"
    configure_repo_source

    BACKUP_DIR="$PI_HOME/.cinemate-install-backups/$(date +%Y%m%d-%H%M%S)"
    sudo mkdir -p "$BACKUP_DIR"
    sudo chown -R "$PI_USER:$PI_GROUP" "$BACKUP_DIR"
    detail "Backups for changed files will be stored in $BACKUP_DIR"

    section "Installing apt dependencies"
    install_apt_packages
    section "Enabling base system services"
    configure_services_base
    section "Applying boot time optimizations"
    configure_boot_optimizations
    section "Refreshing the libtiff linker fix"
    prepare_libtiff_link
    section "Building redis-plus-plus"
    build_redis_plus_plus
    ensure_build_zram   # compressed-RAM build swap on < 4 GB boards; removed after
    section "Building libcamera"
    build_libcamera
    section "Building cpp-mjpeg-streamer"
    build_cpp_mjpeg_streamer
    section "Building cinepi-raw"
    build_cinepi_raw
    remove_build_zram
    section "Seeding initial cinepi-raw Redis defaults"
    seed_cinepi_raw_white_balance
    section "Installing sensor-specific support"
    install_imx283_support
    install_imx585_support
    install_sensor_tuning_overrides
    install_ir_filter_helper
    section "Installing optional GPIO backend"
    install_lgpio_backend
    section "Preparing the Python environment"
    install_python_environment
    section "Writing runtime loader configuration"
    configure_loader_paths
    section "Configuring hostname and I2C"
    configure_hostname_and_i2c
    section "Writing boot configuration"
    configure_boot_config
    configure_cmdline
    section "Writing audio and preview helper files"
    configure_asound
    configure_post_processing
    section "Applying optional UI and boot helpers"
    configure_console_font
    configure_console_autologin
    configure_pishrink
    configure_plymouth
    section "Refreshing Pi 5 boot handoff"
    refresh_pi5_boot_handoff
    section "Preparing runtime wrappers and permissions"
    configure_media_permissions
    configure_run_wrapper
    configure_sudoers
    configure_audio_rtprio
    configure_logrotate
    configure_bashrc
    configure_settings_json
    section "Seeding Redis defaults"
    seed_redis_defaults
    section "Installing Cinemate services"
    install_cinemate_services

    print_post_install_notes

    section "Finishing up"
    log "Install complete"
    log "Backups saved under $BACKUP_DIR"

    if is_true "$RUN_REBOOT"; then
        log "Rebooting now"
        sudo reboot
    else
        log "Reboot recommended before first camera test"
    fi
}

main "$@"
