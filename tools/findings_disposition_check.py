#!/usr/bin/env python3
"""
findings_disposition_check.py -- every row in FINDINGS.md must carry one of
five dispositions.

Why this exists
----------------
B10.1 added a `disposition` column and filled all 228 rows: `fixed` /
`guarded` / `accepted` / `superseded` / `strength`, and nothing else. Most of
those are "accepted, no action" -- a legitimate outcome, since not every
finding warrants a code change. Writing it down is what separates an
accepted risk from a forgotten one. This check is the part that keeps that
true after B10.1: a new finding appended without a disposition, or a typo'd
value, fails CI instead of silently reopening the gap this batch closed.

"Named in a batch" (system-review/deliverables/REMEDIATION-PLAN.md) is a
different, weaker property than "has a disposition" -- a finding can be
planned for future work and still carry `accepted` today. This check only
enforces the latter.

Usage
-----
    python3 tools/findings_disposition_check.py [--repo PATH]

Exit codes: 0 ok / 1 a row is missing a disposition or has an invalid one.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FINDINGS = "system-review/FINDINGS.md"
ALLOWED = {"fixed", "guarded", "accepted", "superseded", "strength"}

ROW_RE = re.compile(r"^\|\s*(F-\d{3})\s*\|(.*)\|\s*$")


def check(repo: Path) -> int:
    path = repo / FINDINGS
    text = path.read_text(encoding="utf-8")

    header_line = next(
        (line for line in text.splitlines() if line.strip().startswith("| id ")), None
    )
    if header_line is None or "disposition" not in header_line:
        print(f"{FINDINGS}: no `disposition` column in the header row")
        return 1

    missing: list[str] = []
    invalid: list[tuple[str, str]] = []
    seen: set[str] = set()

    for line in text.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        fid, rest = m.group(1), m.group(2)
        seen.add(fid)
        cells = [c.strip() for c in rest.split("|")]
        disposition = cells[-1] if cells else ""
        if not disposition:
            missing.append(fid)
        elif disposition not in ALLOWED:
            invalid.append((fid, disposition))

    if missing:
        print(f"MISSING disposition ({len(missing)}): {', '.join(missing)}")
    if invalid:
        print(f"INVALID disposition ({len(invalid)}):")
        for fid, val in invalid:
            print(f"  {fid}: {val!r} -- must be one of {sorted(ALLOWED)}")

    if not missing and not invalid:
        print(f"findings_disposition_check: {len(seen)} findings, all dispositioned")
        return 0
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", type=Path)
    args = ap.parse_args()
    return check(args.repo.resolve())


if __name__ == "__main__":
    sys.exit(main())
