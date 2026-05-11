#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="/tmp"
INPUT_FILE="$STATE_DIR/cinemate_cli.in"
LOG_FILE="$STATE_DIR/cinemate_cli.log"
PID_FILE="$STATE_DIR/cinemate_cli.pid"

usage() {
  cat <<'EOF'
Usage:
  scripts/pi_cinemate_cli.sh start
  scripts/pi_cinemate_cli.sh send "<command>"
  scripts/pi_cinemate_cli.sh tail [lines]
  scripts/pi_cinemate_cli.sh status
  scripts/pi_cinemate_cli.sh stop
  scripts/pi_cinemate_cli.sh test-take [delay_seconds] [frames]

Requires:
  PI_PASSWORD in the environment when password auth is needed.
EOF
}

run_remote_script() {
  local script="$1"
  local encoded
  encoded="$(printf '%s' "$script" | base64 | tr -d '\n')"
  PI_PASSWORD="${PI_PASSWORD:-}" "$SCRIPT_DIR/pi_ssh.sh" "printf '%s' '$encoded' | base64 -d | bash"
}

cmd_start() {
  local script
  read -r -d '' script <<'EOF' || true
pkill -f '/home/pi/cinemate/src/main.py' || true
pkill -f 'cinepi-raw' || true
rm -f /tmp/cinemate_cli.in /tmp/cinemate_cli.log /tmp/cinemate_cli.pid
: > /tmp/cinemate_cli.in
nohup bash -lc 'tail -n0 -f /tmp/cinemate_cli.in | bash -lic cinemate' >/tmp/cinemate_cli.log 2>&1 &
echo $! >/tmp/cinemate_cli.pid
cat /tmp/cinemate_cli.pid
EOF
  run_remote_script "$script"
}

cmd_send() {
  if [[ $# -lt 1 ]]; then
    echo "send requires a command string" >&2
    exit 2
  fi
  local payload="$1"
  local quoted_payload
  printf -v quoted_payload '%q' "$payload"
  run_remote_script "printf '%s\n' $quoted_payload >> /tmp/cinemate_cli.in; echo sent"
}

cmd_tail() {
  local lines="${1:-80}"
  run_remote_script "tail -n ${lines} /tmp/cinemate_cli.log"
}

cmd_status() {
  local script
  read -r -d '' script <<'EOF' || true
if [[ -f /tmp/cinemate_cli.pid ]]; then
  pid="$(cat /tmp/cinemate_cli.pid)"
  if kill -0 "$pid" 2>/dev/null; then
    echo "running:$pid"
  else
    echo "stale:$pid"
  fi
else
  echo "stopped"
fi
EOF
  run_remote_script "$script"
}

cmd_stop() {
  local script
  read -r -d '' script <<'EOF' || true
if [[ -f /tmp/cinemate_cli.pid ]]; then
  pid="$(cat /tmp/cinemate_cli.pid)"
  kill "$pid" 2>/dev/null || true
fi
pkill -f '/home/pi/cinemate/src/main.py' || true
pkill -f 'cinepi-raw' || true
EOF
  run_remote_script "$script"
}

cmd_test_take() {
  local delay="${1:-18}"
  local frames="${2:-100}"
  local script
  read -r -d '' script <<EOF || true
pkill -f '/home/pi/cinemate/src/main.py' || true
pkill -f 'cinepi-raw' || true
rm -f /tmp/cinemate_cli.in /tmp/cinemate_cli.log /tmp/cinemate_cli.pid
: > /tmp/cinemate_cli.in
nohup bash -lc 'tail -n0 -f /tmp/cinemate_cli.in | bash -lic cinemate' >/tmp/cinemate_cli.log 2>&1 &
pid=\$!
echo "started:\$pid"
echo \$pid >/tmp/cinemate_cli.pid
sleep ${delay}
printf '%s\n' 'rec f ${frames}' >> /tmp/cinemate_cli.in
echo "sent:rec f ${frames}"
sleep 12
echo '--- status ---'
if kill -0 "\$pid" 2>/dev/null; then
  echo "running:\$pid"
else
  echo "stopped:\$pid"
fi
echo '--- recent log ---'
tail -n 200 /tmp/cinemate_cli.log
echo '--- latest takes ---'
ls -1dt /media/RAW/CINEPI_* 2>/dev/null | head -n 3
latest=\$(ls -1dt /media/RAW/CINEPI_* 2>/dev/null | head -n 1 || true)
if [[ -n "\$latest" ]]; then
  echo "--- latest files: \$latest ---"
  find "\$latest" -maxdepth 1 -type f | sort | tail -n 20
fi
EOF
  run_remote_script "$script"
}

main() {
  local subcommand="${1:-}"
  case "$subcommand" in
    start)
      shift
      cmd_start "$@"
      ;;
    send)
      shift
      cmd_send "$@"
      ;;
    tail)
      shift
      cmd_tail "$@"
      ;;
    status)
      shift
      cmd_status "$@"
      ;;
    stop)
      shift
      cmd_stop "$@"
      ;;
    test-take)
      shift
      cmd_test_take "$@"
      ;;
    *)
      usage
      exit 2
      ;;
  esac
}

main "$@"
