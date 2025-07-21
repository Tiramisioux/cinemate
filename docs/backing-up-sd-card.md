# Backing up the SD card

Create a compressed image:

```shell
sudo dd if=/dev/mmcblk0 bs=4M conv=sparse,noerror status=progress | \ gzip -c > /media/RAW/cinemate_$(date +"%Y%m%d_%H%M%S").img.gz
```

Or use PiShrink for a smaller file:

```shell
sudo bash -Eeuo pipefail -c '
  # Timestamp like 2025-07-19_19-38-33
  ts=$(date +%F_%H-%M-%S)

  # Paths on /media/RAW
  raw="/media/RAW/Cinemate_${ts}.img"         # working image
  final="/media/RAW/cinemate_${ts}.img.xz"    # desired end-result

  # 1 ─ Image the SD-card (pads bad blocks, keeps sparsity)
  dd if=/dev/mmcblk0 of="$raw" \
     bs=4M conv=noerror,sync,sparse status=progress

  # 2 ─ Shrink + parallel-xz compress **in place**
  /usr/local/bin/pishrink.sh -s -v -Z -a "$raw"

  # 3 ─ Rename the freshly-made .xz to the lowercase style you want
  mv "${raw}.xz" "$final"

  # 4 ─ Remove the now-unused raw image
  rm -f "$raw"
'
```

To copy the file to your desktop computer:

```shell
# From the desktop computers terminal

scp -r pi@<IP ADDRESS OF YOU PI>:/media/RAW/<COMPRESSED IMAGE FILE NAME> ~/Desktop/
```
