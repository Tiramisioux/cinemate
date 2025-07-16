# Backing up the SD card

Create a compressed image:

```shell
sudo dd if=/dev/mmcblk0 bs=4M conv=sparse,noerror status=progress | \ gzip -c > /media/RAW/Cinemate_$(date +"%Y%m%d_%H%M%S").img.gz
```

Or use PiShrink for a smaller file:

```shell
sudo bash -euo pipefail -c '
  ts=$(date +%Y%m%d_%H%M%S)
  raw="/media/RAW/Cinemate_${ts}.img"
  final="/media/RAW/Cinemate_${ts}.img.gz"
  dd if=/dev/mmcblk0 of="$raw" bs=4M conv=sparse,noerror status=progress
  pishrink.sh -v -z "$raw" "$final"
  rm -f "$raw"
'
```