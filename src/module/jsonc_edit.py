"""Change values in a JSONC document without disturbing anything else.

settings.jsonc is 74 comment lines out of 386 -- section banners and per-key
explanations that make the file editable by hand. The web settings editor used
to rewrite it with json.dumps(), which meant every save deleted all of them.

Rewriting from the parsed tree can never preserve comments, because the tree
does not contain them. So this module goes the other way: it locates each
value's exact span in the *original text* and rewrites only the spans whose
values actually changed. Everything else -- comments, blank lines, key order,
indentation, trailing commas -- survives byte-for-byte because it is never
touched.

That only works while the document's shape is unchanged. Adding or removing a
key, resizing an array, or changing a value's type has no span to overwrite.
When that happens `apply_updates` returns None and the caller falls back to a
full rewrite: the last rung still produces a correct file, it just loses the
comments, and the caller is expected to say so out loud rather than quietly.

No dependencies beyond the standard library. Pure text in, text out.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["apply_updates", "mask_comments", "value_spans", "StructureChanged"]


class StructureChanged(Exception):
    """The document's shape changed, so no surgical edit is possible."""


def mask_comments(text: str) -> str:
    """Blank out // and /* */ comments, preserving every character offset.

    Offsets must survive so that spans found in the masked text address the
    same characters in the original. Comment bodies become spaces; newlines
    inside block comments are kept so line numbers stay meaningful too.
    """
    out = list(text)
    i, n = 0, len(text)
    in_string = escape = False
    while i < n:
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            for _ in range(2):
                if i < n:
                    out[i] = " "
                    i += 1
            continue
        i += 1
    return "".join(out)


class _Scanner:
    """Recursive-descent walk that records (path -> span) for every value."""

    def __init__(self, text: str):
        self.text = text
        self.i = 0
        self.spans: dict[tuple, tuple[int, int]] = {}

    def _ws(self) -> None:
        while self.i < len(self.text) and self.text[self.i] in " \t\r\n,":
            self.i += 1

    def _string(self) -> str:
        assert self.text[self.i] == '"'
        start = self.i
        self.i += 1
        while self.i < len(self.text):
            c = self.text[self.i]
            if c == "\\":
                self.i += 2
                continue
            if c == '"':
                self.i += 1
                return json.loads(self.text[start:self.i])
            self.i += 1
        raise StructureChanged("unterminated string")

    def value(self, path: tuple) -> None:
        self._ws()
        start = self.i
        c = self.text[self.i]
        if c == "{":
            self.i += 1
            while True:
                self._ws()
                if self.i >= len(self.text):
                    raise StructureChanged("unterminated object")
                if self.text[self.i] == "}":
                    self.i += 1
                    break
                key = self._string()
                self._ws()
                if self.text[self.i] != ":":
                    raise StructureChanged("expected ':'")
                self.i += 1
                self.value(path + (key,))
        elif c == "[":
            self.i += 1
            idx = 0
            while True:
                self._ws()
                if self.i >= len(self.text):
                    raise StructureChanged("unterminated array")
                if self.text[self.i] == "]":
                    self.i += 1
                    break
                self.value(path + (idx,))
                idx += 1
        elif c == '"':
            self._string()
        else:
            while self.i < len(self.text) and self.text[self.i] not in ",}]\n \t\r":
                self.i += 1
        self.spans[path] = (start, self.i)


def value_spans(text: str) -> dict[tuple, tuple[int, int]]:
    """Map every value's path to its (start, end) offsets in *text*."""
    scanner = _Scanner(mask_comments(text))
    scanner.value(())
    return scanner.spans


def _leaves(node: Any, path: tuple = ()) -> dict[tuple, Any]:
    if isinstance(node, dict):
        out: dict[tuple, Any] = {}
        for key, sub in node.items():
            out.update(_leaves(sub, path + (key,)))
        return out
    if isinstance(node, list):
        out = {}
        for idx, sub in enumerate(node):
            out.update(_leaves(sub, path + (idx,)))
        return out
    return {path: node}


def apply_updates(text: str, current: Any, desired: Any) -> str | None:
    """Rewrite *text* so it holds *desired* instead of *current*.

    `current` must be what parsing `text` yields. Returns the edited text, or
    **None** when the change is structural and no span-level edit expresses it
    -- keys added or removed, an array resized, or a scalar swapped for a
    container. Callers treat None as "fall back to a full rewrite, and tell the
    user the comments were lost".
    """
    before, after = _leaves(current), _leaves(desired)
    if before.keys() != after.keys():
        return None

    changed = {p: v for p, v in after.items() if before[p] != v}
    if not changed:
        return text

    try:
        spans = value_spans(text)
    except (StructureChanged, AssertionError, IndexError, ValueError):
        return None

    edits = []
    for path, new_value in changed.items():
        span = spans.get(path)
        if span is None:
            return None
        edits.append((span[0], span[1], json.dumps(new_value, ensure_ascii=False)))

    # Apply right-to-left so earlier offsets stay valid.
    out = text
    for start, end, replacement in sorted(edits, reverse=True):
        out = out[:start] + replacement + out[end:]
    return out
