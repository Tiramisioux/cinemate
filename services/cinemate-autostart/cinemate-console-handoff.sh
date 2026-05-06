#!/usr/bin/env bash

set -euo pipefail

shutdown_targets=(
    halt.target
    kexec.target
    poweroff.target
    reboot.target
    shutdown.target
)

systemd_manager_stopping() {
    local state
    state=$(/bin/systemctl is-system-running 2>/dev/null || true)
    [[ "${state}" == "stopping" || "${state}" == "offline" ]]
}

shutdown_job_in_progress() {
    local unit

    while read -r _job_id unit _job_type _job_state _rest; do
        [[ -z "${unit:-}" ]] && continue

        for target in "${shutdown_targets[@]}"; do
            if [[ "${unit}" == "${target}" ]]; then
                return 0
            fi
        done
    done < <(/bin/systemctl list-jobs --no-legend --no-pager 2>/dev/null || true)

    return 1
}

if systemd_manager_stopping || shutdown_job_in_progress; then
    /bin/systemctl --no-block start plymouth-start.service >/dev/null 2>&1 || true
    if command -v plymouth >/dev/null 2>&1; then
        plymouth change-mode --shutdown >/dev/null 2>&1 || true
        plymouth show-splash >/dev/null 2>&1 || true
    fi
    exit 0
fi

/bin/systemctl start getty@tty1.service >/dev/null 2>&1 || true
