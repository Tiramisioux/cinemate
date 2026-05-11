#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_HOST="${PI_HOST:-pi@cinepi.local}"
PI_SUDO_PASSWORD="${PI_SUDO_PASSWORD:-${PI_PASSWORD:-}}"
DEFAULT_DEST_DIR="${BACKUP_DEST_DIR:-$HOME/Downloads/cinemate-backups}"

usage() {
  cat <<'EOF'
Usage: scripts/pi_backup_sd_to_mac.sh [dest_dir]

Runs the SD-card image backup on the Pi, compresses it with PiShrink, and copies
the resulting .img.xz back to this Mac.

Environment:
  PI_HOST           SSH target. Default: pi@cinepi.local
  PI_PASSWORD       Optional SSH password for scripts/pi_expect.exp
  PI_SUDO_PASSWORD  Optional sudo password on the Pi. Defaults to PI_PASSWORD
  BACKUP_DEST_DIR   Default local destination if dest_dir is not passed
EOF
}

if [[ $# -gt 1 ]]; then
  usage >&2
  exit 2
fi

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

DEST_DIR="${1:-$DEFAULT_DEST_DIR}"
mkdir -p "$DEST_DIR"

remote_script="$(cat <<'EOF'
set -Eeuo pipefail

ts="$(date +%F_%H-%M-%S)"
raw="/media/RAW/Cinemate_${ts}.img"
final="/media/RAW/cinemate_${ts}.img.xz"

if [[ ! -x /usr/local/bin/pishrink.sh ]]; then
  echo "Missing /usr/local/bin/pishrink.sh on the Pi." >&2
  exit 1
fi

dd if=/dev/mmcblk0 of="$raw" \
  bs=4M conv=noerror,sync,sparse status=progress

/usr/local/bin/pishrink.sh -s -v -Z -a "$raw"

mv "${raw}.xz" "$final"
rm -f "$raw"

printf '__FINAL_PATH__=%s\n' "$final"
EOF
)"

payload="$(printf '%s' "$remote_script" | base64 | tr -d '\n')"
sudo_password_b64=""

if [[ -n "$PI_SUDO_PASSWORD" ]]; then
  sudo_password_b64="$(printf '%s' "$PI_SUDO_PASSWORD" | base64 | tr -d '\n')"
fi

remote_cmd="python3 -c 'import base64, subprocess, sys; script=base64.b64decode(sys.argv[1]).decode(); password=base64.b64decode(sys.argv[2]).decode()+\"\\n\" if len(sys.argv)>2 and sys.argv[2] else None; cmd=[\"sudo\",\"-S\",\"-p\",\"\",\"bash\",\"-Eeuo\",\"pipefail\",\"-c\",script] if password is not None else [\"sudo\",\"-n\",\"bash\",\"-Eeuo\",\"pipefail\",\"-c\",script]; result=subprocess.run(cmd, input=password, text=True) if password is not None else subprocess.run(cmd); sys.exit(result.returncode)' '$payload'"

if [[ -n "$sudo_password_b64" ]]; then
  remote_cmd+=" '$sudo_password_b64'"
fi

remote_log="$(mktemp)"
cleanup() {
  rm -f "$remote_log"
}
trap cleanup EXIT

echo "Starting Pi backup on $PI_HOST"
echo "Local destination: $DEST_DIR"

if ! "$SCRIPT_DIR/pi_ssh.sh" "$remote_cmd" 2>&1 | tee "$remote_log"; then
  echo "Remote backup failed." >&2
  exit 1
fi

remote_path="$(sed -n 's/^__FINAL_PATH__=//p' "$remote_log" | tail -n 1 | tr -d '\r')"

if [[ -z "$remote_path" ]]; then
  echo "Could not determine the backup path on the Pi." >&2
  exit 1
fi

echo "Copying $remote_path to $DEST_DIR"

if [[ -n "${PI_PASSWORD:-}" ]]; then
  "$SCRIPT_DIR/pi_expect.exp" "$PI_PASSWORD" \
    scp -o StrictHostKeyChecking=accept-new \
    "${PI_HOST}:${remote_path}" \
    "$DEST_DIR/"
else
  scp -o StrictHostKeyChecking=accept-new \
    "${PI_HOST}:${remote_path}" \
    "$DEST_DIR/"
fi

local_path="$DEST_DIR/$(basename "$remote_path")"

if [[ ! -f "$local_path" ]]; then
  echo "Copy finished, but $local_path was not found locally." >&2
  exit 1
fi

echo "Local backup ready: $local_path"
