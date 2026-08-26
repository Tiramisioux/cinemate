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
# cinemate-autostart.service declares Conflicts=getty@tty1.service. In
# systemd's default job mode ("replace") a getty start request is allowed to
# reverse an already-queued start job for the conflicting unit -- so during a
# `systemctl restart` this line could cancel the restart's own start half.
# The unit then settled inactive/dead with Result=success (not failed), which
# means Restart= never fired and nothing retried it: observed dead for 15+ s
# with no self-recovery until a human re-issued the restart.
#
# --job-mode=fail makes systemd refuse exactly that reversal: if a start job
# for a conflicting unit is already pending, this request fails instead of
# cancelling it. During a restart the getty start is skipped (harmless --
# cinemate reclaims tty1 seconds later anyway); during a plain stop there is
# no pending start job, so getty starts as before.
#
# Previously tried and rejected: --job-mode=ignore-dependencies (a different
# mode -- it relaxes ordering, not conflict reversal, so it still collided),
# deferring via a timer and re-checking is-active at fire time (a stale timer
# from a prior restart can fire mid-transition of a later one and misread),
# debouncing the timer (the cancel only runs at the end of this script, after
# a stale timer may have already fired), and dropping Conflicts= entirely
# (breaks worse: TTYVHangup=yes then SIGHUPs this unit's own ExecStartPre if
# a getty is still alive on tty1, killing a fresh start, not just a restart
# -- confirmed on hardware, reverted).
sudo -n /bin/systemctl --no-block --job-mode=fail start getty@tty1.service >/dev/null 2>&1 || true
