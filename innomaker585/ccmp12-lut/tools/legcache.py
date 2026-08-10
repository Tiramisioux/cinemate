#!/usr/bin/env python3
"""legcache.py — cache fitcurve.leg_points to disk so diagnosis is interactive.

    from legcache import legs, points
    P = points("17:05", "3<->5 full res", "G1")

Reading 12 DNGs and blocking four phases takes ~20 s per leg; a diagnosis pass
asks the same question of the same blocks twenty times. The cache is keyed on
every argument that changes the blocks -- take paths, block size, frame limit,
satmax, the co-registration switch -- so a changed knob misses rather than
silently returning stale points.

NOTHING here changes a number. It stores exactly what leg_points returned.
"""
import os, sys, glob, hashlib
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modes as M                                                   # noqa: E402
from fitcurve import leg_points, PHASES                             # noqa: E402
from fit_all import SESSIONS, ALL_LEGS, take_dir                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "evidence", "cache")

# (session, leg name) -> (A mode, B mode, expected b, section)
LEGS = {(s, l[1]): (l[2], l[3], l[4], l[0])
        for s, _, _ in SESSIONS for l in ALL_LEGS}


def _key(sess, leg, phase, **kw):
    h = hashlib.sha1(repr(sorted(kw.items())).encode()).hexdigest()[:10]
    safe = leg.replace("<->", "-").replace(" ", "_")
    return os.path.join(CACHE, f"{sess.replace(':','')}_{safe}_{phase}_{h}.npz")


def points(sess, leg, phase, bs=8, limit=6, satmax=0.0, register=True,
           measured_black=True, refresh=False):
    """leg_points for one (session, leg, phase), cached on disk."""
    kw = dict(bs=bs, limit=limit, satmax=satmax, register=register,
              measured_black=measured_black)
    f = _key(sess, leg, phase, **kw)
    if os.path.exists(f) and not refresh:
        z = np.load(f, allow_pickle=True)
        d = {k: z[k] for k in z.files}
        d["meta"] = d["meta"].item()
        d["shape"] = tuple(d["shape"])
        return d
    am, bm, _, _ = LEGS[(sess, leg)]
    root, mm = next((r, m) for s, r, m in SESSIONS if s == sess)
    P = leg_points(take_dir(root, mm[am][0]), take_dir(root, mm[bm][0]), phase,
                   bs=bs, limit=limit, satmax=satmax, register=register,
                   measured_black=measured_black)
    os.makedirs(CACHE, exist_ok=True)
    np.savez_compressed(f, **{k: v for k, v in P.items() if k != "meta"},
                        meta=np.array(P["meta"], dtype=object))
    return P


def all_points(section="3.2", **kw):
    """{(session, leg, phase): P} for every leg in a section."""
    out = {}
    for sess, _, _ in SESSIONS:
        for sec, leg, am, bm, b_exp in ALL_LEGS:
            if section not in ("both", sec):
                continue
            for ph in PHASES:
                out[(sess, leg, ph)] = points(sess, leg, ph, **kw)
    return out


if __name__ == "__main__":
    sec = sys.argv[1] if len(sys.argv) > 1 else "3.2"
    for k, P in all_points(sec).items():
        print(f"{k[0]:>7} {k[1]:>16} {k[2]:>3}  {P['meta']['nused']:>6} blocks  "
              f"x {P['x'].min():8.1f}..{P['x'].max():8.1f}  "
              f"dy={P['meta']['dy']:+d} r={P['meta']['corr']:.3f}")
