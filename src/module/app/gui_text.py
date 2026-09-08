"""The settings editor's copy, read from resources/gui-text/ at startup.

Every heading and description string the settings editor shows lives in the
markdown files under `resources/gui-text/`, not in the template. The template
asks for each one by key -- `{{ t('card.system.welcome.show.help') }}` -- and
this module is what answers.

The point is that the copy has exactly one home. It used to live only in
`templates/settings_editor.html`, which meant editing a sentence meant editing
a 6,500-line HTML file, and nothing could check that a description still
described the setting it sat under. Now the prose is in markdown a person can
read end to end, and `tools/gui_text_check.py` gates the two sides against
each other in CI.

Read once, when the Flask app is built (see `app/__init__.py`). Changing a
string means restarting CineMate -- the same as changing anything else in
`src/`.

Markdown shape, per file:

    ### Show welcome message         <- the heading line: the label
    <!-- key: card.system.welcome.show -->
                                     <- the paragraph: the description
    Displays a greeting over the image for a few seconds after boot.

The key prefix decides what the two halves mean; see `_ROLES` below and
`resources/gui-text/README.md` for the operator-facing version of the same
table.
"""

import html
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

GUI_TEXT_DIR = "resources/gui-text"

# key prefix -> (name for the heading line, name for the paragraph).
# None means that half is not text -- a note box has no heading of its own,
# a sidebar link has no paragraph.
_ROLES = {
    "tab": ("label", "hint"),
    "rail": ("title", "blurb"),
    "raillink": ("label", None),
    "pane": ("heading", "sub"),
    "card": ("label", "help"),
    "caption": (None, None),  # handled separately: one line, "·" separated
    "warn": (None, "body"),
    "note": (None, "body"),
    "help": (None, "body"),
    "text": (None, "body"),
}

_KEY_LINE = re.compile(r"^<!--\s*key:\s*([A-Za-z0-9_.\-]+)(?:\s+·[^>]*)?\s*-->\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
# "_(no pane description)_" and friends: an editor's note that this string is
# deliberately absent, not the string itself.
_ABSENT = re.compile(r"^_\(.*\)_$")

_MONO = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)(?:\{([^}]*)\})?")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def render_inline(text: str) -> str:
    """Markdown-ish inline text to the HTML the template used to hold.

    Escaped first, so a stray `<` in someone's sentence renders as a `<`
    rather than opening a tag. Mono runs are substituted before the emphasis
    patterns so a `*` inside backticks is left alone.
    """
    out = html.escape(text, quote=False)
    out = _MONO.sub(lambda m: f'<span class="mono">{m.group(1)}</span>', out)
    out = _LINK.sub(_link_html, out)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _ITALIC.sub(r"<em>\1</em>", out)
    return out


def _link_html(match: re.Match) -> str:
    """`[label](href){attrs}` -> an anchor, attributes and all.

    The trailing brace group carries whatever the anchor needs beyond href --
    `data-nav` for the sidebar's scrollspy, `data-open-config` for the button
    that opens the reconstructed config.txt. It is written out rather than
    inferred from the href because guessing it wrong produces a link that
    looks right and does nothing.
    """
    label, href, attrs = match.group(1), match.group(2), match.group(3)
    extra = f" {attrs.strip()}" if attrs and attrs.strip() else ""
    return f'<a href="{html.escape(href, quote=True)}"{extra}>{label}</a>'


def _blocks(lines: list[str]):
    """Yield (key, heading, body) for every keyed block in one file."""
    heading = None
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if match:
            heading = match.group(2)
            continue
        key_match = _KEY_LINE.match(line)
        if not key_match:
            continue
        body_lines = []
        for following in lines[index + 1:]:
            stripped = following.strip()
            if not stripped and not body_lines:
                continue  # the blank line between the key and its paragraph
            if not stripped:
                break
            if _HEADING.match(following) or _KEY_LINE.match(following) or stripped == "---":
                break
            body_lines.append(stripped)
        body = " ".join(body_lines)
        if _ABSENT.match(body):
            body = ""
        yield key_match.group(1), heading, body
        heading = None


def load_gui_text(directory: Path | str | None = None) -> dict[str, str]:
    """Parse every markdown file in the gui-text directory into {key: html}.

    A missing or unreadable directory warns and returns what it has rather
    than raising: a camera that cannot render its settings page is still a
    camera that records, and the page itself shows the misses loudly (see
    `lookup`). A duplicate key is a different matter -- it means two files
    disagree about one string, so it warns and the first one wins.
    """
    if directory is None:
        directory = Path(__file__).resolve().parents[3] / GUI_TEXT_DIR
    directory = Path(directory)

    try:
        files = sorted(p for p in directory.glob("*.md") if p.name != "README.md")
    except OSError as exc:
        logger.warning("GUI text directory unavailable (%s): %s", directory, exc)
        return {}
    if not files:
        logger.warning("No GUI text files found in %s", directory)
        return {}

    text: dict[str, str] = {}
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("GUI text file unreadable (%s): %s", path, exc)
            continue
        for key, heading, body in _blocks(lines):
            prefix = key.split(".", 1)[0]
            if prefix == "caption":
                for position, caption in enumerate(_captions(body)):
                    _put(text, f"{key}.{position}", render_inline(caption), path)
                continue
            heading_role, body_role = _ROLES.get(prefix, (None, None))
            if heading_role and heading:
                _put(text, f"{key}.{heading_role}", render_inline(heading), path)
            if body_role and body:
                _put(text, f"{key}.{body_role}", render_inline(body), path)

    logger.info("Loaded %d GUI strings from %s", len(text), directory)
    return text


def _captions(body: str) -> list[str]:
    """The captions line is one italic run of '·'-separated control labels."""
    return [part.strip() for part in body.strip("*").split("·") if part.strip()]


def _put(text: dict[str, str], key: str, value: str, path: Path) -> None:
    if key in text:
        logger.warning("GUI text key %s defined twice (%s); keeping the first", key, path.name)
        return
    text[key] = value


def lookup(text: dict[str, str], key: str) -> str:
    """The template's `t()`. A miss is shown, not swallowed.

    Returning the key in a visible marker means a typo or a deleted block
    shows up as a legible fault in the page instead of a blank space nobody
    notices. `tools/gui_text_check.py` gates this at zero in CI, so one of
    these reaching a camera means the check was skipped, not that a miss is
    normal.
    """
    if key in text:
        return text[key]
    logger.warning("GUI text key not found: %s", key)
    return f'<span class="gui-text-missing">[missing text: {html.escape(key)}]</span>'
