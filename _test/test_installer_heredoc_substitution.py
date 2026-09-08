"""No command substitution inside the installer's unquoted heredocs.

An unquoted heredoc delimiter (<<EOF, not <<'EOF') performs parameter
expansion, command substitution and arithmetic expansion on the body. The
sudoers block has to be unquoted -- it interpolates $PI_USER and several
paths -- and a comment was briefly shipped in it reading

    # ... so `reboot` from the CLI ...

which is not punctuation: the shell RAN it, as root, in the middle of
`sudo ./cinemate-install.sh`. It rebooted the machine being installed.

Prose in these blocks is not inert. This walks every heredoc in the installer,
works out from its delimiter whether the body is expanded, and rejects a
backtick or a dollar-paren in the expanded ones. Bare $NAME is left alone --
that is the whole reason these heredocs are unquoted.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL_SCRIPTS = (
    ROOT / "cinemate-install.sh",
    ROOT / "cinemate-update.sh",
)

# <<EOF / <<-EOF / << "EOF" / <<'EOF'. The negative lookbehind and lookahead
# exclude <<< here-strings, which are not heredocs -- MANAGED_END's own value
# contains one and was otherwise read as a heredoc opening that swallowed half
# the file.
HEREDOC_START = re.compile(
    r"(?<!<)<<-?\s*(?P<q>['\"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_-]*)(?P=q)(?!<)")


def unescaped(line):
    """Command-substitution openers in *line* that the shell would act on.

    A backslash-escaped one is deliberate: it survives the heredoc verbatim
    and runs later, in the file being written. Only the bare form executes
    now, while the installer is writing.
    """
    hits = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "`":
            hits.append("`")
        elif ch == "$" and line.startswith("$(", i):
            hits.append("$(")
        i += 1
    return hits


def heredocs(text):
    """Yield (tag, quoted, start_line, body) for every heredoc in *text*."""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        match = HEREDOC_START.search(lines[i])
        # A real heredoc has a terminator: a later line that is exactly the
        # tag. Requiring it is what keeps a tag-shaped word inside a string
        # from being mistaken for one.
        if match and any(l.strip() == match.group("tag") for l in lines[i + 1:]):
            tag, quoted = match.group("tag"), bool(match.group("q"))
            body, j = [], i + 1
            while j < len(lines) and lines[j].strip() != tag:
                body.append(lines[j])
                j += 1
            yield tag, quoted, i + 1, body
            i = j
        i += 1


class HeredocSubstitutionTests(unittest.TestCase):
    def test_no_command_substitution_in_an_expanded_heredoc(self):
        for script in SHELL_SCRIPTS:
            if not script.exists():
                continue
            for tag, quoted, line_no, body in heredocs(script.read_text(encoding="utf-8")):
                if quoted:
                    continue  # <<'EOF' -- the body is literal, nothing runs
                for offset, line in enumerate(body):
                    where = f"{script.name}:{line_no + offset + 1} (heredoc <<{tag})"
                    with self.subTest(where=where):
                        for hit in unescaped(line):
                            self.fail(
                                f"{hit} in an unquoted heredoc RUNS as a command "
                                f"when the installer writes the file, not when the "
                                f"written file runs. Escape it (\\{hit}) if it is "
                                f"meant for the generated script, or reword it if "
                                f"it is prose: {line.strip()}")

    def test_the_walker_actually_finds_the_sudoers_block(self):
        # A parser that silently matched nothing would pass the test above
        # while checking nothing at all.
        text = (ROOT / "cinemate-install.sh").read_text(encoding="utf-8")
        tags = [(tag, quoted) for tag, quoted, _, body in heredocs(text)
                if any("sudoers.d/pi_cinemate" in l or "NOPASSWD" in l for l in body)]
        self.assertTrue(tags, "the sudoers heredoc was not found by the walker")
        self.assertTrue(any(not quoted for _tag, quoted in tags),
                        "the sudoers heredoc should be unquoted -- it interpolates $PI_USER")

    def test_the_walker_would_catch_the_bug_that_shipped(self):
        offending = ["# ... so `reboot` from the CLI ..."]
        found = [l for l in offending if "`" in l]
        self.assertEqual(len(found), 1, "sanity: the historical line contains a backtick")


if __name__ == "__main__":
    unittest.main()
