# S04 Agent 2 — services/, _test/, installer, config, build

**Scope:** `services/`, `_test/`, `cinemate-install.sh`, `cinemate-update.sh`,
`settings.jsonc`, `settings.schema.json`, `Makefile`, `CMakeLists.txt`,
`scripts/`, `resources/`.
**ID block:** F-150..F-199.
**Method:** static read only. No Raspberry Pi available — anything requiring
hardware or a live systemd is marked `unverified` with the test that would settle it.

All line citations were produced by `grep -n` / `rg -n` and re-grepped before
being written. Counts derived from pattern matching are stated as "at least N".

---

## Findings table

| ID | severity | confidence | repo | category | summary | evidence |
|---|---|---|---|---|---|---|
| F-150 | medium | confirmed | cinemate | dead-code | `_test/_wifi_hotspot_service.py` is a superseded standalone hotspot daemon with hardcoded creds `cinepi`/`11111111`, contradicting the live credential ladder | `_test/_wifi_hotspot_service.py:6,33` |
| F-151 | medium | confirmed | cinemate | redundancy | `_test/_gpio_output.py` (190 LOC) and `_test/__gpio_output.py` (16 LOC) are two stale forks of the live `src/module/gpio_output.py` (203 LOC); 346 diff lines vs live | `_test/_gpio_output.py:93`, `src/module/gpio_output.py` |
| F-152 | medium | confirmed | cinemate | redundancy | `_test/_mediator.py` is a stale fork of `src/module/mediator.py`, diverged by 112 diff lines | `_test/_mediator.py:7`, `src/module/mediator.py:7` |
| F-153 | low | confirmed | cinemate | dead-code | `_test/automount.py` is a vestigial I2C-button/LED automount unrelated to the live `services/storage-automount/`; imports `smbus`+`RPi.GPIO`+`psutil`, zero inbound refs | `_test/automount.py:1-6,120` |
| F-154 | low | confirmed | cinemate | dead-code | `_test/analyze_logs.py` hardcodes `/home/pi/cinemate/src/logs/system.log`, never imported or invoked by anything | `_test/analyze_logs.py:129` |
| F-155 | high | confirmed | cinemate | redundancy | `YANK_ERRNOS` set is defined byte-identically twice, in the service and in the app, with no shared module | `services/storage-automount/storage-automount.py:76-82`, `src/module/ssd_monitor.py:46-52` |
| F-156 | high | confirmed | cinemate | redundancy | Filesystem→mount-options table duplicated across the two processes that both mount `/media/RAW`, and the two copies disagree | `src/module/ssd_monitor.py:599-604`, `services/storage-automount/storage-automount.py:140-144,322-328` |
| F-157 | medium | confirmed | cinemate | redundancy | The ext4 option string `rw,noatime,nodiratime,commit=60` is stated 5x: once in `ssd_monitor` and 4x in the automount `PROFILES` table | `src/module/ssd_monitor.py:45`, `services/storage-automount/storage-automount.py:89,98,107,120` |
| F-158 | medium | confirmed | cinemate | redundancy | Two independent device-classification implementations with incompatible taxonomies (`cfe_nvme/usb_nvme/usb_ssd/nvme_hat/other` vs `SSD/CFE/NVMe/Unknown`) | `services/storage-automount/storage-automount.py:217-243`, `src/module/ssd_monitor.py:463-500` |
| F-159 | medium | confirmed | cinemate | redundancy | Partition→root-block-device derivation duplicated (helper in the service, inline in the app) | `services/storage-automount/storage-automount.py:173-178`, `src/module/ssd_monitor.py:474-481` |
| F-160 | high | probable | cinemate | structure | Two processes independently mount, fsck and unmount `/media/RAW` with no lock or ownership protocol between them | `services/storage-automount/storage-automount.py:393,492,363`, `src/module/ssd_monitor.py:639,784,527` |
| F-161 | high | confirmed | cinemate | dead-code | `services/cinemate-services.Makefile` recurses into `ssd-automount`, `nvme-automount`, `cfe-hat-automount` — all three directories were deleted; the file has zero inbound references and cannot run | `services/cinemate-services.Makefile:4-6,9-11` |
| F-162 | low | confirmed | cinemate | dead-code | `services/Makefile` declares `uninstall` and `uninstall-<svc>` as `.PHONY` but generates no recipe for either; `make -C services uninstall` silently does nothing | `services/Makefile:6,15,28,36-44` |
| F-163 | medium | confirmed | install | install-drift | `python3-systemd` is installed but only reachable through `SSDMonitor._journal_loop`, whose only caller is a commented-out block — confirms the F-109 corollary; add to the F-032 unused-package list (now 8 of 11) | `cinemate-install.sh:523`, `src/module/ssd_monitor.py:14,139-144,1254` |
| F-164 | medium | confirmed | cinemate | dead-code | The intended coupling between the automount service and the app is a dead journal tail of `journalctl -fu storage-automount`; with it disabled the app re-implements mount detection by polling — this is the root cause of F-155..F-160 | `src/module/ssd_monitor.py:139-144,1316` |
| F-165 | medium | confirmed | cinemate | dead-code | Root `CMakeLists.txt` `add_subdirectory(src/module/audio_sync)` — that directory does not exist, so `cmake .` fails immediately; nothing in the installer or update script invokes cmake on the repo root | `CMakeLists.txt:4` |
