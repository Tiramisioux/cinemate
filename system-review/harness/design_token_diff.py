#!/usr/bin/env python3
"""Compare the HDMI GUI's colour constants against the web GUI's CSS custom properties.

Written for S08 of the CineMate system review, to put a number on F-007 and to give
ADR-001 option B a concrete cost. It is also the check option B would need to *stay* true:
right now the two sides are kept in agreement by a comment, and this review has watched
three hand-sync comments drift.

Two sources:
  Python  src/module/simple_gui.py   module-level *_COLOR constants + the self.colors table
  CSS     src/module/app/templates/template.html   :root { --token: rgb(...) }

Pairing is by the comment the CSS already carries -- `--drop: rgb(120,40,180); /*
DROP_WARNING_COLOR */` names its own counterpart. Tokens with no such comment are matched
by value, and reported separately so an unannotated match is never mistaken for a
declared one.

Usage:
    python3 system-review/harness/design_token_diff.py [--repo PATH] [--strict]

    --strict   exit 1 if any annotated pair disagrees.

Limitations, stated because the review's convention requires it:
  * Only literal `rgb(r, g, b)` and `(r, g, b)` tuples are compared. Named CSS colours
    (`lightgreen`), hex (`#000`) and Python string colours (`"magenta"`) are listed as
    uncomparable rather than silently skipped.
  * A value match is not proof of intent. Two tokens can share a value by coincidence;
    the annotated pairs are the contract, the rest is a hint.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

SIMPLE_GUI = "src/module/simple_gui.py"
TEMPLATE = "src/module/app/templates/template.html"


def python_colors(repo: Path) -> tuple[dict[str, tuple], dict[str, str]]:
    """(NAME -> rgb tuple, NAME -> uncomparable literal) for *_COLOR bindings.

    Walks the whole tree, not just module level. ZOOM_HIGHLIGHT_COLOR is a
    function-local at simple_gui.py:1226; an earlier version of this script only
    read module scope, reported the CSS comment naming it as pointing at nothing,
    and would have shipped a false drift finding.
    """
    tree = ast.parse((repo / SIMPLE_GUI).read_text(encoding="utf-8"))
    rgb: dict[str, tuple] = {}
    other: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if not (isinstance(t, ast.Name) and "COLOR" in t.id):
                continue
            v = node.value
            if isinstance(v, ast.Tuple) and len(v.elts) == 3 and all(
                isinstance(e, ast.Constant) and isinstance(e.value, int) for e in v.elts
            ):
                rgb[t.id] = tuple(e.value for e in v.elts)
            elif isinstance(v, ast.Constant):
                other[t.id] = repr(v.value)
    return rgb, other


def python_table_colors(repo: Path) -> dict[str, tuple]:
    """The `self.colors` field table: field -> its "normal" rgb, where literal."""
    tree = ast.parse((repo / SIMPLE_GUI).read_text(encoding="utf-8"))
    out: dict[str, tuple] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)):
            continue
        if not any(isinstance(t, ast.Attribute) and t.attr == "colors" for t in node.targets):
            continue
        for k, v in zip(node.value.keys, node.value.values):
            if not (isinstance(k, ast.Constant) and isinstance(v, ast.Dict)):
                continue
            for kk, vv in zip(v.keys, v.values):
                # Some entries carry an alpha channel -- "lock" is (255, 0, 0, 255).
                # Compare on RGB and drop alpha rather than skipping the row.
                if (isinstance(kk, ast.Constant) and kk.value == "normal"
                        and isinstance(vv, ast.Tuple) and len(vv.elts) in (3, 4)
                        and all(isinstance(e, ast.Constant) and isinstance(e.value, int)
                                for e in vv.elts)):
                    out[k.value] = tuple(e.value for e in vv.elts[:3])
    return out


TOKEN_RE = re.compile(
    r"--([a-z0-9-]+)\s*:\s*([^;]+?)\s*;(?:\s*/\*\s*(.*?)\s*\*/)?", re.I)
RGB_RE = re.compile(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", re.I)


def css_tokens(repo: Path) -> list[tuple[str, str, str | None]]:
    """[(token, raw value, trailing comment or None)] from the first :root block."""
    src = (repo / TEMPLATE).read_text(encoding="utf-8")
    start = src.find(":root")
    if start < 0:
        raise SystemExit("no :root block in " + TEMPLATE)
    block = src[start:src.find("}", start)]
    return [(m.group(1), m.group(2).strip(), (m.group(3) or None))
            for m in TOKEN_RE.finditer(block)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", type=Path)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    repo = args.repo.resolve()

    py_rgb, py_other = python_colors(repo)
    table = python_table_colors(repo)
    tokens = [t for t in css_tokens(repo) if RGB_RE.search(t[1]) or "#" in t[1]
              or t[1].isalpha()]

    colour_tokens = [t for t in tokens if not t[0].startswith(
        ("gap", "value-size", "label-size", "box-size", "box-height"))]

    annotated, dangling, unannotated, uncomparable = [], [], [], []
    for name, raw, comment in colour_tokens:
        m = RGB_RE.search(raw)
        if not m:
            uncomparable.append((name, raw, comment))
            continue
        val = tuple(int(g) for g in m.groups())
        key = (comment or "").upper().replace(" ", "_")
        if key in py_rgb:
            annotated.append((name, val, comment, py_rgb[key]))
        elif comment and key.endswith("_COLOR"):
            # A comment that names a constant which does not exist. Reported
            # separately: "the comment points at nothing" is a different defect
            # from "there is no comment".
            dangling.append((name, val, comment))
        else:
            unannotated.append((name, val, comment))

    print("Python module colour constants : %d comparable, %d not (%s)"
          % (len(py_rgb), len(py_other), ", ".join(py_other) or "-"))
    print("Python self.colors field table : %d fields" % len(table))
    print("CSS custom properties (colour) : %d" % len(colour_tokens))
    print()

    print("ANNOTATED pairs -- the CSS names its Python counterpart (%d):" % len(annotated))
    bad = 0
    for name, val, comment, pyval in annotated:
        ok = val == pyval
        bad += not ok
        print("  %-16s %-18s %s %-18s %s"
              % ("--" + name, str(val), "==" if ok else "!=", str(pyval),
                 comment + ("" if ok else "   <-- DRIFTED")))
    print()

    if dangling:
        print("DANGLING annotations -- comment names a constant that does not exist (%d):"
              % len(dangling))
        for name, val, comment in dangling:
            print("  %-16s %-18s /* %s */   <-- points at nothing" % ("--" + name, str(val), comment))
        print()

    print("UNANNOTATED tokens -- matched by value only, or unmatched (%d):"
          % len(unannotated))
    by_val = {v: k for k, v in py_rgb.items()}
    for name, val, comment in unannotated:
        hint = by_val.get(val)
        if hint is None:
            fields = [f for f, v in table.items() if v == val]
            hint = ("self.colors[%s]" % ", ".join(sorted(fields)[:3])) if fields else None
        print("  %-16s %-18s %s" % ("--" + name, str(val),
                                    ("~ " + hint) if hint else "no Python counterpart found"))
    print()

    if uncomparable:
        print("NOT COMPARABLE -- named or hex colours (%d):" % len(uncomparable))
        for name, raw, comment in uncomparable:
            print("  %-16s %s" % ("--" + name, raw))
        print()

    matched = sum(1 for _, val, _ in unannotated
                  if val in {v for v in py_rgb.values()} or val in set(table.values()))
    print("VERDICT: %d colour tokens. %d carry a resolvable annotation (%d drifted); "
          "%d dangle; %d rely on a value match alone (%d of those resolve); "
          "%d not comparable."
          % (len(colour_tokens), len(annotated), bad, len(dangling),
             len(unannotated), matched, len(uncomparable)))
    print("Sync mechanism today is a comment. Three hand-sync comments in this review have")
    print("drifted (F-260, F-183, F-220). See F-007 and ADR-001 option B.")

    if args.strict and (bad or dangling):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
