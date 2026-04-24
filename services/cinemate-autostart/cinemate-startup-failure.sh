failure_file="${CINEMATE_STARTUP_FAILURE_FILE:-/home/pi/.cache/cinemate/startup-failure.ansi}"

case $- in
    *i*) ;;
    *) return 0 2>/dev/null || exit 0 ;;
esac

if [[ "$(tty 2>/dev/null)" != "/dev/tty1" ]]; then
    return 0 2>/dev/null || exit 0
fi

if [[ -s "${failure_file}" ]]; then
    printf '\033[2J\033[H'
    cat "${failure_file}"
    printf '\033[0m\033[?25h\n'
    stty sane 2>/dev/null || true
    rm -f "${failure_file}"
fi
