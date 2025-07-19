# Backing up the SD card

Create a compressed image:

```shell
sudo dd if=/dev/mmcblk0 bs=4M conv=sparse,noerror status=progress | \ gzip -c > /media/RAW/cinemate_$(date +"%Y%m%d_%H%M%S").img.gz
```

Or use PiShrink for a smaller file:

```shell
sudo bash -Eeuo pipefail -c 'ts=$(date +%F_%H%M%S); raw="/media/RAW/cinemate_${ts}.img"; out="/media/RAW/cinemate_${ts}.img"; dd if=/dev/mmcblk0 of="$raw" bs=4M conv=noerror,sync,sparse status=progress && /usr/local/bin/pishrink.sh -s -v -Z -a "$raw" "$out" && rm -f "$raw"'

```