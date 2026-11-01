"""Basic smoke tests for the SmartBite meal catalogue and planner.

Run with: python -m unittest discover -s tests -v
"""
import unittest
from pathlib import Path

class DatasetTests(unittest.TestCase):
    def test_meal_catalogue_exists(self):
        path = Path(__file__).resolve().parents[1] / "data" / "meals.csv"
        self.assertTrue(path.is_file())

    def test_meal_catalogue_has_records(self):
        import csv
        path = Path(__file__).resolve().parents[1] / "data" / "meals.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreaterEqual(len(rows), 1)
        self.assertTrue({"veg", "non-veg", "mixed"}.issubset({r["diet_type"] for r in rows}))

if __name__ == "__main__":
    unittest.main()
