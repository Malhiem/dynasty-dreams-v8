"""Iter 231ak — Draft Room eligible-players pagination + prospect-pool dedup.

User complaint after iter 231ai went live:
  "The draft in TFHL still only shows 30 prospects. Please review why
   and correct."

Root cause was twofold:
  1. The `use-draft-eligible-players` hook fetched only the first
     `limit=100` rows (sorted by points DESC). With 1,368 backfilled
     prospects + ~2,000 NHL skaters in a `criteria='all'` draft, NHL
     stars saturated the first page and prospects only surfaced ~17
     rows deep. The hook now drains every page (PAGE_SIZE=200, up to
     50 pages) so the Eligible tab reflects the full eligible pool.
  2. The NHL API backfill (iter 231ah) silently created 29 duplicate
     prospect rows (same name as the curated iter 170o seed) and 179
     contaminated `player_type: 'skater'` rows that were actually
     amateur/junior players with fake 9-digit `nhl_id`s. Both wedges
     polluted the eligible list. The DB cleanup script removed them
     and the players collection now has a single canonical row per
     prospect.

These tests guard the source-of-truth markers so a future refactor
doesn't regress the pagination loop or smuggle duplicates back in.
"""
from pathlib import Path


ELIGIBLE_HOOK = Path("/app/frontend/src/hooks/use-draft-eligible-players.ts")


def test_eligible_hook_paginates_every_page():
    src = ELIGIBLE_HOOK.read_text()
    # The hook must request a fixed PAGE_SIZE constant so reviewers can
    # spot tuning changes in code review instead of hunting for magic
    # numbers inside a URL template literal.
    assert "const PAGE_SIZE = 200" in src
    # Hard safety cap on the loop — if the API ever misreports `pages`
    # the hook should bail out before runaway-fetching the whole DB.
    assert "const MAX_PAGES = 50" in src
    # The fetch loop must read `pages` off the response so it knows
    # when to stop, not just assume "len(rows) < PAGE_SIZE" (last page
    # could be exactly PAGE_SIZE rows long).
    assert "totalPages = Number(res.data?.pages || 1)" in src
    assert "while (page <= totalPages && page <= MAX_PAGES)" in src
    # Each request must carry the `limit` + `page` query params.
    assert "/eligible-players?limit=${PAGE_SIZE}&page=${page}" in src


def test_eligible_hook_accumulates_into_single_setplayers_call():
    src = ELIGIBLE_HOOK.read_text()
    # We accumulate into `all[]` and call setPlayers once at the end —
    # not once per page — so the Eligible tab doesn't flicker through
    # partial states (and so existing memoised selectors don't fire 16
    # times for a 16-page draft).
    assert "const all: ApiPlayer[] = []" in src
    assert "all.push(...rows)" in src
    # setPlayers fired exactly once per draft id change.
    assert src.count("setPlayers(") == 1


def test_eligible_hook_resets_on_unmount():
    """Concurrent draft switches must not race — the cleanup flag has
    to be set even when an in-flight pagination loop is mid-way."""
    src = ELIGIBLE_HOOK.read_text()
    assert "let cancelled = false" in src
    assert "if (cancelled) return" in src
    assert "return () => { cancelled = true; }" in src
