import unittest
from fastapi import HTTPException
from services.roto_schedule import calendar

class RotoCalendar(unittest.TestCase):
    def league(self,**extra): return {"season_start_date":"2025-01-01","season_end_date":"2025-02-04","regular_season_weeks":5,"matchup_length_days":7,**extra}
    def test_biweekly_groups_final_short_period_without_opponents(self):
        rows=calendar(self.league(roto_period_length_weeks=2))
        self.assertEqual([p['id'] for p in rows],[1,3,5]);self.assertEqual(rows[-1]['endDate'],'2025-02-04')
        self.assertTrue(all(set(p)=={'id','startDate','endDate','type'} for p in rows))
    def test_full_season_is_one_scoring_period(self):
        rows=calendar(self.league(roto_period_length_weeks=0));self.assertEqual(len(rows),1);self.assertEqual(rows[0]['endDate'],'2025-02-04')
    def test_missing_dates_and_overlapping_playoffs_are_rejected(self):
        for league in [{},self.league(playoffs_enabled=True,roto_playoffs_enabled=True,playoff_start_week=5,playoff_end_week=7)]:
            with self.assertRaises(HTTPException):calendar(league)
    def test_disabled_roto_playoffs_produce_no_playoff_periods(self):
        self.assertTrue(all(p['type']=='regular' for p in calendar(self.league(playoffs_enabled=True,roto_playoffs_enabled=False))))
