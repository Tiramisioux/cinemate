#!/usr/bin/env bash
#
# camera-ready.sh - Camera Detection Verification Script
#
# This script waits for the camera sensor to be properly initialized before
# allowing the Cinemate service to start. This solves the "black screen on boot"
# issue where the GUI starts before the IMX283 (or other) sensor is ready.
#
# Used by: systemd cinemate-autostart.service
# Location: /usr/local/bin/camera-ready.sh
#
# Exit Codes:
#   0 - Camera detected and ready
#   1 - Camera not detected after timeout
#
# Author: Cinemate Community
# Version: 1.0.0
# Date: 2025-10-15
#

set -euo pipefail

# Configuration
readonly MAX_ATTEMPTS=30           # Maximum number of detection attempts
readonly RETRY_INTERVAL=1          # Seconds between attempts
readonly LOG_TAG="camera-ready"    # Tag for systemd journal logging

# Colors for console output (when running manually)
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# ────────────────────────────────────────────────────────────────────────────
# Logging Functions
# ────────────────────────────────────────────────────────────────────────────

# Log to systemd journal with priority
log_info() {
    echo "<6>${LOG_TAG}: $1" >&2
}

log_warning() {
    echo "<4>${LOG_TAG}: $1" >&2
}

log_error() {
    echo "<3>${LOG_TAG}: $1" >&2
}

# Console output (for manual testing)
print_info() {
    if [[ -t 1 ]]; then
        echo -e "${BLUE}[INFO]${NC} $1"
    fi
}

print_success() {
    if [[ -t 1 ]]; then
        echo -e "${GREEN}[OK]${NC} $1"
    fi
}

print_warning() {
    if [[ -t 1 ]]; then
        echo -e "${YELLOW}[WARN]${NC} $1"
    fi
}

print_error() {
    if [[ -t 1 ]]; then
        echo -e "${RED}[ERROR]${NC} $1"
    fi
}

# ────────────────────────────────────────────────────────────────────────────
# Pre-flight Checks
# ────────────────────────────────────────────────────────────────────────────

# Check if cinepi-raw command exists
check_cinepi_command() {
    if ! command -v cinepi-raw &> /dev/null; then
        log_error "cinepi-raw command not found"
        print_error "cinepi-raw command not found in PATH"
        return 1
    fi
    return 0
}

# Check if I2C is enabled (required for camera communication)
check_i2c_enabled() {
    if [[ ! -e /dev/i2c-0 ]] && [[ ! -e /dev/i2c-1 ]]; then
        log_warning "No I2C devices found - camera may not be accessible"
        print_warning "No I2C devices found (/dev/i2c-0 or /dev/i2c-1)"
        # Don't fail - continue with detection attempt
    fi
}

# ────────────────────────────────────────────────────────────────────────────
# Camera Detection
# ────────────────────────────────────────────────────────────────────────────

# Check if any camera is detected by cinepi-raw
detect_camera() {
    local attempt="$1"

    # Run cinepi-raw --list-cameras and capture output
    local output
    local exit_code=0

    output=$(cinepi-raw --list-cameras 2>&1) || exit_code=$?

    # Check if we got any camera output
    # cinepi-raw lists cameras as: "0 : imx283 [5472x3648 ...] (...)"
    if echo "$output" | grep -qE "^\s*[0-9]+\s*:\s*imx"; then
        # Camera found!
        local camera_name
        camera_name=$(echo "$output" | grep -oE "imx[0-9]+" | head -n 1)

        log_info "Camera detected: ${camera_name} (attempt ${attempt}/${MAX_ATTEMPTS})"
        print_success "Camera detected: ${camera_name} (attempt ${attempt}/${MAX_ATTEMPTS})"

        return 0
    fi

    # No camera detected
    if [[ ${attempt} -eq 1 ]]; then
        # First attempt - log at info level
        log_info "Waiting for camera initialization (attempt ${attempt}/${MAX_ATTEMPTS})"
        print_info "Waiting for camera initialization (attempt ${attempt}/${MAX_ATTEMPTS})..."
    elif [[ ${attempt} -eq $((MAX_ATTEMPTS / 2)) ]]; then
        # Halfway through - log a warning
        log_warning "Camera not yet detected after ${attempt} attempts (${attempt}s elapsed)"
        print_warning "Camera not detected after ${attempt} seconds..."
    fi

    return 1
}

# ────────────────────────────────────────────────────────────────────────────
# Main Detection Loop
# ────────────────────────────────────────────────────────────────────────────

main() {
    local attempt=1

    log_info "Camera detection starting (timeout: ${MAX_ATTEMPTS}s)"
    print_info "Checking camera readiness..."

    # Pre-flight checks
    if ! check_cinepi_command; then
        log_error "Pre-flight check failed: cinepi-raw not found"
        print_error "Cannot proceed without cinepi-raw command"
        exit 1
    fi

    check_i2c_enabled

    # Detection loop
    while [[ ${attempt} -le ${MAX_ATTEMPTS} ]]; do
        if detect_camera "${attempt}"; then
            # Camera detected - success!
            log_info "Camera ready - Cinemate can start"
            print_success "Camera ready - proceeding with Cinemate startup"
            exit 0
        fi

        # Wait before next attempt
        sleep "${RETRY_INTERVAL}"
        ((attempt++))
    done

    # Timeout reached - camera not detected
    log_error "Camera detection timeout after ${MAX_ATTEMPTS} attempts (${MAX_ATTEMPTS}s)"
    print_error "Camera not detected after ${MAX_ATTEMPTS} seconds"
    print_error "Cinemate may start with black screen"

    # Log helpful troubleshooting info
    log_error "Troubleshooting hints:"
    log_error "1. Check /boot/firmware/config.txt for correct dtoverlay"
    log_error "2. Verify camera cable connection"
    log_error "3. Check 'dmesg | grep -i imx' for driver errors"
    log_error "4. Ensure I2C is enabled: 'sudo raspi-config nonint do_i2c 0'"

    print_error ""
    print_error "Troubleshooting:"
    print_error "  - Check camera cable connection"
    print_error "  - Verify /boot/firmware/config.txt has correct dtoverlay"
    print_error "  - Check: dmesg | grep -i imx"
    print_error "  - Check: journalctl -u cinemate-autostart"

    exit 1
}

# ────────────────────────────────────────────────────────────────────────────
# Entry Point
# ────────────────────────────────────────────────────────────────────────────

main "$@"
