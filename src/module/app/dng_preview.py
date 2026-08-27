"""CinemaDNG -> JPEG preview decoding for the clip playback pane.

Pure numpy + Pillow + stdlib. No rawpy/libraw, no exiftool subprocess: the
frames cinepi-raw writes are a narrow, known subset of TIFF/DNG, and reading
them directly is both faster and one less runtime dependency on the Pi.

What cinepi-raw actually writes (dng_encoder.cpp), and what this module relies on:
  - little-endian TIFF, one IFD, at the *end* of the file
  - exactly one strip, StripOffsets == 8, RowsPerStrip == full height
  - Compression == 1 (none). There is no embedded thumbnail or preview IFD,
    so a preview cannot be lifted out -- the CFA mosaic must be decoded.
  - BitsPerSample 12 (TIFF MSB-packed, 2 px per 3 bytes) or 16 (plain u2)
  - optional LinearizationTable (12-bit ClearHDR / CineMate Log takes)
  - FrameRate in CinemaDNG tag 51044, written on every frame

Two properties of that layout are what make the playback pane viable, and both
are load-bearing enough to state here:

1. Because the IFD is at the tail and its offset is in the 8-byte header,
   read_metadata() reads ~2 kB per file instead of the 3-16 MB frame. Indexing
   a card full of takes therefore costs kilobytes, not gigabytes.
2. Because the strip is uncompressed and row-addressable, decode_frame() only
   unpacks the rows a downscaled preview actually needs. Cost scales with the
   *output* size, not the frame size.

Decoding is deliberately crude -- one output pixel per 2x2 Bayer cell, no
interpolation. This is a review preview for judging framing, focus and motion,
not a rendering intended to be graded from.
"""

import io
import struct

import numpy as np
from PIL import Image

# Only the tags this decoder acts on. Anything else in the IFD is skipped.
_TAGS = {
    256: "width",
    257: "height",
    258: "bits",
    259: "compression",
    262: "photometric",
    273: "strip_offset",
    277: "samples_per_pixel",
    279: "strip_bytes",
    272: "model",
    33422: "cfa_pattern",
    50712: "linearization_table",
    50714: "black_level",
    50717: "white_level",
    50728: "as_shot_neutral",
    51044: "frame_rate",
}

_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
_TYPE_FMT = {1: "B", 3: "H", 4: "I", 6: "b", 8: "h", 9: "i", 11: "f", 12: "d"}

_PHOTOMETRIC_CFA = 32803

# Read this much of the file tail to cover the IFD plus any out-of-line values
# it points at (a 4096-entry LinearizationTable is 8 kB, the largest of them).
_IFD_TAIL_BYTES = 32768


class DngError(Exception):
    """Raised when a file is not a DNG this decoder can read."""


def _parse_ifd(buf, offset, base=0):
    """Parse one IFD out of ``buf``. ``base`` is the file offset ``buf`` starts at."""
    if buf[:2] == b"II":
        end = "<"
    elif buf[:2] == b"MM":
        end = ">"
    else:
        end = "<"  # tail-only reads carry no header; cinepi-raw is always little-endian

    pos = offset - base
    if pos < 0 or pos + 2 > len(buf):
        raise DngError("IFD offset outside the bytes read")
    count = struct.unpack_from(end + "H", buf, pos)[0]

    tags = {}
    for i in range(count):
        entry = pos + 2 + 12 * i
        if entry + 12 > len(buf):
            raise DngError("truncated IFD")
        tag, typ, cnt = struct.unpack_from(end + "HHI", buf, entry)
        name = _TAGS.get(tag)
        if name is None:
            continue
        size = _TYPE_SIZE.get(typ, 1) * cnt
        if size <= 4:
            data = buf[entry + 8: entry + 8 + size]
        else:
            voff = struct.unpack_from(end + "I", buf, entry + 8)[0] - base
            if voff < 0 or voff + size > len(buf):
                continue  # value lives outside the tail window; not one we need
            data = buf[voff: voff + size]

        if typ == 2:
            value = data.rstrip(b"\0").decode("ascii", "replace")
        elif typ in (5, 10):
            fmt = end + ("II" if typ == 5 else "ii")
            pairs = [struct.unpack_from(fmt, data, 8 * j) for j in range(cnt)]
            value = [a / b if b else 0.0 for a, b in pairs]
        elif typ in _TYPE_FMT:
            value = list(struct.unpack_from(end + str(cnt) + _TYPE_FMT[typ], data))
        else:
            value = list(data)
        tags[name] = value[0] if len(value) == 1 else value

    return tags


def read_metadata(path):
    """Return the tags of ``path`` without reading its pixel data.

    Reads the 8-byte header, seeks to the IFD offset it carries, and reads the
    tail from there. Roughly 2 kB of I/O per frame, which is what makes it
    affordable to probe a take's first frame while building a clip index.
    """
    with open(path, "rb") as handle:
        header = handle.read(8)
        if len(header) < 8 or header[:2] not in (b"II", b"MM"):
            raise DngError("not a TIFF/DNG file")
        end = "<" if header[:2] == b"II" else ">"
        magic, ifd_offset = struct.unpack(end + "HI", header[2:8])
        if magic != 42:
            raise DngError("not a TIFF/DNG file")

        handle.seek(ifd_offset)
        tail = handle.read(_IFD_TAIL_BYTES)

    if not tail:
        raise DngError("IFD offset past end of file")
    return _parse_ifd(tail, ifd_offset, base=ifd_offset)


def frame_rate(meta, default=None):
    """Frame rate from CinemaDNG tag 51044, or ``default`` if absent.

    This is the rate cinepi-raw was *configured* to run at when the frame was
    written, not a measured one. It is the only per-frame fps record on disk;
    everything else (timecode deltas, WAV duration) is a cross-check.
    """
    rate = meta.get("frame_rate")
    if isinstance(rate, list):
        rate = rate[0] if rate else None
    if rate is None or rate <= 0:
        return default
    return round(float(rate), 3)


def describe_mode(meta):
    """Infer the capture mode from the level/depth signature.

    There is no HDR tag. cinepi-raw writes nothing that names ClearHDR, log, or
    SDR, so the mode has to be read off the tags that the encoder *does* vary,
    and the one that actually varies with dynamic range is WhiteLevel -- because
    under a LinearizationTable the level tags describe the table's linear
    OUTPUT, not the stored codes (dng_encoder.cpp).

        BitsPerSample  LinearizationTable  WhiteLevel   -> mode
        12             absent              4095          SDR, 12-bit linear
        16             absent              65535         ClearHDR, 16-bit linear
        12             present             ~62.7k-63.3k  ClearHDR, 12-bit companded
        12/10          present             4095 / 1023   log-encoded SDR
        12/10          present             65535         log-encoded ClearHDR

    Returns ``(hdr, encoding, label)``. ``hdr`` is True when the linear range
    exceeds what a 12-bit sensor mode can hold, which is the thing worth
    badging. ``encoding`` is "linear" or "companded".

    What this deliberately does not claim: *which* curve a LinearizationTable
    holds. The CCMP decompand and the CineMate Log curve are written to the same
    tag (0xC618), and when log runs on top of 12-bit ClearHDR the two are
    composed into one table. A file carrying a table cannot be resolved into
    "log" versus "ClearHDR companding" from the tags alone -- so this does not
    guess, and callers should not present one.
    """
    bits = int(meta.get("bits", 12))
    white = meta.get("white_level")
    if isinstance(white, list):
        white = white[0]
    if white is None:
        white = (1 << bits) - 1
    white = int(white)
    companded = bool(meta.get("linearization_table"))

    hdr = white > 4095
    encoding = "companded" if companded else "linear"

    if not hdr:
        label = "SDR"
    elif companded:
        label = "HDR"          # ClearHDR via companding, or log over ClearHDR
    else:
        label = "HDR"          # 16-bit linear ClearHDR
    return hdr, encoding, label


def _black_white(meta):
    """Black and white levels in the sample domain the pixels are stored in."""
    black = meta.get("black_level", 0)
    black = float(np.mean(black)) if isinstance(black, list) else float(black)

    white = meta.get("white_level")
    if isinstance(white, list):
        white = white[0]
    if white is None:
        white = (1 << int(meta.get("bits", 16))) - 1
    white = float(white)

    # Under a LinearizationTable the stored codes are companded: the levels
    # describe the table's output domain, so take them through the table too.
    table = meta.get("linearization_table")
    if table:
        lut = np.asarray(table, np.uint16)
        white = float(lut.max())
        black = float(lut[min(int(black), len(lut) - 1)])
    return black, white


def _cfa_letters(meta):
    """CFA pattern as four letters (e.g. ['B','G','G','R']), or None for mono."""
    if meta.get("photometric") != _PHOTOMETRIC_CFA:
        return None
    pattern = meta.get("cfa_pattern")
    if not pattern:
        return None
    if isinstance(pattern, (bytes, bytearray)):
        pattern = list(pattern)
    letters = {0: "R", 1: "G", 2: "B"}
    try:
        return [letters[int(v)] for v in pattern[:4]]
    except KeyError:
        return None


def _load_rows(path, meta, row_step):
    """Load only every ``row_step``-th Bayer row *pair* of the frame.

    The strip is uncompressed and starts at a fixed offset, so rows are directly
    addressable. Skipping rows here is what keeps decode cost proportional to
    the preview size rather than the sensor size -- at 1/4 scale it is a quarter
    of the unpacking work, and the 12-bit unpack is the single most expensive
    step in the pipeline.
    """
    width = int(meta["width"])
    height = int(meta["height"])
    bits = int(meta.get("bits", 16))
    offset = int(meta.get("strip_offset", 8))

    if bits == 12:
        row_bytes = width * 3 // 2
    elif bits == 16:
        row_bytes = width * 2
    else:
        raise DngError(f"unsupported BitsPerSample {bits}")

    # Row pairs: each output pixel needs the top and bottom row of one Bayer cell.
    pair_starts = np.arange(0, height - 1, 2 * row_step, dtype=np.int64)
    wanted = np.empty(pair_starts.size * 2, dtype=np.int64)
    wanted[0::2] = pair_starts
    wanted[1::2] = pair_starts + 1

    if row_step == 1:
        # Every row pair is wanted, so one sequential read is strictly better
        # than seeking.
        with open(path, "rb") as handle:
            handle.seek(offset)
            strip = handle.read(row_bytes * height)
        if len(strip) < row_bytes * height:
            raise DngError("frame truncated")
        rows = np.frombuffer(strip, np.uint8).reshape(height, row_bytes)[wanted]
    else:
        # Read only the row pairs the preview needs. The two rows of a Bayer
        # cell are adjacent, so this is one contiguous read per pair rather than
        # per row -- and it cuts bytes off the card by ``row_step``, which is
        # what keeps UHD playback off the storage bandwidth ceiling.
        rows = np.empty((wanted.size, row_bytes), np.uint8)
        pair_bytes = row_bytes * 2
        with open(path, "rb") as handle:
            for n, start in enumerate(pair_starts):
                handle.seek(offset + int(start) * row_bytes)
                chunk = handle.read(pair_bytes)
                if len(chunk) < pair_bytes:
                    raise DngError("frame truncated")
                rows[2 * n:2 * n + 2] = np.frombuffer(chunk, np.uint8).reshape(2, row_bytes)

    if bits == 16:
        return rows.view("<u2").reshape(len(wanted), width)

    # TIFF MSB-first 12-bit: 2 pixels per 3 bytes.
    triples = rows.reshape(-1, 3).astype(np.uint16)
    out = np.empty((triples.shape[0], 2), np.uint16)
    out[:, 0] = (triples[:, 0] << 4) | (triples[:, 1] >> 4)
    out[:, 1] = ((triples[:, 1] & 0x0F) << 8) | triples[:, 2]
    return out.reshape(len(wanted), width)


def _to_rgb(raw, letters, col_step):
    """Collapse each 2x2 Bayer cell to one pixel. ``raw`` is already row-reduced."""
    step = 2 * col_step
    if letters is None:
        return raw[0::2, ::step].astype(np.float32)[..., None]

    planes = {}
    for index, letter in enumerate(letters):
        row, col = divmod(index, 2)
        planes.setdefault(letter, []).append(raw[row::2, col::step])

    height = min(min(p.shape[0] for p in v) for v in planes.values())
    width = min(min(p.shape[1] for p in v) for v in planes.values())

    def plane(letter):
        parts = [p[:height, :width].astype(np.float32) for p in planes[letter]]
        return parts[0] if len(parts) == 1 else (parts[0] + parts[1]) * 0.5

    return np.stack([plane("R"), plane("G"), plane("B")], axis=-1)


def decode_frame(path, meta=None, scale=4, quality=80, auto_levels=False,
                 mono=False, gamma=1 / 2.2):
    """Decode one DNG to JPEG bytes.

    ``scale`` is the reduction factor: 4 means a quarter of the sensor's width
    (one pixel per Bayer cell), 8 an eighth, and so on. Values below 4 are not
    supported -- there is no interpolating demosaic here, so a Bayer cell is the
    smallest unit that yields a colour pixel.

    ``mono`` forces greyscale. cinepi-raw tags every frame with a colour CFA
    even on a monochrome sensor, so nothing on disk distinguishes the two and
    the caller has to say.

    Returns ``(jpeg_bytes, (width, height))``.
    """
    if scale < 4 or scale % 4:
        raise ValueError("scale must be a multiple of 4")
    if meta is None:
        meta = read_metadata(path)
    if meta.get("compression", 1) != 1:
        raise DngError("compressed DNG frames are not supported")

    cell_step = scale // 4  # extra Bayer cells to skip beyond the 2x2 collapse
    raw = _load_rows(path, meta, row_step=cell_step)
    letters = None if mono else _cfa_letters(meta)
    rgb = _to_rgb(raw, letters, col_step=cell_step)

    black, white = _black_white(meta)
    rgb = (rgb - black) / max(white - black, 1.0)
    np.clip(rgb, 0.0, 1.0, out=rgb)

    if auto_levels:
        low, high = np.percentile(rgb, (0.5, 99.7))
        if high - low > 1e-6:
            rgb = np.clip((rgb - low) / (high - low), 0.0, 1.0)

    rgb = rgb ** np.float32(gamma)
    out = (rgb * 255.0 + 0.5).astype(np.uint8)
    if out.shape[-1] == 1:
        out = out[..., 0]

    buffer = io.BytesIO()
    Image.fromarray(out).save(buffer, "JPEG", quality=quality,
                              subsampling=2, optimize=False)
    height, width = out.shape[0], out.shape[1]
    return buffer.getvalue(), (width, height)
