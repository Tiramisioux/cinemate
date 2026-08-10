#!/usr/bin/env python3
"""ccmp_decode.py — ONE generator, TWO tables. The CCMP12 decompand LUT.

    ccmp_decode.py --report          # §3.4: knees, domains, tags, both b
    ccmp_decode.py --vs-133          # §3.4: measured against §13.3's derived curve
    ccmp_decode.py --check           # the self-tests (no DNG is touched)

THE MODEL, measured (handoff §2, §3.2b, §3.2c, §3.3e):

    stored_code = ccmp(b*L)/b + P        b = 4 binned, 1 full res
                                         L = linear above black, in 16-bit
                                             ClearHDR LSB (mode 4/5's scale)
    ccmp(x) = x                          x <= T1
            = T1 + (x-T1)*s1             T1 < x <= T2
            = C2 + (x-T2)*s2             x >  T2,  C2 = T1 + (T2-T1)*s1

Nothing here is typed twice. The only literals are the register readbacks
(T1, T2 and the two ratio menu indices — the index IS the register value and
ratio = 1/2**idx, handoff §2), the BlackLevel tag P, and the measured binning
factor b. Every knee code, every table entry and both tags are computed.

  ** NEVER HAND-WRITE A GOLDEN VALUE ** (handoff §4). The "at code 400 the
  decode gives 4925" error came from doing this arithmetic by hand: it mixed the
  binned L-domain knot 2875 with the un-binned code-domain knot 671.875 and
  dropped the final /b. It is 3387.5, and this file is why.

§13.3 of CINEMATE-LOG-COLORCHECKER.md is NOT reimplemented here. It is this
same generator with P=0 and b=1 — that is exactly what "the compander sees
black-inclusive 16-bit data" means — so the §3.4 comparison is mechanical.

OUTPUT DOMAIN. A DNG LinearizationTable is TIFF type SHORT: entries are uint16,
max 65535. It also moves BlackLevel and WhiteLevel into the TABLE'S OUTPUT
domain, so both tags must be rewritten to match. The domains are enumerated in
DOMAINS and `--report` prints all of them with their tags and whether they fit;
KEEP_PEDESTAL is the one chosen in §3.4. Nothing is clamped — a domain that
does not fit raises, because a silently clipped highlight is exactly the defect
this table exists to remove.

Rounding is floor(x+0.5), not numpy's round-half-to-even. Every entry on mode
2's top segment is a half-integer (16*C - 2812.5), so a half-to-even rule would
alternate the step 15/17 and put a visible ripple in the LUT's slope.
"""
import argparse, json, os
import numpy as np

# ── the registers, read back from the driver with ClearHDR live (handoff §2) ──
T1_REG, T2_REG = 500.0, 11500.0        # CCMP thresholds
ACMP1_IDX, ACMP2_IDX = 6, 4            # menu index IS the register value,
                                       # ratio = 1/2**idx -> 1/64 and 1/16
P_TAG = 200.0                          # BlackLevel, measured on all six modes
B_BINNED, B_FULL = 4.0, 1.0            # measured 4.004/4.003 and 0.998/0.995
BITS = 12                              # BitsPerSample of the CCMP modes

# ── the middle segment's ANCHOR, measured (handoff §3.6, tools/anchor.py) ─────
# The model's middle and high segments both hang off one number,
#
#     a1 = P + T1*(1 - s1)/b
#
# and P, T1 and b enter them ONLY through it -- so on those segments the three
# are DEGENERATE and no mid-segment data can separate them. What IS determined,
# to +/-0.03 codes and reproducibly on both chart sessions, is a1 itself:
#
#     delta_c = a1(measured) - a1(register+tag)     mid segment, 8 leg-phases
#       b = 1   0.3266 (17:05)   0.3406 (18:37)     -> 0.3336, spread 0.03/0.07
#       b = 4   0.2283 (17:05)   0.2359 (18:37)     -> 0.2321, spread 0.025
#
# Held here as an effective T1 with P kept at the measured tag 200 (§2) and b at
# the design value. THAT ASSIGNMENT IS A CHOICE, NOT A MEASUREMENT -- the same
# a1 could be written as a pedestal of 200.33/200.23 or a b of 0.9993/3.992, and
# the table is bit-identical either way. It is written on T1 because that is the
# only one of the three the low segment does not contradict: mode 3's identity
# segment measures the pedestal directly and puts it within +/-0.5 of 200, while
# 0.33 codes of pedestal would be 21 L on the middle segment either way.
#
# ** delta_c does NOT scale as 1/b between the modes ** -- 0.33 against 0.23 is
# a ratio of 1.4, where a pure T1 error would give 4 and a pure pedestal error
# 1. So it is not one physical parameter shared by the two modes. It is two
# measured anchors, one per table, which is what "one generator, two tables"
# already provides for.
T1_EFF = {B_FULL: 500.3389, B_BINNED: 500.9431}


def for_mode(b, anchored=True):
    """The delivered curve for one mode: register T1, or the measured anchor.

    anchored=False is the register-only curve -- what §3.2d closed on, and what
    every number in §3.4 was computed from. Keep it reachable: the difference
    between the two IS the §3.5 residual, and a tool that can only build the
    corrected one cannot show that.
    """
    return Ccmp(b, T1=(T1_EFF[b] if anchored and b in T1_EFF else T1_REG))


class Ccmp:
    """The transfer, parameterised. b and P are the only per-mode inputs."""

    def __init__(self, b, P=P_TAG, T1=T1_REG, T2=T2_REG,
                 i1=ACMP1_IDX, i2=ACMP2_IDX):
        self.b, self.P, self.T1, self.T2 = float(b), float(P), float(T1), float(T2)
        self.s1, self.s2 = 2.0 ** -i1, 2.0 ** -i2
        self.C2 = self.T1 + (self.T2 - self.T1) * self.s1   # ccmp at the 2nd knot

    # ── the compander itself, in its own (pre-binning) domain ──
    def ccmp(self, x):
        x = np.asarray(x, float)
        return np.where(x <= self.T1, x,
               np.where(x <= self.T2, self.T1 + (x - self.T1) * self.s1,
                        self.C2 + (x - self.T2) * self.s2))

    def ccmp_inv(self, y):
        y = np.asarray(y, float)
        return np.where(y <= self.T1, y,
               np.where(y <= self.C2, self.T1 + (y - self.T1) / self.s1,
                        self.T2 + (y - self.C2) / self.s2))

    # ── the delivered transfer: linear-above-black <-> stored 12-bit code ──
    def forward(self, L):
        return self.ccmp(self.b * np.asarray(L, float)) / self.b + self.P

    def inverse(self, C):
        return self.ccmp_inv(self.b * (np.asarray(C, float) - self.P)) / self.b

    # ── where the knees land, in both domains ──
    @property
    def knots_L(self):
        return self.T1 / self.b, self.T2 / self.b

    @property
    def knee_codes(self):
        return tuple(float(self.forward(k)) for k in self.knots_L)


# ── candidate output domains for the table ────────────────────────────────────
# name -> (pedestal added to L on the way out, rescale to fill uint16?)
# The four candidates of §3.4. `build` accepts or rejects each on the uint16
# constraint alone — the choice is forced, not preferred.
DOMAINS = {
    "ABOVE_BLACK":   (0.0,        False),  # (a) BlackLevel 0
    "KEEP_PEDESTAL": (P_TAG,      False),  # (a') BlackLevel unchanged at 200
    "RAW16":         (16 * P_TAG, False),  # (b) mode 4/5's own 3200 pedestal
    "SCALED":        (P_TAG,      True),   # (c) stretched to fill 0..65535
}


def build(c, domain="KEEP_PEDESTAL", bits=BITS):
    """The table and its two tags. Derived — nothing here is transcribed."""
    if domain not in DOMAINS:
        raise SystemExit(f"unknown domain {domain!r}; have {list(DOMAINS)}")
    ped, rescale = DOMAINS[domain]
    codes = np.arange(1 << bits)
    exact = c.inverse(codes) + ped
    scale = 65535.0 / exact[-1] if rescale else 1.0
    exact = exact * scale
    lo, top = float(exact.min()), float(exact[-1])
    # 1e-6 of one code: SCALED lands on exactly 65535 by construction, and a
    # bare `> 65535` rejects it on a float ulp with a message about clipped
    # highlights that would be a lie.
    if lo < -1e-6 or top > 65535 + 1e-6:
        why = ("every stored code below the pedestal, which is where a real "
               "dark frame puts 10.7% of its pixels"
               if lo < 0 else
               "the highlights this table exists to recover")
        raise SystemExit(
            f"domain {domain} does not fit uint16 for b={c.b:g}: "
            f"range {lo:.1f}..{top:.1f}. A LinearizationTable entry is TIFF "
            f"SHORT. Clamping would lose {why} — pick another domain.")
    table = np.floor(exact + 0.5).astype(np.uint16)
    # Rounding cost on the identity segment, where the true transfer is exactly
    # 1:1 and any ripple we add is ours, not the sensor's.
    n1 = int(np.floor(c.knee_codes[0]))
    step = np.diff(table[:n1 + 1].astype(int))
    return dict(table=table, exact=exact, domain=domain, scale=scale,
                black=int(np.floor(ped * scale + 0.5)), white=int(table[-1]),
                white_exact=top,
                seg0_step=(int(step.min()), int(step.max())) if len(step) else (0, 0),
                seg0_err=float(np.abs(exact[:n1 + 1] - table[:n1 + 1]).max()))


# ── self-tests. These run before any DNG is touched. ─────────────────────────
def check(verbose=True):
    fails = []

    def ok(name, cond, detail=""):
        (print(f"  {'ok ' if cond else 'FAIL'}  {name}  {detail}")
         if verbose else None)
        if not cond:
            fails.append(name)

    for label, b in (("full res", B_FULL), ("binned", B_BINNED)):
        c = for_mode(b)
        codes = np.arange(1 << BITS)

        # 1. ROUND TRIP, the test the handoff asks for first.
        rt = c.forward(c.inverse(codes))
        ok(f"[{label}] forward o inverse == identity on all 4096 codes",
           np.allclose(rt, codes, atol=1e-9),
           f"max |err| {np.abs(rt - codes).max():.2e}")

        # ...and the other way, on a dense L grid spanning both knots.
        L = np.linspace(0, float(c.inverse(4095)), 200001)
        ok(f"[{label}] inverse o forward == identity on L in [0, L(4095)]",
           np.allclose(c.inverse(c.forward(L)), L, atol=1e-6),
           f"max |err| {np.abs(c.inverse(c.forward(L)) - L).max():.2e}")

        # 2. The knots land where the registers put them, divided by b.
        k1, k2 = c.knots_L
        ok(f"[{label}] knots at T/b", (k1, k2) == (c.T1 / b, c.T2 / b),
           f"L = {k1:g} and {k2:g}")

        # 3. Slopes either side of each knot are the register ratios.
        e = 1e-6
        for nm, k, want in (("1", k1, (1.0, c.s1)), ("2", k2, (c.s1, c.s2))):
            lo = float(c.forward(k) - c.forward(k - e)) / e
            hi = float(c.forward(k + e) - c.forward(k)) / e
            ok(f"[{label}] slopes across knee{nm} are {want[0]:g} -> {want[1]:g}",
               abs(lo - want[0]) < 1e-4 and abs(hi - want[1]) < 1e-4,
               f"measured {lo:.6f} -> {hi:.6f}")

        # 4. Monotone, and the identity below knee1 in the chosen domain.
        t = build(c, "KEEP_PEDESTAL")["table"]
        ok(f"[{label}] table is monotone non-decreasing", bool((np.diff(t) >= 0).all()))
        n1 = int(np.floor(c.knee_codes[0]))
        ok(f"[{label}] KEEP_PEDESTAL table is the identity on [0, knee1]",
           bool((t[:n1 + 1] == codes[:n1 + 1]).all()),
           f"codes 0..{n1}")

    # 5. The two tables are genuinely different — one cannot serve both modes.
    tb = build(for_mode(B_BINNED), "KEEP_PEDESTAL")["table"]
    tf = build(for_mode(B_FULL), "KEEP_PEDESTAL")["table"]
    ok("the binned and full-res tables differ", bool((tb != tf).any()),
       f"max |diff| {int(np.abs(tb.astype(int) - tf.astype(int)).max())} codes")

    # 6. THE ANCHOR. The correction must deliver exactly the measured delta_c on
    # the middle segment and delta_c/4 on the high one, and NOTHING below knee1
    # — that is the whole claim, and it is arithmetic, not a fit.
    for label, b, dc in (("full res", B_FULL, 0.3336), ("binned", B_BINNED, 0.2321)):
        reg, eff = for_mode(b, False), for_mode(b)
        mid = 0.5 * (reg.knots_L[0] + reg.knots_L[1])
        hi = reg.knots_L[1] * 1.2
        for nm, L, want in (("middle", mid, dc * 64), ("high", hi, dc * 16)):
            got = float(reg.inverse(eff.forward(L)) - L)
            ok(f"[{label}] anchor moves the {nm} segment by delta_c*dL/dC",
               abs(got - want) < 0.05 * abs(want),
               f"{got:.2f} L against {want:.2f} predicted")
        lo = reg.knots_L[0] * 0.5
        ok(f"[{label}] anchor leaves the identity segment alone",
           abs(float(reg.inverse(eff.forward(lo)) - lo)) < 1e-9)

    if verbose:
        print(f"\n{len(fails)} failed" if fails else "\nall passed")
    return fails


# ── reports ───────────────────────────────────────────────────────────────────
def emit(outdir, domain="KEEP_PEDESTAL"):
    """Write the two tables and their tags. 4096 uint16 entries each."""
    os.makedirs(outdir, exist_ok=True)
    man = {}
    for label, b, m in (("mode3_fullres", B_FULL, 3), ("mode2_binned", B_BINNED, 2)):
        c = for_mode(b)
        r = build(c, domain)
        base = os.path.join(outdir, f"ccmp_decode_{label}")
        r["table"].astype("<u2").tofile(base + ".bin")
        with open(base + ".txt", "w") as f:
            f.write(f"# CCMP12 decompand LinearizationTable — mode {m}, b={b:g}\n"
                    f"# domain {domain}; BlackLevel {r['black']} WhiteLevel "
                    f"{r['white']}; {len(r['table'])} uint16 entries\n"
                    f"# T1 {c.T1:.4f} (register {T1_REG:g} + measured anchor) "
                    f"T2 {c.T2:g} s1 1/{1/c.s1:g} s2 1/{1/c.s2:g} P {c.P:g}\n")
            for i in range(0, len(r["table"]), 16):
                f.write(" ".join(f"{v:5d}" for v in r["table"][i:i + 16]) + "\n")
        man[label] = dict(mode=m, b=b, domain=domain, black=r["black"],
                          white=r["white"], white_exact=r["white_exact"],
                          T1=c.T1, T2=c.T2, s1=c.s1, s2=c.s2, P=c.P,
                          knee_codes=list(c.knee_codes), knots_L=list(c.knots_L),
                          entries=int(len(r["table"])),
                          files=[os.path.basename(base) + e for e in (".bin", ".txt")])
        print(f"  {label:<16} {base}.bin / .txt   BlackLevel {r['black']}  "
              f"WhiteLevel {r['white']}")
    json.dump(man, open(os.path.join(outdir, "manifest.json"), "w"), indent=1)
    print(f"  manifest         {os.path.join(outdir, 'manifest.json')}")
    return man


def report():
    print("§3.4 — the generator's own arithmetic. Nothing below is transcribed.\n")
    print(f"registers  T1 {T1_REG:g}  T2 {T2_REG:g}  "
          f"ACMP1 idx {ACMP1_IDX} = 1/{2**ACMP1_IDX}  "
          f"ACMP2 idx {ACMP2_IDX} = 1/{2**ACMP2_IDX}   pedestal P {P_TAG:g}")
    print(f"measured anchor -> effective T1  "
          + "   ".join(f"b={b:g}: {t:.4f}" for b, t in sorted(T1_EFF.items()))
          + "   (§3.6; P and b held, see T1_EFF)\n")
    for label, b, m in (("mode 3  full res", B_FULL, 3), ("mode 2  binned", B_BINNED, 2)):
        c = for_mode(b)
        k1, k2 = c.knots_L
        c1, c2 = c.knee_codes
        print(f"{label}   b = {b:g}   (mode {m})")
        print(f"  knee1   L {k1:10.4f}   ->  code {c1:9.5f}")
        print(f"  knee2   L {k2:10.4f}   ->  code {c2:9.5f}")
        print(f"  code 4095            ->  L    {float(c.inverse(4095)):10.4f}")
        print(f"  code  400            ->  L    {float(c.inverse(400)):10.4f}"
              f"   (handoff §2 point 4)")
        for d in DOMAINS:
            try:
                r = build(c, d)
                lo, hi = r["seg0_step"]
                print(f"    {d:<14} BlackLevel {r['black']:>6}   "
                      f"WhiteLevel {r['white']:>6}   (exact {r['white_exact']:.1f})"
                      f"   fits   identity-segment step {lo}..{hi}, "
                      f"round err {r['seg0_err']:.2f}")
            except SystemExit as e:
                print(f"    {d:<14} REJECTED — {str(e).split(': ', 1)[1]}")
        print()


def vs_133():
    """§13.3 is this generator with P=0 and b=1. Compare, do not transcribe."""
    d133 = Ccmp(b=1.0, P=0.0)
    print("§3.4 — measured against §13.3's derived curve.")
    print("§13.3 IS this generator with P=0, b=1 (its compander sees "
          "black-INCLUSIVE 16-bit data).\n")
    print(f"§13.3's own numbers, regenerated:")
    print(f"  companded black   = forward(3200) = {float(d133.forward(16 * P_TAG)):.4f}"
          f"     (doc says 'approx 542')")
    print(f"  WhiteLevel        = inverse(4095) = {float(d133.inverse(4095)):.1f}"
          f"        (doc says 66270)")
    print(f"  knee1, knee2 code = {d133.knee_codes[0]:.4f}, {d133.knee_codes[1]:.4f}"
          f"   (its knee1 sits BELOW its own black of 3200 -> 'unobservable')\n")

    for label, b in (("mode 3 (b=1)", B_FULL), ("mode 2 (b=4)", B_BINNED)):
        c = for_mode(b)
        print(f"{label} — decoded L at the same stored code")
        print(f"  {'code':>10}{'measured':>12}{'§13.3':>12}{'§13.3 - meas':>14}"
              f"{'ratio':>9}   note")
        pts = [P_TAG, c.knee_codes[0], c.knee_codes[1], 1000.0, 4095.0]
        notes = ["black", "knee1", "knee2", "", "white (code 4095)"]
        for C, n in zip(pts, notes):
            mv, dv = float(c.inverse(C)), float(d133.inverse(C))
            rat = "--" if mv == 0 else f"{dv / mv:.2f}"
            print(f"  {C:>10.5g}{mv:>12.2f}{dv:>12.2f}{dv - mv:>14.2f}"
                  f"{rat:>9}   {n}")
        print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--vs-133", dest="vs133", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--emit", metavar="DIR",
                    help="write both tables plus a manifest")
    a = ap.parse_args()
    if not (a.report or a.vs133 or a.check or a.emit):
        ap.print_help()
    if a.check:
        raise SystemExit(1 if check() else 0)
    if a.report:
        report()
    if a.vs133:
        vs_133()
    if a.emit:
        # The self-tests gate the emit: no table is written from a generator
        # that has not just proved its own round trip and its anchor.
        if check(verbose=False):
            raise SystemExit("self-tests FAILED — no table written")
        print(f"self-tests passed; writing to {a.emit}")
        emit(a.emit)
