#!/usr/bin/env python3
"""Stdlib-only JSONC stripper for the recovery console.

THIS IS THE THIRD COPY OF THIS LOGIC IN THE TREE. The others are:

  * src/module/config_loader.py        -- the original, used by Cinemate
  * cinemate-install.sh (~line 1586)   -- a minimal mirror, for the installer

It is duplicated rather than imported on purpose. The recovery console must
keep working when the venv is broken, when redis is down, and when
/home/pi/cinemate is unreadable -- so it may not import anything from
src/module/.

The cost of that decision is drift. The mitigation is
_test/test_recovery_jsonc_golden.py, which asserts character-for-character
equality against module.config_loader.strip_jsonc over a shared corpus. If you
edit either implementation, that test fails until you edit both. Do not delete
it and do not weaken it to a "close enough" comparison.

Behaviour contract, identical to the original:
  * // and /* */ comments are blanked, not deleted, so every surviving
    character keeps its original line and column. A JSONDecodeError raised
    against the result still points at the right place in the real file.
  * newlines inside a block comment survive as newlines
  * a trailing comma before } or ] is blanked
  * neither transformation touches the inside of a string literal
"""


class UnterminatedBlockComment(Exception):
    """Raised when a /* comment is never closed."""

    def __init__(self, line: int, column: int) -> None:
        super().__init__(f"Unterminated /* comment at line {line}, column {column}")
        self.line = line
        self.column = column


def strip_jsonc_comments(text: str) -> str:
    """Blank out // and /* */ comments, outside of string literals."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
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
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            line_start = text.rfind("\n", 0, i) + 1
            start_line = text.count("\n", 0, i) + 1
            start_col = i - line_start + 1
            out.append("  ")
            i += 2
            closed = False
            while i < n:
                if text[i] == "*" and i + 1 < n and text[i + 1] == "/":
                    out.append("  ")
                    i += 2
                    closed = True
                    break
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if not closed:
                raise UnterminatedBlockComment(start_line, start_col)
            continue
        out.append(c)
        i += 1
    return "".join(out)


def strip_trailing_commas(text: str) -> str:
    """Blank out a comma followed only by whitespace before } or ]."""
    out = list(text)
    in_string = False
    escape = False
    i = 0
    n = len(text)
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
        if c == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                out[i] = " "
        i += 1
    return "".join(out)


def strip_jsonc(text: str) -> str:
    """Make JSONC parseable by json.loads(), preserving line/column offsets."""
    return strip_trailing_commas(strip_jsonc_comments(text))
