"""Season labels must agree before and after completing the same season."""
import unittest
from services.schedule_store import season


class SeasonContractTest(unittest.TestCase):
    def test_completion_year_is_the_start_year(self):
        self.assertEqual(season({"current_season_year": 2026}), "2026-27")

    def test_explicit_legacy_label_wins(self):
        self.assertEqual(season({"season": "2025-26", "current_season_year": 2026}), "2025-26")

    def test_string_start_year_remains_supported(self):
        self.assertEqual(season({"current_season_year": "2026"}), "2026-27")

    def test_century_boundary_uses_the_next_year(self):
        self.assertEqual(season({"current_season_year": 2099}), "2099-00")
