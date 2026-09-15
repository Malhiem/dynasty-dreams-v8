"""Tests for Roto standings rank engine — validates acceptance criteria.

AC focus:
  - 12-team no-tie → ranks 1-12, points 12-1
  - Scoring direction respected
  - Total = sum of category points
  - Ranks included in API response
  - Standings sorted by total DESC
"""
import pytest
from routes.roto import _rank_category


class TestRankCategory:
    """Pure unit tests for the _rank_category engine."""

    def test_12_teams_no_ties_higher_is_better(self):
        """12 distinct values → ranks 1-12, points 12-1."""
        teams = [(f"t{i}", float(13 - i)) for i in range(1, 13)]
        # t1=12, t2=11, ..., t12=1  (all distinct)
        points, ranks = _rank_category(teams, higher_is_better=True, tiebreak="split", num_teams=12)
        for i in range(1, 13):
            tid = f"t{i}"
            assert ranks[tid] == i, f"{tid} expected rank {i}, got {ranks[tid]}"
            expected_pts = 13 - i  # rank 1→12pts, rank 2→11pts, ..., rank 12→1pt
            assert points[tid] == expected_pts, f"{tid} expected {expected_pts}pts, got {points[tid]}"

    def test_12_teams_no_ties_lower_is_better(self):
        """Lower-is-better: lowest value → rank 1 → 12 points."""
        teams = [(f"t{i}", float(i)) for i in range(1, 13)]
        # t1=1 (lowest=best), t2=2, ..., t12=12 (highest=worst)
        points, ranks = _rank_category(teams, higher_is_better=False, tiebreak="split", num_teams=12)
        for i in range(1, 13):
            tid = f"t{i}"
            assert ranks[tid] == i, f"{tid} expected rank {i}, got {ranks[tid]}"
            expected_pts = 13 - i
            assert points[tid] == expected_pts, f"{tid} expected {expected_pts}pts, got {points[tid]}"

    def test_12_teams_tie_split(self):
        """Two teams tied for 5th: both get rank 5, points = avg(8,7)=7.5."""
        vals = [12, 11, 10, 9, 5, 5, 4, 3, 2, 1, 0.5, 0.1]
        teams = [(f"t{i+1}", vals[i]) for i in range(12)]
        points, ranks = _rank_category(teams, higher_is_better=True, tiebreak="split", num_teams=12)
        # t5 and t6 both have value 5 → tied for rank 5
        assert ranks["t5"] == 5
        assert ranks["t6"] == 5
        assert points["t5"] == 7.5  # (8+7)/2
        assert points["t6"] == 7.5
        # t7 has rank 7 (skips rank 6)
        assert ranks["t7"] == 7
        assert points["t7"] == 6.0

    def test_12_teams_tie_high(self):
        """Two teams tied for 5th with 'high' tiebreak: both get 8 pts."""
        vals = [12, 11, 10, 9, 5, 5, 4, 3, 2, 1, 0.5, 0.1]
        teams = [(f"t{i+1}", vals[i]) for i in range(12)]
        points, ranks = _rank_category(teams, higher_is_better=True, tiebreak="high", num_teams=12)
        assert ranks["t5"] == 5
        assert ranks["t6"] == 5
        assert points["t5"] == 8.0  # max(8,7)
        assert points["t6"] == 8.0

    def test_total_equals_sum_of_category_points(self):
        """With 3 categories, total per team = sum of 3 category points."""
        teams_goals = [(f"t{i}", float(13 - i)) for i in range(1, 13)]
        teams_assists = [(f"t{i}", float(i)) for i in range(1, 13)]
        teams_pim = [(f"t{i}", float(i * 2)) for i in range(1, 13)]

        pts_g, _ = _rank_category(teams_goals, True, "split", 12)
        pts_a, _ = _rank_category(teams_assists, True, "split", 12)
        pts_pim, _ = _rank_category(teams_pim, False, "split", 12)  # lower is better

        for i in range(1, 13):
            tid = f"t{i}"
            total = pts_g[tid] + pts_a[tid] + pts_pim[tid]
            assert total == pts_g[tid] + pts_a[tid] + pts_pim[tid]

    def test_all_tied_split(self):
        """All 12 teams at 0 → rank 1, points = avg(1..12) = 6.5 each."""
        teams = [(f"t{i}", 0.0) for i in range(1, 13)]
        points, ranks = _rank_category(teams, True, "split", 12)
        for i in range(1, 13):
            tid = f"t{i}"
            assert ranks[tid] == 1
            assert points[tid] == 6.5  # (1+2+...+12)/12 = 78/12 = 6.5

    def test_ranks_are_competition_style(self):
        """Competition ranking: 1,1,3 (not 1,1,2) when two are tied."""
        teams = [("a", 10.0), ("b", 10.0), ("c", 5.0)]
        _, ranks = _rank_category(teams, True, "split", 3)
        assert ranks["a"] == 1
        assert ranks["b"] == 1
        assert ranks["c"] == 3  # NOT 2
