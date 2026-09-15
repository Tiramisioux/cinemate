#!/usr/bin/env bash
# Mac-side driver for scripts/make-release-image.sh.
#
# Same shape as pi_backup_sd_to_mac.sh, with one difference worth knowing: the
# work is not embedded here. make-release-image.sh lives in the repository and
# is therefore already on the Pi, so this script only invokes it and fetches
# the result. Keeping the logic in one place on the Pi is what lets the same
# procedure be run by hand over SSH when something needs watching.
#
# That does mean the Pi's checkout has to contain the script -- git pull there
# first after this lands.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_HOST="${PI_HOST:-pi@cinepi.local}"
PI_SUDO_PASSWORD="${PI_SUDO_PASSWORD:-${PI_PASSWORD:-}}"
PI_CINEMATE_DIR="${PI_CINEMATE_DIR:-/home/pi/cinemate}"
DEFAULT_DEST_DIR="${RELEASE_DEST_DIR:-$HOME/Downloads/cinemate-releases}"

usage() {
  cat <<'EOF'
Usage: scripts/pi_release_image_to_mac.sh [--dry-run] [dest_dir]

Runs scripts/make-release-image.sh on the Pi -- which swaps settings.jsonc and
config.txt to stock, images the card, and puts both files back -- then copies
the resulting .img.xz and its manifest to this Mac.

Switch the repositories to whichever branch you want to ship before running
this; the script does not touch branches.

Options:
  --dry-run   Run the Pi script's --dry-run: the full swap and restore, without
              the hour of dd and xz. Nothing is copied back.

Environment:
  PI_HOST           SSH target. Default: pi@cinepi.local
  PI_PASSWORD       Optional SSH password for scripts/pi_expect.exp
  PI_SUDO_PASSWORD  Optional sudo password on the Pi. Defaults to PI_PASSWORD
  PI_CINEMATE_DIR   Repository path on the Pi. Default: /home/pi/cinemate
  RELEASE_DEST_DIR  Default local destination if dest_dir is not passed
EOF
}

DRY_RUN=0
DEST_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)  DRY_RUN=1 ;;
    -h|--help)  usage; exit 0 ;;
    -*)         usage >&2; exit 2 ;;
    *)
      [[ -z "$DEST_DIR" ]] || { usage >&2; exit 2; }
      DEST_DIR="$1"
      ;;
  esac
  shift
done

DEST_DIR="${DEST_DIR:-$DEFAULT_DEST_DIR}"

remote_args=""
if (( DRY_RUN )); then
  remote_args="--dry-run"
fi

# sudo over a non-interactive ssh channel: -S with the password on stdin when
# we have one, -n (fail fast, never prompt) when we do not. Same handling as
# pi_backup_sd_to_mac.sh.
remote_script="$PI_CINEMATE_DIR/scripts/make-release-image.sh $remote_args"

if [[ -n "$PI_SUDO_PASSWORD" ]]; then
  sudo_password_b64="$(printf '%s' "$PI_SUDO_PASSWORD" | base64 | tr -d '\n')"
  remote_cmd="printf '%s' '$sudo_password_b64' | base64 -d | sudo -S -p '' bash -Eeuo pipefail -c '$remote_script'"
else
  remote_cmd="sudo -n bash -Eeuo pipefail -c '$remote_script'"
fi

remote_log="$(mktemp)"
trap 'rm -f "$remote_log"' EXIT

echo "Starting release image build on $PI_HOST"
if (( DRY_RUN )); then
  echo "Dry run: the Pi will swap and restore, but not image the card."
else
  mkdir -p "$DEST_DIR"
  echo "Local destination: $DEST_DIR"
fi

if ! "$SCRIPT_DIR/pi_ssh.sh" "$remote_cmd" 2>&1 | tee "$remote_log"; then
  echo "Remote release image build failed." >&2
  echo "If it was interrupted after the swap, put your files back with:" >&2
  echo "  sudo $PI_CINEMATE_DIR/scripts/make-release-image.sh --restore-only" >&2
  exit 1
fi

if (( DRY_RUN )); then
  echo "Dry run finished."
  exit 0
fi

fetch() {
  local marker="$1" label="$2" remote_path
  remote_path="$(sed -n "s/^${marker}=//p" "$remote_log" | tail -n 1 | tr -d '\r')"

  if [[ -z "$remote_path" ]]; then
    echo "Could not determine the $label path on the Pi." >&2
    return 1
  fi

  echo "Copying $remote_path to $DEST_DIR"
  if [[ -n "${PI_PASSWORD:-}" ]]; then
    "$SCRIPT_DIR/pi_expect.exp" "$PI_PASSWORD" \
      scp -o StrictHostKeyChecking=accept-new "${PI_HOST}:${remote_path}" "$DEST_DIR/"
  else
    scp -o StrictHostKeyChecking=accept-new "${PI_HOST}:${remote_path}" "$DEST_DIR/"
  fi

  local local_path
  local_path="$DEST_DIR/$(basename "$remote_path")"
  [[ -f "$local_path" ]] || { echo "Copy finished, but $local_path was not found locally." >&2; return 1; }
  echo "Local $label ready: $local_path"
}

fetch __RELEASE_IMAGE__ image
fetch __RELEASE_MANIFEST__ manifest || echo "Manifest copy skipped." >&2
