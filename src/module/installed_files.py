"""Drift between the repo's system files and their installed copies.

`git pull` on the Pi updates the repo working tree. It does **not** update
`/etc/systemd/system/cinemate-autostart.service` or the helpers under
`/usr/local/bin/` -- those are *copied* into place by `sudo make install`
(see the root `Makefile`'s `install` target), which the installer runs and a
plain pull does not.

That gap is silent and open-ended: a unit-file change can sit in the repo,
unread by systemd, for as long as the operator keeps updating by pulling. It
bit C3.4, whose entire mechanism is one character -- the leading `-` on
`ExecStartPre=-/usr/local/bin/camera-ready.sh` that makes the camera-ready
gate advisory. Without the copy step an existing Pi keeps the strict gate:
no camera, the gate exits 1, systemd fails the unit *before* main.py ever
runs, and the operator gets a bare terminal on tty1 with no CineMate error
to explain it -- because CineMate never started.

This module only *reports*. CineMate must never `sudo` anything on the
operator's behalf; the warning names the remedy and the operator runs it.
"""

import filecmp
import logging
import os
from collections import namedtuple


# (path inside the repo, path it is installed to). Mirrors the root
# Makefile's `install` target -- keep the two in step.
INSTALLED_FILES = (
    ("services/cinemate-autostart/cinemate-autostart.service",
     "/etc/systemd/system/cinemate-autostart.service"),
    ("services/cinemate-autostart/camera-ready.sh",
     "/usr/local/bin/camera-ready.sh"),
    ("services/cinemate-autostart/cinemate-startup-failure-display.sh",
     "/usr/local/bin/cinemate-startup-failure-display.sh"),
    ("services/cinemate-autostart/cinemate-console-handoff.sh",
     "/usr/local/bin/cinemate-console-handoff.sh"),
    ("services/cinemate-autostart/cinemate-startup-failure.sh",
     "/etc/profile.d/cinemate-startup-failure.sh"),
)

REMEDY = "cd {repo_root} && sudo make install && sudo systemctl daemon-reload"

# If this isn't present, `make install` has never run on this machine: the
# operator is running CineMate manually, or installed with autostart
# disabled. Nothing has drifted -- there is nothing to drift from -- and
# warning about all five files every boot would be a standing false alarm.
INSTALL_SENTINEL = "/etc/systemd/system/cinemate-autostart.service"

DriftedFile = namedtuple("DriftedFile", "repo_path installed_path reason")


def find_installed_file_drift(repo_root, pairs=INSTALLED_FILES):
    """Return a DriftedFile per installed copy that is missing or stale.

    Silent about anything it cannot judge: a repo file that doesn't exist
    (a partial checkout, or this running from somewhere unexpected) and an
    installed path it cannot read (no permission, or a system that installs
    elsewhere) are both skipped rather than reported as drift.
    """
    if pairs is INSTALLED_FILES and not os.path.exists(INSTALL_SENTINEL):
        logging.debug(
            "%s is not present -- CineMate is not installed as a service here, "
            "skipping the installed-file drift check.", INSTALL_SENTINEL,
        )
        return []

    drifted = []
    for relative_path, installed_path in pairs:
        repo_path = os.path.join(str(repo_root), relative_path)
        if not os.path.isfile(repo_path):
            continue
        try:
            if not os.path.exists(installed_path):
                drifted.append(DriftedFile(repo_path, installed_path, "not installed"))
                continue
            if not filecmp.cmp(repo_path, installed_path, shallow=False):
                drifted.append(
                    DriftedFile(repo_path, installed_path, "differs from the repo copy")
                )
        except OSError as exc:
            logging.debug(
                "Could not compare %s with %s: %s", repo_path, installed_path, exc
            )
    return drifted


def log_installed_file_drift(repo_root, pairs=INSTALLED_FILES):
    """Warn about every stale installed copy, naming the exact remedy."""
    drifted = find_installed_file_drift(repo_root, pairs=pairs)
    if not drifted:
        return drifted

    logging.warning(
        "%s installed system file(s) are out of date with this checkout. "
        "`git pull` does not copy them -- run:  %s",
        len(drifted),
        REMEDY.format(repo_root=repo_root),
    )
    for entry in drifted:
        logging.warning(
            "  %s: %s (repo copy: %s)",
            entry.installed_path, entry.reason, entry.repo_path,
        )
    return drifted
