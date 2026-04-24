#!/usr/bin/env bash

set -euo pipefail

readonly TTY_PATH="/dev/tty1"
readonly FAILURE_FILE="${CINEMATE_STARTUP_FAILURE_FILE:-/run/cinemate-autostart/startup-failure.ansi}"

if [[ ! -s "${FAILURE_FILE}" ]]; then
    exit 0
fi

/usr/bin/python3 -c 'import fcntl, os; fd = os.open("/dev/tty1", os.O_RDWR | os.O_CLOEXEC); fcntl.ioctl(fd, 0x4B3A, 0); os.close(fd)' 2>/dev/null || true

{
    printf '\033[2J\033[H'
    cat "${FAILURE_FILE}"
    printf '\033[0m\033[?25h\n'
} > "${TTY_PATH}" || true
