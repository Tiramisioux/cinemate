"""The canonical aspect-ratio table (ASPECT-RATIOS.md, "What CineMate does
with this", step 2/5): id, exact value, common name, in one file. Do not
write a second copy in JavaScript -- this codebase carries the scar of a
catalogue kept twice (resources/sensors.json's own loader docstring), and it
drifted.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.aspect_ratios import load_aspect_ratio_table, resolve_aspect_ratio_table_path

# ASPECT-RATIOS.md: "Fourteen ratios: 1:1, 1.33:1, 1.37:1, 1.78:1, 1.85:1,
# 1.89:1, 1.90:1, 2.00:1, 2.20:1, 2.22:1, 2.35:1, 2.39:1, 2.50:1, 2.55:1."
EXPECTED_IDS = [
    "1:1", "1.33:1", "1.37:1", "1.78:1", "1.85:1", "1.89:1", "1.90:1",
    "2.00:1", "2.20:1", "2.22:1", "2.35:1", "2.39:1", "2.50:1", "2.55:1",
]
EXPECTED_VALUES = {
    "1:1": 1.0, "1.33:1": 1.33, "1.37:1": 1.37, "1.78:1": 1.78,
    "1.85:1": 1.85, "1.89:1": 1.89, "1.90:1": 1.90, "2.00:1": 2.00,
    "2.20:1": 2.20, "2.22:1": 2.22, "2.35:1": 2.35, "2.39:1": 2.39,
    "2.50:1": 2.50, "2.55:1": 2.55,
}


class AspectRatioTableTests(unittest.TestCase):
    def test_the_shipped_table_has_exactly_the_fourteen_ratios(self):
        table = load_aspect_ratio_table()
        self.assertEqual([e["id"] for e in table], EXPECTED_IDS)

    def test_each_entry_carries_id_value_and_name(self):
        table = load_aspect_ratio_table()
        for entry in table:
            with self.subTest(id=entry["id"]):
                self.assertEqual(entry["value"], EXPECTED_VALUES[entry["id"]])
                self.assertIsInstance(entry["name"], str)
                self.assertTrue(entry["name"])

    def test_the_file_is_strict_json_no_comments(self):
        # Same convention as resources/sensors.json: a stray `//` takes the
        # whole file down, so this is never a .jsonc.
        import json  # noqa: PLC0415
        path = resolve_aspect_ratio_table_path()
        json.loads(path.read_text(encoding="utf-8"))  # must not raise

    def test_a_missing_file_warns_and_returns_empty_rather_than_raising(self):
        table = load_aspect_ratio_table("does/not/exist.json")
        self.assertEqual(table, [])

    def test_default_path_is_resources_aspect_ratios_json(self):
        path = resolve_aspect_ratio_table_path()
        self.assertEqual(path, ROOT / "resources" / "aspect_ratios.json")


if __name__ == "__main__":
    unittest.main()
