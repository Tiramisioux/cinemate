"""The findings check must skip an absent archive without going blind.

`system-review/` was moved off `dev` in 54cae555 -- a dated audit record and an
analysis workspace, not shipped product code. `tools/findings_disposition_check.py`
kept pointing at `system-review/FINDINGS.md` regardless, so it raised
`FileNotFoundError` on every push to `dev` for over a week. Because the steps in
a GitHub Actions job run in sequence, that traceback also skipped the five drift
checks wired in after it: design tokens, controller action resolution, link
frequencies, settings-editor copy, and the cross-repo redis key contract. One
stale path turned six checks off at once, and the red X looked like a single
failing check.

Making it skip is the fix, but a skip is also how a check stops protecting you
(see the handbook's "a check that finds nothing must fail"). So the skip is
narrow, and this pins all three edges of it:

- archive absent entirely -> skip, exit 0 (the documented state on dev);
- archive present but `FINDINGS.md` gone -> exit 1, because that is a broken
  archive rather than an absent one;
- `FINDINGS.md` present but the row pattern matches too little -> exit 1,
  rather than reporting zero findings and passing forever.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "tools" / "findings_disposition_check.py"

# Two rows in the shape FINDINGS.md uses, enough to prove the parser runs.
HEADER = "| id | title | disposition |\n|---|---|---|\n"
ROWS = "| F-001 | a thing | accepted |\n| F-002 | another | fixed |\n"


def run(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), "--repo", str(repo)],
        capture_output=True, text=True,
    )


class FindingsDispositionSkip(unittest.TestCase):
    def test_absent_archive_skips(self):
        """dev carries no system-review/, and that is not a failure."""
        with tempfile.TemporaryDirectory() as d:
            result = run(Path(d))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("skipped", result.stdout)

    def test_archive_without_findings_file_fails(self):
        """A half-present archive is breakage, not the documented absence."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "system-review").mkdir()
            result = run(Path(d))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("incomplete", result.stdout)

    def test_unparseable_table_fails_rather_than_finding_nothing(self):
        """Zero matched rows must read as a broken pattern, not a clean bill."""
        with tempfile.TemporaryDirectory() as d:
            review = Path(d) / "system-review"
            review.mkdir()
            # Right header, but no row matches ROW_RE's `F-###`.
            (review / "FINDINGS.md").write_text(
                HEADER + ROWS.replace("F-", "G-"), encoding="utf-8"
            )
            result = run(Path(d))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ROW_RE", result.stdout)

    def test_a_full_table_passes_and_one_blank_disposition_fails(self):
        """The original gate still works once the table clears the floor.

        Built above MINIMUM_ROWS on purpose: a fixture that trips the floor
        would exit 1 for the wrong reason and pass this test even if the
        disposition logic were deleted.
        """
        full = HEADER + "".join(
            f"| F-{n:03d} | row {n} | accepted |\n" for n in range(1, 261)
        )
        with tempfile.TemporaryDirectory() as d:
            review = Path(d) / "system-review"
            review.mkdir()
            findings = review / "FINDINGS.md"

            findings.write_text(full, encoding="utf-8")
            ok = run(Path(d))
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            self.assertIn("260 findings", ok.stdout)

            findings.write_text(
                full + "| F-261 | undispositioned |  |\n", encoding="utf-8"
            )
            bad = run(Path(d))
        self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
        self.assertIn("F-261", bad.stdout)


if __name__ == "__main__":
    unittest.main()
