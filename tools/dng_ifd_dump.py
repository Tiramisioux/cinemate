#!/usr/bin/env python3
"""Walk the IFD chain of a cinepi-raw DNG and report where its bytes go.

For each file: total size, the sum of every IFD's strip bytes, the residual
overhead (TIFF header + IFDs + out-of-line tag payloads such as a
LinearizationTable), and one line per IFD with dimensions, bit depth,
samples per pixel, photometric interpretation, compression and strip size.
A second IFD (IFD1, SubfileType 1) is cinepi-raw's embedded thumbnail; its
strip size is the per-frame cost of that thumbnail. Compression 7 (thumbnail
mode 3, colour JPEG) is called out as "JPEG" rather than left as a bare
number, and -- only when Pillow happens to be importable -- the strip is
decoded as a self-check that it actually IS a valid JPEG at the dimensions
IFD1 claims, printing Pillow's own size/mode rather than trusting the tags.

Independent of cinemate's own reader (src/module/app/dng_preview.py) on
purpose: it is a check on what the encoder wrote, not on what the pane reads.
Standard library only for the IFD walk itself -- Pillow is optional and only
used for the JPEG self-check above, imported lazily so its absence does not
stop the walk. Cross-check with `exiftool -a -G1 <file>`.

Usage:
    python3 dng_ifd_dump.py <file.dng> [<file.dng> ...]
"""
import os
import struct
import sys

TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}

TAG_SUBFILE, TAG_WIDTH, TAG_HEIGHT, TAG_BITS = 254, 256, 257, 258
TAG_COMPRESSION, TAG_PHOTOMETRIC, TAG_MODEL, TAG_SPP = 259, 262, 272, 277
TAG_STRIP_OFFSET, TAG_STRIP_BYTES = 273, 279
TAG_SOFTWARE, TAG_UCM, TAG_LIN_TABLE = 305, 0xC614, 0xC618
COMPRESSION_JPEG = 7


def _read_ascii(handle, offset, count):
    handle.seek(offset)
    return handle.read(count).rstrip(b"\0").decode("ascii", "replace")


def _jpeg_self_check(handle, offset, length, claimed_width, claimed_height):
    """Decode a thumbnail strip Pillow's own way, as a check independent of
    trusting IFD1's own width/height/compression tags -- the same
    independent-of-the-encoder spirit as this whole script, one level
    deeper. Never raises: a corrupt strip is exactly the thing this is
    looking for, so it is reported, not propagated.
    """
    if not offset or not length:
        return "    JPEG self-check: skipped (no strip offset/length)"
    try:
        from PIL import Image
    except ImportError:
        return "    JPEG self-check: skipped (Pillow not installed)"
    try:
        import io
        handle.seek(offset)
        data = handle.read(length)
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            decoded = f"{img.width}x{img.height} mode={img.format}/{img.mode}"
    except Exception as exc:  # noqa: BLE001 -- report any decode failure, don't crash the dump
        return f"    JPEG self-check: FAILED to decode ({exc})"
    match = "OK" if (claimed_width, claimed_height) == (img.width, img.height) else "MISMATCH"
    return (f"    JPEG self-check: Pillow decoded {decoded}, IFD1 claims "
            f"{claimed_width}x{claimed_height} -- {match}")


def dump(path):
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        header = handle.read(8)
        if header[:2] != b"II":
            print(f"{path}: not a little-endian TIFF")
            return
        next_ifd = struct.unpack("<I", header[4:8])[0]
        index = 0
        strips_total = 0
        raw_strip = 0
        thumb_strip = 0
        lines = []
        while next_ifd and index < 8:
            handle.seek(next_ifd)
            count = struct.unpack("<H", handle.read(2))[0]
            entries = {}
            for _ in range(count):
                tag, typ, cnt, val = struct.unpack("<HHII", handle.read(12))
                entries[tag] = (typ, cnt, val)
            following = struct.unpack("<I", handle.read(4))[0]

            def get(tag):
                entry = entries.get(tag)
                if not entry:
                    return None
                typ, cnt, val = entry
                if typ == 3 and cnt == 1:
                    return val & 0xFFFF
                if typ == 2:
                    if cnt <= 4:
                        return struct.pack("<I", val)[:cnt].rstrip(b"\0").decode()
                    return _read_ascii(handle, val, cnt)
                return val

            bits = entries.get(TAG_BITS)
            if bits and bits[1] == 1:
                bits_text = str(bits[2] & 0xFFFF)
            elif bits:
                bits_text = f"{bits[1]}x8"
            else:
                bits_text = "?"
            strip = get(TAG_STRIP_BYTES) or 0
            strips_total += strip
            if index == 0:
                raw_strip = strip
            elif get(TAG_SUBFILE) == 1:
                thumb_strip += strip
            lin = entries.get(TAG_LIN_TABLE)
            lin_text = f"LinearizationTable {lin[1]} entries ({lin[1] * 2} B)" if lin else "no LinearizationTable"
            compression = get(TAG_COMPRESSION)
            compression_text = f"{compression} (JPEG)" if compression == COMPRESSION_JPEG else f"{compression}"
            line = (f"  IFD{index}: subfile={get(TAG_SUBFILE)} {get(TAG_WIDTH)}x{get(TAG_HEIGHT)} "
                    f"bits={bits_text} spp={get(TAG_SPP)} photometric={get(TAG_PHOTOMETRIC)} "
                    f"compression={compression_text} strip={strip:,} B  {lin_text}")
            if index == 0:
                line += f"  model='{get(TAG_MODEL)}' software='{get(TAG_SOFTWARE)}' ucm='{get(TAG_UCM)}'"
            lines.append(line)
            if compression == COMPRESSION_JPEG:
                lines.append(_jpeg_self_check(handle, get(TAG_STRIP_OFFSET), strip,
                                               get(TAG_WIDTH), get(TAG_HEIGHT)))
            next_ifd = following
            index += 1

    overhead = size - strips_total
    print(f"{os.path.basename(path)}  size={size:,} B ({size / 1048576:.2f} MiB)  "
          f"strips={strips_total:,} B  overhead={overhead:,} B  ifds={index}")
    for line in lines:
        print(line)
    if thumb_strip and raw_strip:
        print(f"  thumbnail adds {thumb_strip:,} B = {100.0 * thumb_strip / raw_strip:.1f}% of the raw strip")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    for arg in sys.argv[1:]:
        dump(arg)
