#!/usr/bin/env python3
"""Mechanical docs-vs-code checks for CineMate.

Written for S09 of the system review. Answers the questions about `docs/` that can be
answered without judgement, so the report can spend its words on the ones that need it.

Six checks, each independent:

  nav        mkdocs.yml nav entries vs files on disk, both directions
  links      internal markdown links vs their targets
  cites      `path/file.py:123` style code citations -- file exists? line in range?
  methods    method names in docs/controller-methods.md vs CinePiController
  keys       redis keys in docs/redis-keys.md vs the ParameterKey enum
  settings   dotted setting paths in docs/settings-json.md vs settings.jsonc + schema

Standard library only. Does not import the application, does not need a Raspberry Pi.

Usage:
    python3 system-review/harness/docs_drift_check.py [--repo PATH] [--only CHECK] [--strict]

Limitations, stated because the review's convention requires it:
  * A name appearing in prose is not proof it is documented *correctly* -- only that it
    exists. Semantic accuracy is a reading job, not a script's.
  * Code citations without a line number are checked for file existence only.
  * The settings check matches quoted or backticked dotted paths; a path written in prose
    without punctuation is invisible to it.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

DOCS = "docs"
MKDOCS = "mkdocs.yml"
CONTROLLER = "src/module/cinepi_controller.py"
REDIS_CTRL = "src/module/redis_controller.py"


# ---------------------------------------------------------------- helpers

def md_files(repo: Path) -> set[str]:
    return {str(p.relative_to(repo / DOCS)) for p in (repo / DOCS).rglob("*.md")}


def nav_entries(repo: Path) -> tuple[set[str], int]:
    """Referenced .md paths in the nav, and how many nav lines are commented out."""
    text = (repo / MKDOCS).read_text(encoding="utf-8")
    live, commented = set(), 0
    for line in text.splitlines():
        stripped = line.strip()
        m = re.search(r":\s*([A-Za-z0-9_./-]+\.md)\s*$", stripped)
        if not m:
            continue
        if stripped.startswith("#"):
            commented += 1
        else:
            live.add(m.group(1))
    return live, commented


def enum_members(repo: Path, cls: str) -> dict[str, str]:
    tree = ast.parse((repo / REDIS_CTRL).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            return {
                t.id: n.value.value
                for n in node.body if isinstance(n, ast.Assign)
                for t in n.targets
                if isinstance(t, ast.Name) and isinstance(n.value, ast.Constant)
                and isinstance(n.value.value, str)
            }
    return {}


def controller_methods(repo: Path) -> set[str]:
    tree = ast.parse((repo / CONTROLLER).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CinePiController":
            return {n.name for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return set()


# ---------------------------------------------------------------- checks

def check_nav(repo: Path) -> list[str]:
    on_disk = md_files(repo)
    live, commented = nav_entries(repo)
    out = [f"files on disk: {len(on_disk)} · live nav entries: {len(live)} · "
           f"commented-out nav lines: {commented}"]
    orphans = sorted(on_disk - live)
    out.append(f"UNREACHABLE from nav ({len(orphans)}):")
    for f in orphans:
        loc = len((repo / DOCS / f).read_text(encoding="utf-8").splitlines())
        flag = "  <-- EMPTY" if loc == 0 else ("  <-- real content" if loc > 100 else "")
        out.append(f"    {f:<36} {loc:>5} LOC{flag}")
    missing = sorted(live - on_disk)
    out.append(f"NAV POINTS AT MISSING FILES ({len(missing)}): {', '.join(missing) or '-'}")
    return out


LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+?)(?:#([^)\s]*))?\)")


def check_links(repo: Path) -> list[str]:
    broken = []
    total = 0
    for p in sorted((repo / DOCS).rglob("*.md")):
        body = p.read_text(encoding="utf-8")
        for m in LINK_RE.finditer(body):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            total += 1
            resolved = (p.parent / target).resolve()
            if not resolved.exists():
                broken.append(f"    {p.relative_to(repo / DOCS)} -> {target}")
    return [f"internal links checked: {total} · broken: {len(broken)}"] + sorted(broken)


CITE_RE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|sh|cpp|hpp|json|jsonc|yml|txt))"
                     r"(?::(\d+)(?:-(\d+))?)?`")


def check_cites(repo: Path) -> list[str]:
    """Do `file.py:123` style citations in docs resolve, and are the lines in range?

    Classify rather than false-positive. An earlier version reported 37 misses; every
    one was an absolute runtime path (/boot/firmware/config.txt, /home/pi/..., a
    libcamera source path) that is *correctly* absent from this repository. Those are
    documentation of the deployed system, not citations of it.
    """
    runtime, bad_file, bad_line, ok = [], [], [], 0
    for p in sorted((repo / DOCS).rglob("*.md")):
        for m in CITE_RE.finditer(p.read_text(encoding="utf-8")):
            ref, start = m.group(1), m.group(2)
            where = p.relative_to(repo / DOCS)
            if ref.startswith("/") or ref.startswith("src/ipa/"):
                runtime.append(ref)
                continue
            cands = [repo / ref] + list(repo.rglob(Path(ref).name))
            hit = next((c for c in cands if c.is_file()
                        and str(c).endswith(ref.lstrip("./"))), None)
            if hit is None:
                # A bare filename that exists nowhere in the repo is most often a
                # deployed artefact (config.txt, compile-raw.sh) rather than drift.
                (runtime if "/" not in ref else bad_file).append(
                    ref if "/" not in ref else f"    {where} -> {ref}")
                continue
            if start:
                n = len(hit.read_text(encoding="utf-8", errors="replace").splitlines())
                if int(start) > n:
                    bad_line.append(f"    {where} -> {ref}:{start}   (file has {n} lines)")
                    continue
            ok += 1
    return ([f"repo citations resolved: {ok} · unresolvable: {len(bad_file)} · "
             f"line out of range: {len(bad_line)}",
             f"runtime / external paths (expected absent): {len(runtime)} "
             f"-- {', '.join(sorted(set(runtime))[:6])}, ..."]
            + sorted(bad_file) + sorted(bad_line))


def check_methods(repo: Path) -> list[str]:
    doc = (repo / DOCS / "controller-methods.md").read_text(encoding="utf-8")
    named = set(re.findall(r"`([a-z_][a-z0-9_]*)\(", doc))
    real = controller_methods(repo)
    public = {m for m in real if not m.startswith("_")}
    missing = sorted(named - real)
    undocumented = sorted(public - named)
    return [
        f"names in controller-methods.md: {len(named)} · "
        f"CinePiController methods: {len(real)} ({len(public)} public)",
        f"DOCUMENTED BUT ABSENT on the controller ({len(missing)}): "
        f"{', '.join(missing) or '-'}",
        f"public but undocumented: {len(undocumented)} "
        f"(the doc says it covers 'the most useful ones', so this is scope, not drift)",
    ]


def check_keys(repo: Path) -> list[str]:
    """redis-keys.md is a markdown TABLE with unbackticked keys in column 1.

    An earlier version of this check matched only backticked lowercase words and
    reported 8 documented keys out of 84, contradicting F-014. It was wrong: the
    doc does not backtick them. It also reported `pip_cam0`/`pip_cam1` as
    documented-but-nonexistent keys -- they are *values* of hdmi_preview_source.
    Both were pattern-matching failures, not findings.
    """
    doc = (repo / DOCS / "redis-keys.md").read_text(encoding="utf-8")
    members = enum_members(repo, "ParameterKey")
    values = set(members.values())

    named: set[str] = set()
    for line in doc.splitlines():
        if not line.startswith("|") or line.startswith("|--") or "| Key " in line:
            continue
        cell = line.split("|")[1].strip()
        # cells like "width / height" and "lores_width / lores_height"
        for part in re.split(r"\s*/\s*", cell):
            part = part.strip().strip("`")
            if re.fullmatch(r"[a-z][a-z0-9_]*", part):
                named.add(part)

    documented = named & values
    orphan = sorted(named - values)
    undocumented = sorted(values - named)
    return [
        f"ParameterKey members: {len(members)} · rows in redis-keys.md: {len(named)}",
        f"documented and real: {len(documented)} · UNDOCUMENTED: {len(undocumented)}",
        f"  {', '.join(undocumented)}",
        f"NAMED IN DOCS BUT NOT IN ParameterKey ({len(orphan)}): {', '.join(orphan) or '-'}",
        "  (cinepi-raw-side keys legitimately live outside ParameterKey -- cross-check "
        "against redis_key_diff.py before calling one of these an orphan doc)",
    ]


def check_settings(repo: Path) -> list[str]:
    """settings-json.md names sections with `##` / `###` HEADINGS, not dotted paths.

    An earlier version matched backticked dotted paths and found 9 in a 611-line
    document, two of which were filenames. The doc is structured by heading.
    """
    sys.path.insert(0, str(repo / "src"))
    from module.config_loader import strip_jsonc  # noqa: E402
    live = json.loads(strip_jsonc((repo / "settings.jsonc").read_text(encoding="utf-8")))

    tops = set(live) - {"$schema"}
    seconds = {k for t in tops if isinstance(live[t], dict) for k in live[t]}

    doc = (repo / DOCS / "settings-json.md").read_text(encoding="utf-8")
    h2 = {m.group(1) for m in re.finditer(r"^##\s+([a-z_][a-z0-9_]*)\s*$", doc, re.M)}
    h3 = {m.group(1) for m in re.finditer(r"^###\s+([a-z_][a-z0-9_]*)\s*$", doc, re.M)}

    return [
        f"top-level sections in settings.jsonc: {len(tops)} · `##` headings: {len(h2)}",
        f"  UNDOCUMENTED top-level ({len(tops - h2)}): {', '.join(sorted(tops - h2)) or '-'}",
        f"  HEADING WITH NO SECTION ({len(h2 - tops)}): {', '.join(sorted(h2 - tops)) or '-'}",
        f"second-level keys: {len(seconds)} · `###` headings: {len(h3)}",
        f"  HEADING WITH NO KEY ({len(h3 - seconds)}): "
        f"{', '.join(sorted(h3 - seconds)) or '-'}",
        "  (a `###` heading may legitimately document a nested block one level deeper; "
        "treat these as candidates, not verdicts)",
    ]


CHECKS = {"nav": check_nav, "links": check_links, "cites": check_cites,
          "methods": check_methods, "keys": check_keys, "settings": check_settings}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", type=Path)
    ap.add_argument("--only", choices=sorted(CHECKS))
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    repo = args.repo.resolve()

    names = [args.only] if args.only else list(CHECKS)
    for name in names:
        print(f"===== {name} " + "=" * (60 - len(name)))
        for line in CHECKS[name](repo):
            print(line)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
