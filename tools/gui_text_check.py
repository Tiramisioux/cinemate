#!/usr/bin/env python3
"""The settings editor's copy and its template must agree.

The editor's prose lives in `resources/gui-text/*.md`; the template
(`src/module/app/templates/settings_editor.html`) carries only `t('key')`
lookups. Three ways that can rot, all of them silent in a browser:

1. The template asks for a key the markdown does not define. The page renders
   a red `[missing text: ...]` marker -- loud, but only to whoever opens that
   pane.
2. The markdown defines a string nothing asks for. Someone edits it for an
   afternoon and wonders why the page never changes.
3. Someone adds a new sentence straight into the template instead of into the
   markdown. Nothing breaks; the copy just quietly stops living in one place,
   which is the whole thing this arrangement exists to prevent.

All three are gated at zero. Run from the repository root:

    python3 tools/gui_text_check.py [--strict]

`--strict` is accepted for symmetry with the other drift checks; this one has
no ratchet, so it behaves the same either way.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def _load_gui_text_reader():
    """Import `gui_text.py` without executing the `module.app` package.

    `gui_text.py` needs nothing but the standard library, but it lives inside
    `module/app/`, whose `__init__.py` imports flask and flask_socketio to
    build the web app. A plain `from module.app.gui_text import ...` therefore
    drags a web framework into a check that only reads two text files -- and
    the drift job installs jsonschema and nothing else, so it died on
    `ModuleNotFoundError: No module named 'flask'` rather than on any drift.

    Loading the file directly by path keeps this dependency-free, which is the
    standard these tools/ checks are held to: they have to run in CI without a
    fragile install step.
    """
    path = DEFAULT_ROOT / "src" / "module" / "app" / "gui_text.py"
    spec = importlib.util.spec_from_file_location("_gui_text", path)
    if spec is None or spec.loader is None:          # pragma: no cover
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_gui_text


load_gui_text = _load_gui_text_reader()

TEMPLATE_PATH = "src/module/app/templates/settings_editor.html"
GUI_TEXT_PATH = "resources/gui-text"

# If the extraction below ever stops matching the markup, it must fail rather
# than compare two empty sets and pass forever. 200 is comfortably under the
# current count and comfortably over anything a real edit would remove.
MINIMUM_LOOKUPS = 200

LOOKUP = re.compile(r"\{\{\s*t\('([^']+)'\)\s*\}\}")

# Text these ids hold in the template is a first paint that JavaScript
# immediately rewrites from its own string. Moving it into the markdown would
# make two sources for one sentence, which is the opposite of the point.
JS_OWNED_IDS = {"cfgStatusText", "statusText", "pbLockBody", "pbLockTitle"}


def template_body(html: str) -> str:
    """The markup, without the stylesheet and scripts."""
    body = html[html.index('<div class="app skin-hud"'):]
    body = re.sub(r"<script\b.*?</script>", "", body, flags=re.S | re.I)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    # The lookups themselves sit between tags and would otherwise read as the
    # very prose this is looking for. Same reasoning for {% ... %} control-flow
    # tags (the settings-editor DNG-thumbnails card's {% for %} over
    # thumbnail_choices, added alongside cinemate's own JPEG thumbnail mode --
    # the template's first use of Jinja control flow, everything before it
    # being plain {{ t('key') }} lookups): a "for value, label in ..." is
    # Jinja syntax, not a hardcoded sentence, and must not read as either.
    body = re.sub(r"\{%.*?%\}", "", body, flags=re.S)
    return re.sub(r"\{\{.*?\}\}", "", body, flags=re.S)


def stray_prose(body: str) -> list[str]:
    """Sentences sitting in the template instead of in the markdown."""
    # Drop the elements whose text is JS-owned, then every remaining tag, and
    # look at what text is left between them.
    for element_id in JS_OWNED_IDS:
        body = re.sub(
            rf"<(\w+)[^>]*\bid=\"{element_id}\"[^>]*>.*?</\1>", "", body, flags=re.S
        )
    found = []
    for chunk in re.split(r"<[^>]+>", body):
        text = re.sub(r"\s+", " ", chunk).strip()
        if len(text) >= 35 and " " in text:
            found.append(text)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(DEFAULT_ROOT), help="repository root to check")
    parser.add_argument("--strict", action="store_true", help="accepted for symmetry; no ratchet here")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    template = root / TEMPLATE_PATH
    html = template.read_text(encoding="utf-8")
    body = template_body(html)

    asked = set(LOOKUP.findall(html))
    have = set(load_gui_text(root / GUI_TEXT_PATH))

    problems = []

    if len(asked) < MINIMUM_LOOKUPS:
        problems.append(
            f"only {len(asked)} t('...') lookups found in {template.name}, expected at least "
            f"{MINIMUM_LOOKUPS}. Suspect this extractor before the template: if the lookup "
            f"syntax changed, this check is comparing almost nothing and would otherwise pass."
        )

    for key in sorted(asked - have):
        problems.append(f"template asks for a key no markdown file defines: {key}")
    for key in sorted(have - asked):
        problems.append(f"markdown defines a string the template never asks for: {key}")
    for text in stray_prose(body):
        problems.append(f"prose hardcoded in the template instead of resources/gui-text/: {text[:90]!r}")

    if problems:
        print(f"gui text check: {len(problems)} problem(s)")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"gui text check: {len(asked)} strings, template and resources/gui-text/ agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
