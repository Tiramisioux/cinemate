#!/usr/bin/env python3
"""dngread.py — the shared DNG reader for this workspace. numpy only.

This is the `dng_geom` lift the README asks for: geometry, bit depth, black
level, white level, CFA pattern and the LinearizationTable all come from the
file's own IFD0, so one tool works on both 1928x1090 and 3856x2180 takes.

THE ONE THING NOT TO GET WRONG — 12-bit DNG unpacking is TIFF/DNG MSB-first,
NOT MIPI. Measured, not assumed: the MIPI ordering returns plausible numbers on
R and G2 while silently garbling G1 and B (means of 1942/1948 against a true
225/233). It does not crash and it does not look obviously wrong.

    p0 = (b0 << 4) | (b1 >> 4)
    p1 = ((b1 & 0x0F) << 8) | b2        # 2 px per 3 bytes
"""
import struct
import numpy as np

TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}

TAG = dict(width=256, height=257, bits=258, strip_offset=273, strip_bytes=279,
           cfa_pattern=0x828E, linearization=0xC618, black_repeat_dim=0xC619,
           black=0xC61A, white=0xC61D, as_shot_neutral=0xC628,
           colour_matrix1=0xC621, colour_matrix2=0xC622)


def read_ifd0(path):
    """{tag: (type, count, raw_bytes, endian)} for IFD0, plus the whole file."""
    raw = open(path, "rb").read()
    endian = "<" if raw[:2] == b"II" else ">"
    (magic,) = struct.unpack(endian + "H", raw[2:4])
    if magic != 42:
        raise ValueError(f"{path}: not a TIFF/DNG")
    (ifd_off,) = struct.unpack(endian + "I", raw[4:8])
    (n,) = struct.unpack(endian + "H", raw[ifd_off:ifd_off + 2])
    tags = {}
    for i in range(n):
        e = ifd_off + 2 + i * 12
        tag, typ, cnt = struct.unpack(endian + "HHI", raw[e:e + 8])
        size = TYPE_SIZE.get(typ, 1) * cnt
        if size <= 4:
            val = raw[e + 8:e + 8 + size]
        else:
            (off,) = struct.unpack(endian + "I", raw[e + 8:e + 12])
            val = raw[off:off + size]
        tags[tag] = (typ, cnt, val, endian)
    return tags, raw


def vals(tags, tag):
    """Tag value as a list of numbers, or None. RATIONALs become floats."""
    if tag not in tags:
        return None
    typ, cnt, b, endian = tags[tag]
    if typ in (5, 10):
        f = "i" if typ == 10 else "I"
        v = struct.unpack(endian + f * (2 * cnt), b[:8 * cnt])
        return [v[i] / (v[i + 1] if v[i + 1] else 1) for i in range(0, len(v), 2)]
    fmt = {1: "B", 3: "H", 4: "I", 6: "b", 8: "h", 9: "i"}.get(typ, "H")
    return list(struct.unpack(endian + fmt * cnt, b[:struct.calcsize(fmt) * cnt]))


def unpack_strip(raw, off, w, h, bits):
    """Standard-DNG-packed CFA strip -> right-justified uint16 (h, w)."""
    n = w * h
    if bits == 16:
        return np.frombuffer(raw, "<u2", count=n, offset=off).reshape(h, w)
    if bits == 12:                                    # 2 px / 3 bytes, MSB-first
        b = np.frombuffer(raw, np.uint8, count=n * 3 // 2, offset=off) \
              .reshape(-1, 3).astype(np.uint16)
        out = np.empty(n, np.uint16)
        out[0::2] = (b[:, 0] << 4) | (b[:, 1] >> 4)
        out[1::2] = ((b[:, 1] & 0x0F) << 8) | b[:, 2]
        return out.reshape(h, w)
    if bits == 10:                                    # 4 px / 5 bytes, MSB-first
        b = np.frombuffer(raw, np.uint8, count=n * 5 // 4, offset=off) \
              .reshape(-1, 5).astype(np.uint16)
        out = np.empty(n, np.uint16)
        out[0::4] = (b[:, 0] << 2) | (b[:, 1] >> 6)
        out[1::4] = ((b[:, 1] & 0x3F) << 4) | (b[:, 2] >> 4)
        out[2::4] = ((b[:, 2] & 0x0F) << 6) | (b[:, 3] >> 2)
        out[3::4] = ((b[:, 3] & 0x03) << 8) | b[:, 4]
        return out.reshape(h, w)
    raise ValueError(f"unsupported BitsPerSample {bits}")


def load(path):
    """Raw CFA codes plus every colour-relevant tag. Nothing is applied."""
    tags, raw = read_ifd0(path)
    g = lambda k: vals(tags, TAG[k])                                  # noqa: E731
    w, h, bits = g("width")[0], g("height")[0], g("bits")[0]
    lut = g("linearization")
    return dict(path=path, w=w, h=h, bits=bits,
                codes=unpack_strip(raw, g("strip_offset")[0], w, h, bits),
                black=g("black"), white=g("white"), cfa=g("cfa_pattern"),
                as_shot_neutral=g("as_shot_neutral"),
                lut=lut, has_lut=lut is not None)
