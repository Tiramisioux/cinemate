# Remote Pi Access

This workspace can target the Raspberry Pi at `pi@cinepi.local` directly.

## Auth

- Preferred: SSH keys.
- Supported fallback: export `PI_PASSWORD` for one command/session.
- Do not store the password in tracked files.

## Helper

- Shell or single command:
  `scripts/pi_ssh.sh`
  `scripts/pi_ssh.sh hostname`
  `scripts/pi_ssh.sh "cd ~/cinepi-raw && git status --short"`
- Managed `cinemate` session:
  `scripts/pi_cinemate_cli.sh start`
  `scripts/pi_cinemate_cli.sh send "rec f 100"`
  `scripts/pi_cinemate_cli.sh tail 200`
  `scripts/pi_cinemate_cli.sh stop`

## Password-based example

```bash
PI_PASSWORD=1 scripts/pi_ssh.sh hostname
```

The wrapper uses `expect` only when `PI_PASSWORD` is set. Otherwise it uses normal `ssh`.

## Verified 100-frame take workflow

```bash
export PI_PASSWORD=1
scripts/pi_cinemate_cli.sh start
PI_PASSWORD=1 scripts/pi_ssh.sh 'for i in $(seq 1 300); do grep -q "Storage pre-roll complete" /tmp/cinemate_cli.log 2>/dev/null && exit 0; sleep 0.2; done; exit 1'
scripts/pi_cinemate_cli.sh send "rec f 100"
PI_PASSWORD=1 scripts/pi_ssh.sh 'for i in $(seq 1 300); do grep -q "Stopped recording" /tmp/cinemate_cli.log 2>/dev/null && exit 0; sleep 0.2; done; exit 1'
latest="$(PI_PASSWORD=1 scripts/pi_ssh.sh 'ls -1dt /media/RAW/CINEPI_* 2>/dev/null | head -n 1' | tail -n 1 | tr -d '\r')"
scripts/pi_expect.exp 1 scp -r -o StrictHostKeyChecking=accept-new "pi@cinepi.local:$latest" "/Users/patrikeriksson/.codex/worktrees/37e5/cinemate/pi-test-takes-speed-bench/"
scripts/pi_cinemate_cli.sh stop
```

Treat `/tmp/cinemate_cli.log` as the authoritative live transcript for helper-managed runs. If the take was started manually instead, that log may not exist.

## SD-card backup to Mac

```bash
scripts/pi_backup_sd_to_mac.sh
PI_PASSWORD=1 scripts/pi_backup_sd_to_mac.sh ~/Downloads/cinemate-backups
```

This wrapper runs the SD-card image backup on the Pi, compresses it to `/media/RAW/cinemate_YYYY-MM-DD_HH-MM-SS.img.xz`, and then copies that file back to the destination on this Mac.

If remote `sudo` needs a password, set `PI_SUDO_PASSWORD`. When present, it defaults to `PI_PASSWORD`.
