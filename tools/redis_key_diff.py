#!/usr/bin/env python3
"""
redis_key_diff.py — diff the two Redis key registries that make up the
cinemate <-> cinepi-raw contract.

Why this exists
---------------
The contract between the two repos is the set of Redis keys both sides agree
on, published over the `cp_controls` channel. But each repo keeps its own
registry, in its own language, with no shared source:

    cinemate    ParameterKey(Enum)        src/module/redis_controller.py
    cinepi-raw  #define CONTROL_KEY_*     cinepi/cinepi_state.hpp

Nothing reconciles them. Review session S03 found at least 11 keys that
cinepi-raw handles and cinemate never references — six of them registered
control handlers that can never fire (finding F-027). Nothing existed that
could have caught that: two languages, two repos, no shared header, no test,
no CI.

This script is the missing check. It is deliberately dependency-free and
hardware-free so it can run on a laptop or in CI.

Usage
-----
    python3 redis_key_diff.py [--cinemate DIR] [--cinepi-raw DIR] [--strict]

    --strict   exit 1 if any cinepi-raw key is unreferenced in cinemate.
               Intended for CI once the current drift is triaged.

Exit codes: 0 ok / 1 drift found (--strict only) / 2 could not read a registry.

KNOWN LIMITATION — read this before trusting the numbers
--------------------------------------------------------
Both registries are extracted by pattern matching, which cannot see
dynamically constructed keys. At least one important key is built by string
concatenation on both sides and appears in neither registry:

    cinepi-raw  cinepi_raw.cpp    "cinepi_ready_" + options->CamPort()
    cinemate    cinepi_multi.py   redis_controller.r.keys("cinepi_ready_*")

So every count this script prints is a LOWER BOUND on the real contract and a
LOWER BOUND on the real drift. It is a regression guard, not a census. Treat a
clean run as "no new drift of the kind this script can see".
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# --- extraction -------------------------------------------------------------

# ParameterKey members:  BIT_DEPTH = "bit_depth"   /   SHUTTER_A_NOM = 'shutter_angle_nom'
# Both quote styles occur. An early review pass used \x27 inside a
# single-quoted shell grep pattern, where it is a literal backslash, and
# silently dropped the five single-quoted members. Hence a real parser here.
PY_MEMBER = re.compile(r'^\s+[A-Z][A-Z_0-9]*\s*=\s*[\'"]([a-z_0-9]+)[\'"]', re.M)

# #define CONTROL_KEY_RECORD "is_recording"
CPP_DEFINE = re.compile(r'^\s*#define\s+CONTROL_KEY_\w+\s+"([A-Za-z_0-9]+)"', re.M)

# Keys cinepi-raw touches WITHOUT going through a CONTROL_KEY_ macro:
#   redis_->set("pll_phase_err_us", ...)      direct literal call
#   constexpr char RECORDER_VU_REDIS_KEY[] = "audio_vu";
# The macros alone undercount the contract, so both are collected.
CPP_DIRECT = re.compile(
    r'redis_?->\s*(?:set|get|hget|hset|hgetall|del|exists|incr|publish)\s*\(\s*"([A-Za-z_0-9]+)"')
CPP_CONSTEXPR = re.compile(r'constexpr\s+char\s+\w+\s*\[\]\s*=\s*"([a-z_0-9]+)"')


def cinemate_keys(repo: Path) -> set[str]:
    """Values of every ParameterKey enum member."""
    src = (repo / "src/module/redis_controller.py").read_text(errors="replace")
    try:
        start = src.index("class ParameterKey")
        end = src.index("def encode_log_encode_request", start)
    except ValueError as exc:
        raise LookupError(
            "could not locate the ParameterKey enum body in redis_controller.py; "
            "the anchors this script relies on have moved"
        ) from exc
    return set(PY_MEMBER.findall(src[start:end]))


def cinepiraw_keys(repo: Path) -> tuple[set[str], set[str]]:
    """(macro keys, direct-call keys) that cinepi-raw touches.

    Returned separately because the split is informative: macro keys are the
    declared control surface, direct-call keys are ad-hoc reads/writes that
    never got a name in cinepi_state.hpp.
    """
    macros = set(CPP_DEFINE.findall(
        (repo / "cinepi/cinepi_state.hpp").read_text(errors="replace")))

    direct: set[str] = set()
    for path in repo.rglob("*"):
        if path.suffix not in (".cpp", ".hpp", ".h", ".c") or ".git" in path.parts:
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if line.lstrip().startswith("//"):
                continue
            direct.update(CPP_DIRECT.findall(line))
            direct.update(CPP_CONSTEXPR.findall(line))
    return macros, direct - macros


def referenced_in_cinemate(repo: Path, key: str) -> bool:
    """Does the literal appear anywhere in cinemate source, outside a comment?

    Deliberately generous: matches the bare quoted string anywhere in .py or
    .html under src/ and services/. A key reached only through a module-level
    constant still counts, because the literal is defined somewhere.
    """
    needle_d, needle_s = f'"{key}"', f"'{key}'"
    for base in ("src", "services"):
        root = repo / base
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix not in (".py", ".html") or "__pycache__" in path.parts:
                continue
            try:
                for line in path.read_text(errors="replace").splitlines():
                    stripped = line.lstrip()
                    if stripped.startswith("#") or stripped.startswith("//"):
                        continue
                    if needle_d in line or needle_s in line:
                        return True
            except OSError:
                continue
    return False


# --- reporting --------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    here = Path(__file__).resolve()
    ap.add_argument("--cinemate", type=Path, default=here.parents[1],
                    help="cinemate repo root (default: inferred from this file)")
    ap.add_argument("--cinepi-raw", type=Path,
                    default=Path(os.environ.get("CINEPI_RAW_DIR", "../cinepi-raw")),
                    help="cinepi-raw repo root")
    ap.add_argument("--max-unreferenced", type=int, default=None,
                    help="exit 1 if MORE than N cinepi-raw keys are unreferenced "
                         "in cinemate. A ratchet: set it to today's count so a new "
                         "one fails, and lower it as the backlog is triaged. "
                         "Raising it is never the fix.")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any cinepi-raw key is unreferenced in cinemate")
    args = ap.parse_args()

    try:
        py = cinemate_keys(args.cinemate)
    except (OSError, LookupError) as exc:
        print(f"error: cannot read cinemate registry: {exc}", file=sys.stderr)
        return 2
    try:
        cpp_macros, cpp_direct = cinepiraw_keys(args.cinepi_raw)
        cpp = cpp_macros | cpp_direct
    except OSError as exc:
        print(f"error: cannot read cinepi-raw registry: {exc}", file=sys.stderr)
        print(f"       expected {args.cinepi_raw}/cinepi/cinepi_state.hpp", file=sys.stderr)
        return 2

    shared = sorted(py & cpp)
    cpp_only = sorted(cpp - py)
    py_only = sorted(py - cpp)

    print(f"cinemate   ParameterKey members    : {len(py)}")
    print(f"cinepi-raw CONTROL_KEY_ macros    : {len(cpp_macros)}")
    print(f"cinepi-raw direct/constexpr keys  : {len(cpp_direct)}   (no macro name)")
    print(f"cinepi-raw total                  : {len(cpp)}")
    print(f"shared (the visible contract)     : {len(shared)}")
    print()

    # cinepi-raw keys absent from the enum: are they referenced at all?
    unreferenced = [k for k in cpp_only if not referenced_in_cinemate(args.cinemate, k)]
    referenced = [k for k in cpp_only if k not in unreferenced]

    if unreferenced:
        print(f"cinepi-raw keys with NO reference anywhere in cinemate ({len(unreferenced)}):")
        for k in unreferenced:
            print(f"    {k}")
        print("    -> cinepi-raw handles or writes these; cinemate never mentions them.")
        print("       Not necessarily dead: reachable by hand with redis-cli, and some")
        print("       read as a deliberate tuning/telemetry surface. See F-027.")
        print()
    if referenced:
        print(f"cinepi-raw keys outside ParameterKey but referenced in cinemate ({len(referenced)}):")
        for k in referenced:
            print(f"    {k}")
        print("    -> reached as raw strings, bypassing the enum. See F-015.")
        print()
    if py_only:
        print(f"cinemate-only keys ({len(py_only)}) — expected: most state is cinemate's alone")
        print(f"    {', '.join(py_only)}")
        print()

    print("NOTE: counts are LOWER BOUNDS. Dynamically built keys (e.g. cinepi_ready_<port>)")
    print("      are invisible to pattern matching and appear in neither registry.")

    if args.max_unreferenced is not None and len(unreferenced) > args.max_unreferenced:
        print(f"\nFAIL: {len(unreferenced)} unreferenced cinepi-raw key(s), "
              f"limit {args.max_unreferenced}. A new one appeared -- find it above "
              f"rather than raising the limit.", file=sys.stderr)
        return 1

    if args.strict and unreferenced:
        print(f"\nFAIL (--strict): {len(unreferenced)} unreferenced cinepi-raw key(s).",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
