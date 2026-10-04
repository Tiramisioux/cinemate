#!/usr/bin/env bash
# Is cef168.ko installed for a kernel? Exit 0 = yes, 1 = no.
#
# Usage: cef168-module-installed.sh [-v] [kernel-release]
#   -v   also print the module path (relative to /lib/modules/<release>)
#   kernel-release defaults to the running kernel (uname -r).
#
# Why it exists: the CEF168 overlay must only be enabled when this module is
# installed. Overlay without module means the sensor driver waits forever for
# a lens driver that never loads, and the camera never registers. The
# installer and CineMate's own overlay enabling both ask this question, so the
# answer lives here once.
#
# The check, exactly (a Python caller should do the same, no subprocess):
#   1. Read /lib/modules/<release>/modules.dep, the index depmod writes.
#   2. Find the line whose module path ends in cef168.ko, cef168.ko.xz,
#      cef168.ko.zst or cef168.ko.gz. The path is the text before the ":".
#   3. Installed only if that file exists under /lib/modules/<release>/.
# modules.dep (one file, a few thousand lines) rather than find or modinfo:
# it is cheap, it works without modinfo on PATH (not on PATH for user pi), and
# it covers every install route, DKMS (updates/dkms/) and Pinefeat's own
# `make install` (kernel/drivers/media/i2c/) alike. It also proves depmod ran,
# which is what lets the kernel autoload the module when the overlay's
# pinefeat,cef168 node appears.
#
# CEF168_MODULES_ROOT overrides /lib/modules (tests only).

set -u

print_path=0
if [[ "${1:-}" == "-v" ]]; then
    print_path=1
    shift
fi

release="${1:-$(uname -r)}"
base="${CEF168_MODULES_ROOT:-/lib/modules}/$release"

[[ -r "$base/modules.dep" ]] || exit 1

rel_path="$(awk -F: '{
    name = $1
    sub(/.*\//, "", name)
    if (name ~ /^cef168\.ko(\.(xz|zst|gz))?$/) { print $1; exit }
}' "$base/modules.dep")"

[[ -n "$rel_path" && -f "$base/$rel_path" ]] || exit 1

if ((print_path)); then
    printf '%s\n' "$rel_path"
fi
exit 0
