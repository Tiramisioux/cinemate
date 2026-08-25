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
    sudo -n /bin/systemctl --no-block start plymouth-start.service >/dev/null 2>&1 || true
    if command -v plymouth >/dev/null 2>&1; then
        plymouth change-mode --shutdown >/dev/null 2>&1 || true
        plymouth show-splash >/dev/null 2>&1 || true
    fi
    exit 0
fi

# Unprivileged `systemctl start` triggers a PolicyKit prompt that blocks
# forever with no tty to answer it -- systemd then kills this ExecStopPost
# step at TimeoutStopSec and the unit lands failed instead of restarting.
# `pi` has passwordless sudo; running as root skips the prompt. Fixes
# F-283's reported symptom (restart hangs, unit lands failed) -- verified
# on hardware across many restarts, ExecStopPost now always completes in
# well under a second.
#
# A separate, narrower race remains open: cinemate-autostart.service
# declares Conflicts=getty@tty1.service, and on hardware this getty-start
# has been observed to occasionally collide with the start half of an
# in-flight `systemctl restart`, leaving the unit inactive instead of
# active (not failed/hung -- a second restart recovers it). Tried and
# rejected: --job-mode=ignore-dependencies (still collided), deferring via
# a timer and re-checking is-active at fire time (a stale timer from a
# prior restart can fire mid-transition of a later one and misread),
# debouncing the timer (the cancel only runs at the end of this script,
# after a stale timer may have already fired), and dropping Conflicts=
# entirely (breaks worse: TTYVHangup=yes then SIGHUPs this unit's own
# ExecStartPre if a getty is still alive on tty1, killing a fresh start,
# not just a restart -- confirmed on hardware, reverted). Left open.
sudo -n /bin/systemctl --no-block start getty@tty1.service >/dev/null 2>&1 || true
