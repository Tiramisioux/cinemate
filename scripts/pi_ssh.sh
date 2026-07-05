#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_HOST="${PI_HOST:-pi@cinepi.local}"
SSH_OPTS=(
  -o
  StrictHostKeyChecking=accept-new
)

if [[ $# -eq 0 ]]; then
  if [[ -n "${PI_PASSWORD:-}" ]]; then
    exec "$SCRIPT_DIR/pi_expect.exp" "$PI_PASSWORD" ssh "${SSH_OPTS[@]}" "$PI_HOST"
  fi
  exec ssh "${SSH_OPTS[@]}" "$PI_HOST"
fi

if [[ -n "${PI_PASSWORD:-}" ]]; then
  exec "$SCRIPT_DIR/pi_expect.exp" "$PI_PASSWORD" ssh "${SSH_OPTS[@]}" "$PI_HOST" "$@"
fi

exec ssh "${SSH_OPTS[@]}" "$PI_HOST" "$@"
