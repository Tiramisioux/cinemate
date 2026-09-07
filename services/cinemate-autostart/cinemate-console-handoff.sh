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

cinemate_is_coming_back() {
    local unit job_type

    while read -r _job_id unit job_type _rest; do
        [[ "${unit:-}" == "cinemate-autostart.service" ]] || continue
        [[ "${job_type:-}" == "start" || "${job_type:-}" == "restart" ]] || continue
        return 0
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
# --job-mode=fail is necessary but NOT sufficient, and the gap is what made a
# restart land at a shell prompt. It refuses only while a start job for the
# conflicting unit is still PENDING. During a restart this ExecStopPost can
# run after the start half has already COMPLETED, and then there is no pending
# job left to refuse: the getty start succeeds, Conflicts=getty@tty1.service
# resolves the other way, and systemd stops the instance it has just started.
#
# Straight off the rig (journalctl -u cinemate-autostart), all inside one
# second, with the service fully up -- "Initialization Complete", Flask
# serving:
#
#   systemd[1]: Started cinemate-autostart.service
#   sudo[5736]: root : COMMAND=/bin/systemctl --job-mode=fail start getty@tty1
#   systemd[1]: cinemate-autostart.service: Deactivated successfully.
#   systemd[1]: Stopped cinemate-autostart.service
#
# Deactivated *successfully* -- not a crash, not the camera gate, not a
# SIGHUP. The conflict did exactly what it is defined to do; this script asked
# for it a moment too late. Hence the state check: if CineMate is already back
# (or on its way), the console is not ours to take.
state="$(/bin/systemctl is-active cinemate-autostart.service 2>/dev/null || true)"
if [[ "${state}" == "active" || "${state}" == "activating" || "${state}" == "reloading" ]]; then
    exit 0
fi

# The state check above is necessary but still not sufficient, and this is
# the half that made "restart lands at a shell prompt" survive two fixes.
#
# It reads the present. During a restart the present looks exactly like a
# stop: the unit is "deactivating" either way, so the request goes through --
# correctly, on the evidence available. What it cannot see is that the getty
# start it is about to ask for will not be RUN for another six seconds.
# cinemate-autostart declares Before=getty@tty1.service, so systemd parks the
# getty's start job behind this unit's own start job and releases it the
# instant that start completes -- into a fully-up CineMate, which
# Conflicts=getty@tty1.service then stops. Off the rig, pressing "Restart
# Cinemate" in the settings editor:
#
#   02:53:47.995  Stopping cinemate-autostart.service...
#   02:53:50.082  sudo[22890]: root : COMMAND=/bin/systemctl ... start getty@tty1
#   02:53:50.092  Starting cinemate-autostart.service...
#   02:53:55.898  Started cinemate-autostart.service       <- fully up
#   02:53:55.916  Started getty@tty1.service               <- +18 ms
#   02:53:55.978  cinemate-autostart.service: Deactivated successfully.
#
# Measured four times: 18, 23, 29 and 30 ms after CineMate's own "Started".
# That is also why "starting it again works" -- the second time there is no
# parked getty job left over from a stop.
#
# --job-mode=fail does not cover it either. It refuses only while a start job
# for the conflicting unit is already pending, and systemd does not enqueue a
# restart's start half until the stop has finished, so at this point there is
# nothing pending for it to refuse.
#
# The job queue, though, says it outright. This script's own probe, during a
# restart, at exactly this line:
#
#   PROBE is-active=deactivating
#   PROBE job: 7216 cinemate-autostart.service restart running
#
# So ask the queue rather than the state. A queued start or restart means
# CineMate is coming back and the console is not ours to take. A plain stop
# queues no such job and the getty comes back as before -- which is this
# script's whole reason to exist.
#
# Tried and rejected before this: doing the same check on the way up, from an
# ExecStartPost that cancels the parked job. It works on paper -- Before=
# guarantees the job is still cancellable there -- and it kills CineMate dead
# on the rig. This unit sets StandardInput=tty-force with TTYVHangup=yes, so
# systemd hangs up /dev/tty1 for *every* Exec command in it; an ExecStartPost
# runs while main.py is alive and owns that tty, and main.py takes the SIGHUP.
# ExecStartPost=/bin/true is enough to do it: Duration 23ms, main PID killed
# by signal HUP. ExecStartPre and ExecStopPost are safe only because main.py
# is not running yet, or not any more.
if cinemate_is_coming_back; then
    exit 0
fi

sudo -n /bin/systemctl --no-block --job-mode=fail start getty@tty1.service >/dev/null 2>&1 || true
