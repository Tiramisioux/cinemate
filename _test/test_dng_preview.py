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

import io
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# dng_preview itself needs neither redis nor flask; the package __init__ does.
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.app import dng_preview  # noqa: E402

SHORT, LONG, RATIONAL = 3, 4, 5


def build_dng(path, width=64, height=32, bits=12, white=None, black=200,
              cfa=(0, 1, 1, 2), linearization=None, frame_rate=25.0,
              photometric=32803, fill=0x400, thumbnail=None):
    """Write a minimal DNG in the shape cinepi-raw emits.

    ``thumbnail``, when given, is a dict with ``width``, ``height``,
    ``samples_per_pixel`` (1 mono / 3 colour) and ``fill`` (one byte,
    repeated), and chains a second IFD after IFD0 -- the shape
    dng_encoder.cpp's IFD1 actually has (C9 Phase 0): NewSubfileType 1,
    the given dimensions, 8-bit, PhotometricInterpretation MINISBLACK (1)
    or RGB (2), one strip placed right after the thumbnail's own pixel
    data, chained via IFD0's next-IFD field. IFD0 itself is untouched --
    same as dng_save() leaves it whenever a thumbnail is chained after it.
    """
    if white is None:
        white = (1 << bits) - 1

    if bits == 12:
        row_bytes = width * 3 // 2
        # TIFF MSB-first: two pixels per three bytes.
        pair = bytes(((fill >> 4) & 0xFF,
                      ((fill & 0x0F) << 4) | ((fill >> 8) & 0x0F),
                      fill & 0xFF))
        row = (pair * (width // 2))[:row_bytes]
    elif bits == 10:
        row_bytes = width * 10 // 8
        # Forward of dng_pack.hpp's pack_group_10bit (4 px in 5 bytes,
        # MSB-first). Every pixel in this fixture is the same `fill`
        # value, so one group's bytes repeat for the whole row.
        p = fill & 0x3FF
        group = bytes((
            p >> 2,
            ((p << 6) | (p >> 4)) & 0xFF,
            ((p << 4) | (p >> 6)) & 0xFF,
            ((p << 2) | (p >> 8)) & 0xFF,
            p & 0xFF,
        ))
        row = group * (width // 4)
    else:
        row_bytes = width * 2
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
    next_ifd_field_pos = None
    for tag, typ, count, value in entries:
        if isinstance(value, tuple):
            value = struct.pack("<I", extra_base + value[1])
        out += struct.pack("<HHI", tag, typ, count) + value
    next_ifd_field_pos = len(out)
    out += struct.pack("<I", 0)   # patched below if `thumbnail` chains after
    out += extra

    if thumbnail is not None:
        tw = thumbnail["width"]
        th = thumbnail["height"]
        tspp = thumbnail.get("samples_per_pixel", 1)
        tfill = thumbnail.get("fill", 0x80)
        tphot = 2 if tspp == 3 else 1   # RGB : MINISBLACK, matching dng_save()

        thumb_off = len(out)
        thumb_data = bytes([tfill]) * (tw * th * tspp)
        out += thumb_data
        thumb_size = len(thumb_data)

        t_entries = []
        t_extra = bytearray()
        ifd1_offset = thumb_off + thumb_size

        def t_add(tag, typ, count, packed):
            nonlocal t_extra
            if len(packed) <= 4:
                t_entries.append((tag, typ, count, packed.ljust(4, b"\0")))
            else:
                t_entries.append((tag, typ, count, ("EXTRA", len(t_extra))))
                t_extra += packed

        t_add(254, LONG, 1, struct.pack("<I", 1))              # NewSubfileType
        t_add(256, LONG, 1, struct.pack("<I", tw))
        t_add(257, LONG, 1, struct.pack("<I", th))
        t_add(258, SHORT, tspp, b"".join(struct.pack("<H", 8) for _ in range(tspp)))
        t_add(259, SHORT, 1, struct.pack("<H", 1))              # uncompressed
        t_add(262, SHORT, 1, struct.pack("<H", tphot))
        t_add(273, LONG, 1, struct.pack("<I", thumb_off))
        t_add(277, SHORT, 1, struct.pack("<H", tspp))
        t_add(278, LONG, 1, struct.pack("<I", th))              # RowsPerStrip
        t_add(279, LONG, 1, struct.pack("<I", thumb_size))
        t_add(284, SHORT, 1, struct.pack("<H", 1))              # PlanarConfig

        t_entries.sort(key=lambda e: e[0])
        t_ifd_size = 2 + 12 * len(t_entries) + 4
        t_extra_base = ifd1_offset + t_ifd_size

        out += struct.pack("<H", len(t_entries))
        for tag, typ, count, value in t_entries:
            if isinstance(value, tuple):
                value = struct.pack("<I", t_extra_base + value[1])
            out += struct.pack("<HHI", tag, typ, count) + value
        out += struct.pack("<I", 0)   # IFD1 is the last IFD
        out += t_extra

        # Chain IFD0 -> IFD1, exactly the after-the-fact patch dng_save()
        # does once IFD1's own offset is known.
        struct.pack_into("<I", out, next_ifd_field_pos, ifd1_offset)

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

    def test_ten_bit_frames_decode(self):
        """The blocker: _load_rows raised for anything but 12/16, but
        cinepi-raw writes contiguous 10-bit for imx296's only mode,
        imx477 1332x990, imx283 modes 3-5, and every log-encoded take on a
        12-bit mode. Every 10-bit take 404'd on every frame."""
        p = build_dng(self.dir / "f.dng", width=64, height=32, bits=10,
                      white=1023, black=64, fill=700)
        data, size = dng_preview.decode_frame(p, None, scale=2)
        self.assertEqual(size, (32, 16))
        self.assertEqual(data[:2], b"\xff\xd8")

    def test_ten_bit_unpack_matches_the_stored_value(self):
        """decode_frame() alone can't tell a correct unpack from a
        consistently wrong one (both would "just decode") -- this checks
        the actual recovered sample value, mono so gamma/CFA averaging
        don't obscure it. 700/1023 (~68%) is comfortably off both 0 and
        255 so a shifted or byte-swapped unpack would visibly miss."""
        p = build_dng(self.dir / "g.dng", width=64, height=32, bits=10,
                      white=1023, black=0, fill=700, cfa=None)
        jpeg, _ = dng_preview.decode_frame(p, None, scale=2, mono=True)
        rendered = np.asarray(Image.open(io.BytesIO(jpeg))).astype(float).mean()
        expected = ((700 / 1023) ** (1 / 2.2)) * 255
        self.assertAlmostEqual(rendered, expected, delta=3.0)

    def test_ten_bit_width_not_a_multiple_of_four_is_refused(self):
        """Every 10-bit sensor mode cinepi-raw actually ships has a
        width that's a multiple of 4 (dng_pack.hpp's pack_row_10bit()
        relies on the same guarantee) -- refuse rather than silently
        misinterpret a shape the writer never produces."""
        p = build_dng(self.dir / "h.dng", width=62, height=32, bits=10, fill=700)
        with self.assertRaises(dng_preview.DngError):
            dng_preview.decode_frame(p, None, scale=2)

    def test_mode_inference_across_the_modes_cinepi_writes(self):
        sdr = build_dng(self.dir / "sdr.dng", bits=12, white=4095, black=200)
        hdr16 = build_dng(self.dir / "hdr16.dng", bits=16, white=65535, black=3200)
        # 12-bit ClearHDR: companded codes plus a table whose output is the
        # linear domain, so WhiteLevel is far above the 12-bit code ceiling.
        lut = [min(65535, i * 16) for i in range(4096)]
        hdr12 = build_dng(self.dir / "hdr12.dng", bits=12, white=63265,
                          black=200, linearization=lut)

        self.assertEqual(dng_preview.describe_mode(dng_preview.read_metadata(sdr)),
                         (False, "linear", "SDR", 12, False))
        self.assertEqual(dng_preview.describe_mode(dng_preview.read_metadata(hdr16)),
                         (True, "linear", "HDR", 16, False))
        self.assertEqual(dng_preview.describe_mode(dng_preview.read_metadata(hdr12)),
                         (True, "companded", "HDR", 12, False))

    def test_log10_reports_the_source_depth_not_the_storage_depth(self):
        """BitsPerSample 10 with a table is unambiguous -- unlike 12-bit,
        nothing but cinepi-raw's log encoder ever produces it (no native
        10-bit sensor mode or CCMP companding carries a table at 10 bits).
        display_bits should say what the take was actually SHOT at (12 or
        16, from the same white>4095 split as `hdr`), not the 10-bit
        encoding it was compressed to for storage."""
        # log-to-10 from a 12-bit SDR source: white stays in the SDR range.
        # The table is indexed by the STORED (10-bit) code, so it only
        # needs 1024 entries, not the 12-bit source's 4096.
        lut10_sdr = list(range(1024))
        sdr_source = build_dng(self.dir / "log10_sdr.dng", bits=10, white=1023,
                               black=64, linearization=lut10_sdr, fill=400)
        hdr, encoding, label, display_bits, log10 = dng_preview.describe_mode(
            dng_preview.read_metadata(sdr_source))
        self.assertTrue(log10)
        self.assertEqual(display_bits, 12)
        self.assertFalse(hdr)

        # log-to-10 from a 16-bit ClearHDR source: white is in the recovered
        # 16-bit linear domain even though the stored codes are 10-bit.
        lut10_hdr = [min(65535, i * 64) for i in range(1024)]
        hdr_source = build_dng(self.dir / "log10_hdr.dng", bits=10, white=65535,
                               black=3200, linearization=lut10_hdr, fill=400)
        hdr, encoding, label, display_bits, log10 = dng_preview.describe_mode(
            dng_preview.read_metadata(hdr_source))
        self.assertTrue(log10)
        self.assertEqual(display_bits, 16)
        self.assertTrue(hdr)

    def test_native_ten_bit_is_not_mistaken_for_log(self):
        """A genuinely 10-bit sensor mode (imx296's only mode, imx477
        1332x990, imx283 modes 3-5) has no LinearizationTable -- log10
        must require the table, not just bits==10."""
        native10 = build_dng(self.dir / "native10.dng", bits=10, white=1023,
                             black=64, linearization=None)
        hdr, encoding, label, display_bits, log10 = dng_preview.describe_mode(
            dng_preview.read_metadata(native10))
        self.assertFalse(log10)
        self.assertEqual(display_bits, 10)

    def test_mono_forces_greyscale_because_the_file_cannot_say(self):
        """cinepi-raw tags a colour CFA even on a mono sensor."""
        p = build_dng(self.dir / "m.dng", width=64, height=32)
        colour, _ = dng_preview.decode_frame(p, None, scale=2, mono=False)
        mono, _ = dng_preview.decode_frame(p, None, scale=2, mono=True)
        self.assertNotEqual(colour, mono)

    def test_linearization_table_is_applied_to_the_pixels(self):
        """A companded frame must be linearised before the levels are applied.

        Skipping the table subtracts a linear-domain BlackLevel from codes that
        never went through the curve (docs/cinemate-log.md:63). The ceiling that
        imposes is what this pins: with 12-bit codes (max 4095) and a table
        whose output white is 62704, an un-linearised decode cannot put any
        pixel above (4095-200)/(62704-200) = 6.2% before gamma, i.e. ~71/255
        after it -- however bright the subject actually was. A near-white patch
        therefore lands under 100 when the table is skipped and well above it
        when it is applied.
        """
        white = 62704
        # Expanding curve in cinepi-raw's shape: the pedestal maps to itself so
        # BlackLevel stays meaningful in the output domain, full scale maps to
        # the tagged WhiteLevel.
        lut = [min(white, int(200 + (white - 200) * ((i - 200) / 3895.0) ** 2.2))
               if i > 200 else i for i in range(4096)]
        bright = build_dng(self.dir / "companded.dng", bits=12, white=white,
                           black=200, linearization=lut, fill=3600)

        jpeg, _ = dng_preview.decode_frame(bright, None, scale=2, mono=True)
        rendered = np.asarray(Image.open(io.BytesIO(jpeg))).astype(float).mean()

        self.assertGreater(
            rendered, 100.0,
            f"near-white companded patch rendered {rendered:.1f}/255 -- at or "
            "below the ~71 ceiling of a decode that skips the table")

    def test_black_level_is_not_put_through_the_table_twice(self):
        """Under a table BOTH levels are already in its output domain.

        Passing BlackLevel through the curve as if it were a stored code
        lands it above the frame's whole linearised range on real footage --
        tag 3200, curve maps 3200 to 11391, frame maxes out at 10817 -- so
        every pixel goes negative, clips, and the take renders solid black.
        Caught on pi-test-takes/CINEPI_26-08-27_223236_F03_C00000_cam0.

        The earlier synthetic curve could not catch this: it mapped the
        pedestal to itself, so lut[black] == black and both readings agreed.
        This one is shaped like the real thing, where they do not.
        """
        # Output domain 2721..65535, as cinepi-raw's 16-bit ClearHDR curve is.
        lut = [min(65535, 2721 + int(i * 15.4)) for i in range(4096)]
        # Stored codes around 500 -> ~10.4k linear, comfortably above the
        # tagged black of 3200 but far below lut[3200] (~10.4k+ ... 51k).
        p = build_dng(self.dir / "levels.dng", bits=12, white=65535,
                      black=3200, linearization=lut, fill=500)

        jpeg, _ = dng_preview.decode_frame(p, None, scale=2, mono=True)
        rendered = np.asarray(Image.open(io.BytesIO(jpeg))).astype(float)

        self.assertLess(
            (rendered == 0).mean(), 1.0,
            "frame rendered entirely black -- BlackLevel is being taken "
            "through the LinearizationTable as though it were a stored code")

        black, white = dng_preview._black_white(dng_preview.read_metadata(p))
        self.assertEqual((black, white), (3200.0, 65535.0),
                         "levels must be used exactly as tagged under a table")

    def test_a_frame_with_no_table_is_untouched_by_linearisation(self):
        """The control for the test above: linear frames must not change."""
        p = build_dng(self.dir / "linear.dng", bits=12, white=4095, black=200,
                      fill=2048, linearization=None)
        jpeg, _ = dng_preview.decode_frame(p, None, scale=2, mono=True)
        rendered = np.asarray(Image.open(io.BytesIO(jpeg))).astype(float).mean()
        expected = (((2048 - 200) / (4095 - 200)) ** (1 / 2.2)) * 255
        self.assertAlmostEqual(rendered, expected, delta=3.0)

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


class ThumbnailReaderTest(unittest.TestCase):
    """C9's other half: cinepi-raw writes IFD1 (Phase 0), this reads it.

    playback.frame_source() answered SOURCE_DECODE for every frame until
    this landed -- meta["thumbnail"] was never set because _parse_ifd()
    never looked past IFD0's own entries. These pin the reading half of
    the same contract build_dng()'s thumbnail= builds.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_thumbnail_is_absent_not_falsy(self):
        """The common case -- every take on a card today. Distinguishing
        "key absent" from "key present but empty" matters because
        frame_source() only checks truthiness, but a future caller might not."""
        p = build_dng(self.dir / "plain.dng", width=64, height=32)
        meta = dng_preview.read_metadata(p)
        self.assertNotIn("thumbnail", meta)

    def test_mono_thumbnail_is_read(self):
        p = build_dng(self.dir / "mono.dng", width=64, height=32,
                      thumbnail={"width": 16, "height": 8, "samples_per_pixel": 1, "fill": 0x40})
        meta = dng_preview.read_metadata(p)
        self.assertIn("thumbnail", meta)
        thumb = meta["thumbnail"]
        self.assertEqual((thumb["width"], thumb["height"]), (16, 8))
        self.assertEqual(thumb["samples_per_pixel"], 1)
        self.assertEqual(thumb["strip_bytes"], 16 * 8)
        # IFD0's own tags are untouched by a thumbnail being present.
        self.assertEqual((meta["width"], meta["height"]), (64, 32))

    def test_colour_thumbnail_is_read(self):
        p = build_dng(self.dir / "colour.dng", width=64, height=32,
                      thumbnail={"width": 16, "height": 8, "samples_per_pixel": 3, "fill": 0x60})
        meta = dng_preview.read_metadata(p)
        thumb = meta["thumbnail"]
        self.assertEqual(thumb["samples_per_pixel"], 3)
        self.assertEqual(thumb["strip_bytes"], 16 * 8 * 3)
        self.assertEqual(thumb["photometric"], 2)  # RGB

    def test_frame_source_answers_thumbnail_when_present(self):
        from module.app import playback

        p = build_dng(self.dir / "with_thumb.dng", width=64, height=32,
                      thumbnail={"width": 16, "height": 8, "samples_per_pixel": 1})
        meta = dng_preview.read_metadata(p)
        self.assertEqual(playback.frame_source(meta), playback.SOURCE_THUMBNAIL)

        p2 = build_dng(self.dir / "no_thumb.dng", width=64, height=32)
        meta2 = dng_preview.read_metadata(p2)
        self.assertEqual(playback.frame_source(meta2), playback.SOURCE_DECODE)

    def test_decode_thumbnail_returns_the_bytes_verbatim(self):
        p = build_dng(self.dir / "d.dng", width=64, height=32,
                      thumbnail={"width": 4, "height": 2, "samples_per_pixel": 1, "fill": 0xAB})
        meta = dng_preview.read_metadata(p)
        jpeg, size = dng_preview.decode_thumbnail(p, meta)
        self.assertEqual(size, (4, 2))
        self.assertEqual(jpeg[:2], b"\xff\xd8")  # a real JPEG, not raw bytes passed through
        rendered = np.asarray(Image.open(io.BytesIO(jpeg)))
        # JPEG is lossy -- a flat 0xAB fill should still land within a few
        # levels of itself, not decode to something structurally different.
        self.assertLess(abs(int(rendered.mean()) - 0xAB), 5)

    def test_decode_thumbnail_refuses_without_one(self):
        p = build_dng(self.dir / "no_thumb2.dng", width=64, height=32)
        meta = dng_preview.read_metadata(p)
        with self.assertRaises(dng_preview.DngError):
            dng_preview.decode_thumbnail(p, meta)

    def test_a_next_ifd_pointer_past_eof_does_not_crash_metadata_reading(self):
        """A corrupt/truncated file's IFD0 tags must still come back -- a
        thumbnail is a bonus, its absence or corruption is never fatal to
        reading the frame's own metadata (or, upstream, to falling back to
        the raw decode)."""
        p = build_dng(self.dir / "corrupt.dng", width=64, height=32,
                      thumbnail={"width": 16, "height": 8, "samples_per_pixel": 1})
        data = bytearray(Path(p).read_bytes())
        # Point IFD0's next-IFD field far past EOF instead of at IFD1.
        ifd0_offset = struct.unpack_from("<I", data, 4)[0]
        count = struct.unpack_from("<H", data, ifd0_offset)[0]
        next_field = ifd0_offset + 2 + 12 * count
        struct.pack_into("<I", data, next_field, len(data) + 10_000_000)
        Path(p).write_bytes(bytes(data))

        meta = dng_preview.read_metadata(p)  # must not raise
        self.assertEqual((meta["width"], meta["height"]), (64, 32))
        self.assertNotIn("thumbnail", meta)


if __name__ == "__main__":
    unittest.main()
