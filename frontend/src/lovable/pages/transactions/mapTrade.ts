// @ts-nocheck
// Iter 232L (refactor) — Backend trade → frontend TradeCard shape mapper.
// Extracted so the huge Transactions page component doesn't own the raw
// backend-to-view translation and so future callers (e.g., the Dashboard
// pending-trades panel) can reuse the same normalization.
import { fmtCapHit } from "./types";

// Backend assets have snake_case fields (player_name, cap_hit,
// fantasy_points_per_game, stat_categories, ...); this converts one row
// into the TradeAsset camelCase shape the cards expect.
export function mapAssetRow(a) {
  const isPick = a.asset_type === "pick" || a.item_type === "pick";
  const salary =
    typeof a.salary === "number"
      ? a.salary
      : typeof a.cap_hit === "number"
      ? a.cap_hit
      : 0;
  return {
    name:
      a.player_name ||
      a.name ||
      (isPick
        ? `${a.pick_year || ""} ${a.pick_round ? "R" + a.pick_round : ""} Pick`.trim()
        : "Unknown"),
    position: a.position || "—",
    age: a.age || 0,
    // Preserve the raw numeric salary alongside the formatted string so
    // the per-side totals row can sum cap hits.
    salary: isPick ? 0 : salary,
    capHit: isPick ? "—" : fmtCapHit(salary),
    goals: a.goals || 0,
    assists: a.assists || 0,
    points: a.points || 0,
    fantasyPts: a.fantasy_points || 0,
    fantasyPtsPerGame: a.fantasy_points_per_game || 0,
    gamesPlayed: a.games_played || 0,
    statCategories: a.stat_categories || {},
    playerType: a.player_type || "skater",
    type: isPick ? "pick" : "player",
    minorEligible: !!a.minor_eligible || a.player_type === "prospect",
  };
}

/**
 * Convert a full backend trade doc into the mapped shape used by the
 * Transactions page. Returns the mapped card PLUS the raw proposer/target
 * team ids and created_at so filters can match by stable id (not display
 * name).
 *
 * `voteState` overlays optimistic vote counts + the user's own vote from
 * `/trades/{id}/vote` responses. `castVote` is threaded through so the
 * card's Approve/Veto buttons can call back into the page.
 */
export function mapTrade(t, { teamName, leagueTeamsCount, voteState, castVote }) {
  const tradeId = t._id || t.id;
  const fromAssets = t.assets_offered || t.from_assets || t.team_a_assets || [];
  const toAssets = t.assets_requested || t.to_assets || t.team_b_assets || [];
  const proposerId = t.proposer_team_id || t.from_team_id || t.team_a_id;
  const targetId = t.target_team_id || t.to_team_id || t.team_b_id;
  const createdAt = t.created_at || t.executed_at || t.submitted_at || "";
  // Iter 231h — Normalize backend `proposed` → `pending` for display so
  // the review card renders the same badge + vote controls.
  const rawStatus = t.status || "pending";
  const status = rawStatus === "proposed" ? "pending" : rawStatus;
  return {
    _proposerId: proposerId,
    _targetId: targetId,
    _createdAt: createdAt,
    card: {
      id: tradeId,
      teamA: teamName(proposerId),
      teamB: teamName(targetId),
      assetsFromA: fromAssets.map(mapAssetRow),
      assetsFromB: toAssets.map(mapAssetRow),
      status,
      submittedAt: (createdAt || "").slice(0, 16).replace("T", " "),
      processesAt: (t.expires_at || t.processes_at || "").slice(0, 16).replace("T", " "),
      votes: {
        approve: voteState[tradeId]?.votes?.approve ?? (t.votes?.approve || 0),
        veto: voteState[tradeId]?.votes?.veto ?? (t.votes?.veto || 0),
        total: leagueTeamsCount,
      },
      yourVote: voteState[tradeId]?.your_vote || null,
      vetoThreshold: voteState[tradeId]?.veto_threshold?.teams_required ?? 0,
      onVote: (vote) => castVote(tradeId, vote),
      scoringCategories: t.scoring_categories,
      // Iter 232M — Held during matchup lock + counter thread linkage.
      deferReason: t.defer_reason || null,
      deferNextUnlock: t.defer_next_unlock || null,
      counteredFrom: t.countered_from || null,
      counteredByTradeId: t.countered_by_trade_id || null,
    },
  };
}
