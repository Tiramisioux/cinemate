"""The playback decoder reads DNG tags the camera never writes down.

Two things here are inference, not transcription, and both would fail silently
if they drifted:

  - `scale` is a linear divisor. It has already been wrong once: because
    collapsing a 2x2 Bayer cell to one pixel halves both dimensions on its own,
    an earlier version produced half width for `scale=4`, so every size label in
    the UI was one step off. A wrong preview size does not raise, it just looks
    plausible, which is exactly the failure this pins.
  - HDR is not recorded anywhere. `describe_mode` infers it from WhiteLevel,
    which works only because under a LinearizationTable the level tags describe
    the table's linear output rather than the stored codes. If cinepi-raw ever
    writes levels in the stored-code domain instead, ClearHDR takes start
    reading as SDR and nothing else notices.

The fixtures are synthesised rather than checked in: the point is to pin the
tag-reading contract, and a handful of bytes states that contract far more
legibly than a binary blob would. The layout mirrors what dng_encoder.cpp
actually emits -- little-endian, single uncompressed strip at offset 8, IFD at
the tail.
"""

import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# dng_preview itself needs neither redis nor flask; the package __init__ does.
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.app import dng_preview  # noqa: E402

SHORT, LONG, RATIONAL = 3, 4, 5


def build_dng(path, width=64, height=32, bits=12, white=None, black=200,
              cfa=(0, 1, 1, 2), linearization=None, frame_rate=25.0,
              photometric=32803, fill=0x400):
    """Write a minimal DNG in the shape cinepi-raw emits."""
    if white is None:
        white = (1 << bits) - 1

    row_bytes = width * 3 // 2 if bits == 12 else width * 2
    if bits == 12:
        # TIFF MSB-first: two pixels per three bytes.
        pair = bytes(((fill >> 4) & 0xFF,
                      ((fill & 0x0F) << 4) | ((fill >> 8) & 0x0F),
                      fill & 0xFF))
        row = (pair * (width // 2))[:row_bytes]
    else:
        row = struct.pack("<H", fill) * width
    strip = row * height

    entries = []          # (tag, type, count, value_or_offset, inline_bytes)
    extra = bytearray()   # values too big to inline
    ifd_offset = 8 + len(strip)

    def add(tag, typ, count, packed):
        nonlocal extra
        if len(packed) <= 4:
            entries.append((tag, typ, count, packed.ljust(4, b"\0")))
        else:
            # Out-of-line values sit after the IFD; the IFD's own size is
            # 2 + 12*n + 4, and n is known only once every entry is queued, so
            # offsets are patched below.
            entries.append((tag, typ, count, ("EXTRA", len(extra))))
            extra += packed

    add(256, LONG, 1, struct.pack("<I", width))
    add(257, LONG, 1, struct.pack("<I", height))
    add(258, SHORT, 1, struct.pack("<H", bits))
    add(259, SHORT, 1, struct.pack("<H", 1))          # uncompressed
    add(262, SHORT, 1, struct.pack("<H", photometric))
    add(273, LONG, 1, struct.pack("<I", 8))           # StripOffsets
    add(277, SHORT, 1, struct.pack("<H", 1))
    add(279, LONG, 1, struct.pack("<I", len(strip)))
    add(272, 2, 7, b"imx585\0")
    if cfa is not None:
        add(33422, 1, 4, bytes(cfa))
    if linearization is not None:
        add(50712, SHORT, len(linearization),
            b"".join(struct.pack("<H", v) for v in linearization))
    add(50714, RATIONAL, 4, b"".join(struct.pack("<II", black, 1) for _ in range(4)))
    add(50717, SHORT, 1, struct.pack("<H", min(white, 0xFFFF)))
    add(51044, 10, 1, struct.pack("<ii", int(round(frame_rate * 1000)), 1000))

    entries.sort(key=lambda e: e[0])
    ifd_size = 2 + 12 * len(entries) + 4
    extra_base = ifd_offset + ifd_size

    out = bytearray()
    out += b"II" + struct.pack("<HI", 42, ifd_offset)
    out += strip
    out += struct.pack("<H", len(entries))
    for tag, typ, count, value in entries:
        if isinstance(value, tuple):
            value = struct.pack("<I", extra_base + value[1])
        out += struct.pack("<HHI", tag, typ, count) + value
    out += struct.pack("<I", 0)
    out += extra

    Path(path).write_bytes(bytes(out))
    return path


class DngPreviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_metadata_reads_without_touching_pixels(self):
        p = build_dng(self.dir / "a.dng", width=64, height=32, bits=12)
        meta = dng_preview.read_metadata(p)
        self.assertEqual((meta["width"], meta["height"]), (64, 32))
        self.assertEqual(meta["bits"], 12)
        self.assertEqual(dng_preview.frame_rate(meta), 25.0)

    def test_frame_rate_survives_fractional_rates(self):
        p = build_dng(self.dir / "b.dng", frame_rate=23.976)
        self.assertEqual(dng_preview.frame_rate(dng_preview.read_metadata(p)), 23.976)

    def test_scale_is_a_linear_divisor(self):
        """scale=2 halves each dimension, 4 quarters it, 8 an eighth."""
        p = build_dng(self.dir / "c.dng", width=128, height=64, bits=12)
        meta = dng_preview.read_metadata(p)
        for scale, expected in ((2, (64, 32)), (4, (32, 16)), (8, (16, 8))):
            _, size = dng_preview.decode_frame(p, meta, scale=scale)
            self.assertEqual(size, expected, f"scale={scale}")
            self.assertEqual(dng_preview.output_size(meta, scale), expected)

    def test_scale_below_a_bayer_cell_is_refused(self):
        p = build_dng(self.dir / "d.dng")
        for bad in (1, 3, 0):
            with self.assertRaises(ValueError):
                dng_preview.decode_frame(p, None, scale=bad)

    def test_sixteen_bit_frames_decode(self):
        p = build_dng(self.dir / "e.dng", width=64, height=32, bits=16,
                      white=65535, black=3200, fill=30000)
        data, size = dng_preview.decode_frame(p, None, scale=2)
        self.assertEqual(size, (32, 16))
        self.assertEqual(data[:2], b"\xff\xd8")

    def test_mode_inference_across_the_modes_cinepi_writes(self):
        sdr = build_dng(self.dir / "sdr.dng", bits=12, white=4095, black=200)
        hdr16 = build_dng(self.dir / "hdr16.dng", bits=16, white=65535, black=3200)
        # 12-bit ClearHDR: companded codes plus a table whose output is the
        # linear domain, so WhiteLevel is far above the 12-bit code ceiling.
        lut = [min(65535, i * 16) for i in range(4096)]
        hdr12 = build_dng(self.dir / "hdr12.dng", bits=12, white=63265,
                          black=200, linearization=lut)

        self.assertEqual(dng_preview.describe_mode(dng_preview.read_metadata(sdr)),
                         (False, "linear", "SDR"))
        self.assertEqual(dng_preview.describe_mode(dng_preview.read_metadata(hdr16)),
                         (True, "linear", "HDR"))
        self.assertEqual(dng_preview.describe_mode(dng_preview.read_metadata(hdr12)),
                         (True, "companded", "HDR"))

    def test_mono_forces_greyscale_because_the_file_cannot_say(self):
        """cinepi-raw tags a colour CFA even on a mono sensor."""
        p = build_dng(self.dir / "m.dng", width=64, height=32)
        colour, _ = dng_preview.decode_frame(p, None, scale=2, mono=False)
        mono, _ = dng_preview.decode_frame(p, None, scale=2, mono=True)
        self.assertNotEqual(colour, mono)

    def test_a_non_dng_is_refused_rather_than_misread(self):
        junk = self.dir / "junk.bin"
        junk.write_bytes(b"not a tiff at all, not even close")
        with self.assertRaises(dng_preview.DngError):
            dng_preview.read_metadata(junk)

    def test_truncated_frame_is_refused(self):
        p = build_dng(self.dir / "t.dng", width=64, height=32)
        meta = dng_preview.read_metadata(p)
        data = Path(p).read_bytes()
        Path(p).write_bytes(data[:100])
        with self.assertRaises(dng_preview.DngError):
            dng_preview.decode_frame(p, meta, scale=2)


if __name__ == "__main__":
    unittest.main()
