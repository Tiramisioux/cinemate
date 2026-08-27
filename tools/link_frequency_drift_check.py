#!/usr/bin/env python3
"""Fail if link-frequency data gets copied out of the sensor database.

resources/sensors.json is the one place the values live. Python reads it and
ships the menus to the settings editor, so the page renders whatever it is
given and knows none of the numbers itself.

That arrangement is easy to undo by accident: a hardcoded value in the
template, or a fallback list "just in case the fetch is slow", and there are
two copies again -- drifting silently, exactly like the ACTION_METHODS
catalogue. A comment does not catch that. This does.

The check is deliberately about *data*, not logic. cfgOverlayLine() in
JavaScript necessarily mirrors overlay_line_for() in Python, because the
drawer renders a live preview of a line the server will write; that mirror is
small, stable, and covered by tests on both sides. A copied frequency table
is the failure mode worth gating.

Usage: python3 tools/link_frequency_drift_check.py [--repo PATH] [--strict]
Exit 1 on drift when --strict, else 0 with the findings printed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TEMPLATE = "src/module/app/templates/settings_editor.html"
DATABASE = "resources/sensors.json"


def link_frequency_values(database: dict) -> dict[int, str]:
    """Every hz value in the database, mapped to the sensor it came from."""
    found: dict[int, str] = {}
    for name, entry in database.get("sensors", {}).items():
        block = entry.get("link_frequency")
        if not isinstance(block, dict):
            continue
        for key in ("options", "excluded"):
            for option in block.get(key, []):
                if isinstance(option, dict) and isinstance(option.get("hz"), int):
                    found.setdefault(option["hz"], name)
        default = block.get("default_hz")
        if isinstance(default, int):
            found.setdefault(default, name)
    return found


def scan(repo: Path) -> list[str]:
    database = json.loads((repo / DATABASE).read_text(encoding="utf-8"))
    values = link_frequency_values(database)
    if not values:
        return [f"{DATABASE} defines no link frequencies at all -- has the block been removed?"]

    text = (repo / TEMPLATE).read_text(encoding="utf-8")
    # Strip comments so an explanatory "720 MHz default" in prose doesn't trip
    # the check. Only live code is a duplication risk.
    code = re.sub(r"/\*.*?\*/", "", text, flags=re.S)

    problems = []
    for hz, sensor in sorted(values.items()):
        # Bare integer literal, not part of a longer number.
        if re.search(r"(?<![\d.])" + str(hz) + r"(?![\d.])", code):
            problems.append(
                f"{TEMPLATE} hardcodes {hz} ({sensor}). Link frequencies belong in "
                f"{DATABASE}; the page is served them via boot_config.link_frequency_menus()."
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    problems = scan(repo)

    print("===== link frequency: one copy only ==============================")
    if problems:
        for problem in problems:
            print(f"  DRIFT: {problem}")
        print(f"\n{len(problems)} hardcoded value(s) found.")
        return 1 if args.strict else 0

    database = json.loads((repo / DATABASE).read_text(encoding="utf-8"))
    counted = len(link_frequency_values(database))
    print(f"  {counted} frequencies in {DATABASE}, none restated in the template. OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
