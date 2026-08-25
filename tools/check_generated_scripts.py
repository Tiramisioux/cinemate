#!/usr/bin/env python3
"""Shellcheck the two scripts cinemate-install.sh writes to the Pi at install
time (compile-raw.sh, run_cinemate.sh) -- F-195. They are heredoc bodies
inside cinemate-install.sh, so the repo-wide `find . -name '*.sh'` sweep in
checks.yml never sees them; this extracts each heredoc, applies bash's own
unquoted-heredoc escaping rules (\\$, \\`, \\\\, and a trailing \\<newline>
are the only specials -- everything else is literal), and shellchecks the
result.

Variables the heredocs reference (CINEPI_RAW_DIR, PYTHON_BIN, ...) come from
cinemate-install.sh's own scope, not the extracted script's -- SC2154 (used
but not assigned) is expected and suppressed per-file below rather than
silenced repo-wide.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLER = REPO_ROOT / "cinemate-install.sh"

# function name -> (target path the heredoc writes to, for a readable label)
TARGETS = {
    "write_compile_raw_script": "compile-raw.sh",
    "configure_run_wrapper": "run_cinemate.sh",
}

HEREDOC_ESCAPES = re.compile(r"\\([$`\\\n])")


def extract_heredoc(text: str, func_name: str) -> str:
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(f"{func_name}()"))
    # Find the heredoc opener (<<EOF or <<'EOF') after the function start.
    open_re = re.compile(r"<<-?\s*'?EOF'?\s*$")
    body_start = next(
        i for i in range(start, len(lines)) if open_re.search(lines[i])
    )
    quoted = "'EOF'" in lines[body_start]
    body_end = next(
        i for i in range(body_start + 1, len(lines)) if lines[i] == "EOF"
    )
    body = "\n".join(lines[body_start + 1 : body_end]) + "\n"
    if not quoted:
        body = HEREDOC_ESCAPES.sub(lambda m: "" if m.group(1) == "\n" else m.group(1), body)
    return body


def main() -> int:
    text = INSTALLER.read_text()
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for func_name, label in TARGETS.items():
            body = extract_heredoc(text, func_name)
            path = Path(tmp) / label
            path.write_text(body)
            paths.append(path)

        result = subprocess.run(
            [
                "shellcheck",
                "-f",
                "gcc",
                "--exclude=SC2154",  # vars from cinemate-install.sh's own scope
                *[str(p) for p in paths],
            ],
            capture_output=True,
            text=True,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if result.returncode != 0:
            failures += 1

    if failures:
        print(
            f"check_generated_scripts: shellcheck found issues in "
            f"{', '.join(TARGETS.values())} (extracted from cinemate-install.sh)",
            file=sys.stderr,
        )
        return 1
    print(f"check_generated_scripts: {', '.join(TARGETS.values())} clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
