// @ts-nocheck
/**
 * DraftPicks — Iter 227 hooked up to live data.
 *
 * Was rendering hardcoded mock picks before. Now fetches the league's
 * scheduled drafts via `/api/drafts?league_id=...`; if none exist, shows
 * the "No drafts planned at this time" empty-state per the iter-227 spec.
 *
 * Future: when the upcoming-pick API surfaces traded picks + projections,
 * map them onto the same `DraftPick` shape and render the legacy grid.
 */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";

const DraftPicks = () => {
  const { activeLeagueId } = useActiveLeague();
  const [drafts, setDrafts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!activeLeagueId) { setLoading(false); return; }
      try {
        const { data } = await api.get(`/drafts`, { params: { league_id: activeLeagueId } });
        if (!cancelled) {
          setDrafts(Array.isArray(data) ? data : (data?.drafts || []));
        }
      } catch {
        if (!cancelled) setDrafts([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [activeLeagueId]);

  if (loading) {
    return (
      <div className="stat-card p-6" data-testid="draft-picks-loading">
        <h3 className="text-lg font-semibold mb-2">Draft Capital</h3>
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  if (drafts.length === 0) {
    return (
      <div className="stat-card p-6" data-testid="draft-picks-empty">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold">Draft Capital</h3>
          <span className="text-xs bg-secondary/40 text-muted-foreground font-medium px-2 py-1 rounded-full">
            0 Picks
          </span>
        </div>
        <p className="text-sm text-muted-foreground italic text-center py-4">
          No drafts planned at this time
        </p>
      </div>
    );
  }

  return (
    <div className="stat-card p-0 overflow-hidden" data-testid="draft-picks-list">
      <div className="p-6 border-b border-border">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Draft Capital</h3>
          <span className="text-xs bg-accent/20 text-accent font-medium px-2 py-1 rounded-full">
            {drafts.length} Scheduled
          </span>
        </div>
      </div>
      <div className="p-6 space-y-3">
        {drafts.map((d) => (
          <div
            key={d.id || d._id}
            className="p-3 rounded-lg border border-border bg-secondary/30 flex items-center justify-between"
          >
            <div>
              <p className="text-sm font-semibold">{d.name || d.title || "Untitled draft"}</p>
              <p className="text-[11px] text-muted-foreground">
                {(d.draft_type || d.type || "Snake").toString()} · {d.total_rounds || d.rounds || 0} rounds
              </p>
            </div>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{d.status || "scheduled"}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default DraftPicks;
