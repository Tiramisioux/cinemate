#!/usr/bin/env python3
"""Extract the GUI field inventory from source, mechanically.

Written for S07 of the CineMate system review. Answers one question:
*which fields does each GUI surface handle, and where does each one come from?*

Why a script and not a reading: the HDMI GUI's field set is a 370-line dict
builder, the web template is 965 lines of HTML+JS, and the settings editor is
3706. Hand-counting those was going to be wrong, and this review has already
been caught over- and under-counting by grep four times.

No dependencies beyond the standard library. Does not import the application,
does not need a Raspberry Pi, does not need redis. Pure `ast` + text scan.

Usage:
    python3 system-review/harness/gui_field_extract.py [--repo PATH] [--format md|text]

Known limitations, stated because the review's convention requires it:
  * Field names built dynamically (f-strings, computed keys) are invisible here.
    Every count below is a LOWER BOUND.
  * "Consumed by the web GUI" is a whole-word text match of the field name in
    the template. It proves the name appears; it does not prove it is rendered.
  * The settings-editor scan finds `data-*` attributes and quoted dotted
    setting paths. A path assembled at runtime will be missed.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Surface 1 — HDMI GUI (PIL raster to /dev/fb0)
# --------------------------------------------------------------------------

SIMPLE_GUI = "src/module/simple_gui.py"
VALUES_BUILDER = "populate_values"


def hdmi_fields(repo: Path) -> dict[str, int]:
    """Field name -> line, for the dict `populate_values` returns.

    Only the dict actually bound to the local `values` (and later
    `values[...] = ...` stores) counts. An earlier version of this walked every
    ast.Dict inside the function and picked up the nested colour table, which
    reported `normal`, `lock` and `low_voltage` as GUI fields. They are not.
    """
    tree = ast.parse((repo / SIMPLE_GUI).read_text(encoding="utf-8"))
    fn = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef) and n.name == VALUES_BUILDER),
        None,
    )
    if fn is None:
        raise SystemExit(f"{VALUES_BUILDER} not found in {SIMPLE_GUI}")

    fields: dict[str, int] = {}

    # `values = { ... }` — the top-level literal
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            if any(isinstance(t, ast.Name) and t.id == "values" for t in node.targets):
                for k in node.value.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        fields.setdefault(k.value, k.lineno)

    # `values["..."] = ...` — later stores
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (isinstance(t, ast.Subscript)
                        and isinstance(t.value, ast.Name) and t.value.id == "values"
                        and isinstance(t.slice, ast.Constant)
                        and isinstance(t.slice.value, str)):
                    fields.setdefault(t.slice.value, node.lineno)

    return fields


def hdmi_providers(repo: Path) -> dict[str, str]:
    """Field name -> a coarse label for where its value comes from.

    Deliberately coarse. Anything that is not a recognisable provider call is
    reported as `derived`, because claiming more than that would need dataflow
    analysis this script does not do.
    """
    text = (repo / SIMPLE_GUI).read_text(encoding="utf-8").splitlines()
    fields = hdmi_fields(repo)
    out: dict[str, str] = {}
    for name, lineno in fields.items():
        line = text[lineno - 1] if 0 < lineno <= len(text) else ""
        if "redis_controller.get_value" in line:
            out[name] = "redis"
        elif re.search(r'"\s*[^"]*"\s*,?\s*$', line) and ":" in line and not any(
            c in line for c in "()[]"
        ):
            out[name] = "literal"
        elif "self._slow_values" in line:
            out[name] = "slow-poll"
        elif "Utils." in line:
            out[name] = "host"
        elif "self." in line:
            out[name] = "gui-internal"
        else:
            out[name] = "derived"
    return out


# --------------------------------------------------------------------------
# Surface 2 — Web GUI (HTML + Socket.IO)
# --------------------------------------------------------------------------

WEB_TEMPLATE = "src/module/app/templates/template.html"
# The push channel is emitted from THREE modules, not one. An earlier version of
# this script scanned only the first two and reported `reload_stream` and
# `resolution_change` as handled-but-never-emitted. They are emitted from
# app/__init__.py. That miss is itself the finding (F-209): nothing in the repo
# lists what the Socket.IO channel carries.
EVENT_SOURCES = (
    "src/module/app/main/events.py",
    "src/module/simple_gui.py",
    "src/module/app/__init__.py",
)
EVENTS = EVENT_SOURCES[0]


def web_consumed(repo: Path, names: list[str]) -> set[str]:
    """Which HDMI field names appear, as whole words, in the web template."""
    src = (repo / WEB_TEMPLATE).read_text(encoding="utf-8")
    return {n for n in names if re.search(r"\b%s\b" % re.escape(n), src)}


def socket_events(repo: Path) -> dict[str, list[str]]:
    """Socket.IO event names emitted by the server and handled by the browser."""
    page = (repo / WEB_TEMPLATE).read_text(encoding="utf-8")
    emitted: set[str] = set()
    for rel in EVENT_SOURCES:
        src = (repo / rel).read_text(encoding="utf-8")
        emitted |= set(re.findall(r"(?:socketio\.)?emit\(\s*['\"]([a-z_]+)['\"]", src))
        emitted |= set(re.findall(
            r"_emit_socketio_event\(\s*\n?\s*['\"]([a-z_]+)['\"]", src))
    handled = set(re.findall(r"socket\.on\(\s*['\"]([a-z_]+)['\"]", page))
    return {
        "emitted_by_server": sorted(emitted),
        "handled_by_browser": sorted(handled),
        "emitted_never_handled": sorted(emitted - handled),
        "handled_never_emitted": sorted(handled - emitted),
    }


# --------------------------------------------------------------------------
# Surface 3 — Settings editor
# --------------------------------------------------------------------------

SETTINGS_EDITOR_PY = "src/module/app/settings_editor.py"
SETTINGS_EDITOR_HTML = "src/module/app/templates/settings_editor.html"
CONTROLLER = "src/module/cinepi_controller.py"


def controller_methods(repo: Path) -> set[str]:
    """Public method names on CinePiController -- the reflective-dispatch targets."""
    tree = ast.parse((repo / CONTROLLER).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CinePiController":
            return {
                n.name for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not n.name.startswith("_")
            }
    return set()


def editor_method_names(repo: Path) -> set[str]:
    """Method-name strings the settings editor offers as actions.

    F-118 is exactly this set diverging from controller_methods(): the
    catalogue offers `set_log`, the method is `set_log_encode`, and the button
    silently does nothing.
    """
    names: set[str] = set()
    for rel in (SETTINGS_EDITOR_PY, SETTINGS_EDITOR_HTML):
        src = (repo / rel).read_text(encoding="utf-8")
        names |= set(re.findall(r"['\"](set_[a-z0-9_]+|inc_[a-z0-9_]+|dec_[a-z0-9_]+)['\"]", src))
    return names


def settings_paths(repo: Path) -> set[str]:
    """Dotted setting paths the editor references as string literals."""
    src = (repo / SETTINGS_EDITOR_HTML).read_text(encoding="utf-8")
    return set(re.findall(r"['\"]([a-z_]+(?:\.[a-z_0-9]+){1,4})['\"]", src))


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", type=Path)
    ap.add_argument("--format", choices=("md", "text", "json"), default="text")
    args = ap.parse_args()
    repo = args.repo.resolve()

    fields = hdmi_fields(repo)
    provs = hdmi_providers(repo)
    consumed = web_consumed(repo, list(fields))
    events = socket_events(repo)
    methods = controller_methods(repo)
    offered = editor_method_names(repo)

    data = {
        "hdmi_field_count": len(fields),
        "hdmi_fields": {k: {"line": v, "provider": provs[k],
                            "in_web_template": k in consumed}
                        for k, v in sorted(fields.items())},
        "hdmi_only": sorted(set(fields) - consumed),
        "socket_events": events,
        "controller_public_methods": len(methods),
        "editor_offered_names": sorted(offered),
        "offered_but_missing_on_controller": sorted(offered - methods),
    }

    if args.format == "json":
        print(json.dumps(data, indent=2))
        return 0

    b = "**" if args.format == "md" else ""
    print(f"{b}HDMI GUI ({SIMPLE_GUI}::{VALUES_BUILDER}){b}")
    print(f"  fields (lower bound): {len(fields)}")
    from collections import Counter
    for prov, n in Counter(provs.values()).most_common():
        print(f"    {prov:<14} {n}")
    print(f"  also named in the web template: {len(consumed)}")
    print(f"  HDMI-only (not named in the web template): {len(data['hdmi_only'])}")
    for n in data["hdmi_only"]:
        print(f"    {n}")
    print()
    print(f"{b}Socket.IO channel{b}")
    for k, v in events.items():
        print(f"  {k}: {', '.join(v) if v else '(none)'}")
    print()
    print(f"{b}Reflective dispatch{b}")
    print(f"  CinePiController public methods: {len(methods)}")
    print(f"  names the settings editor offers: {len(offered)}")
    bad = data["offered_but_missing_on_controller"]
    print(f"  offered but ABSENT on the controller: {len(bad)}")
    for n in bad:
        print(f"    {n}   <-- silently does nothing (cf. F-118)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
