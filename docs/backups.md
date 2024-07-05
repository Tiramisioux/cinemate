# Backing Up the SD Card

To make a compressed image backup of the SD card onto the SSD:

    sudo dd if=/dev/mmcblk0 bs=1M status=progress | xz -c > /media/RAW/cinepi_cinemate_raspbian_image_$(date +%Y-%m-%d_%H-%M-%S).img.xz

Backing up an 8 GB CineMate image takes about 2 hours.
