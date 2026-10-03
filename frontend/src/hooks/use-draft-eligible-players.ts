/**
 * Iter 229d — `useDraftEligiblePlayers`
 * Extracted from DraftRoom.tsx. Fetches the eligible-players list for
 * the active draft and overlays `drafted=true` for any player whose id
 * already appears in the backend `picks[]`. Falls back to the caller's
 * default (mock) list when the API fails so the Draft Room never
 * renders blank during commissioner setup flows.
 *
 * Iter 231ak — Paginate the request so the full eligible pool is
 * available client-side. Previously the hook only fetched the first
 * 100 rows (sorted by points DESC), which made the 1,368 backfilled
 * prospects appear as ~17 visible rows because NHL skaters dominated
 * the head of the list. Now we drain every page (200 per request) up
 * to a safety cap so the Eligible tab always reflects the true pool.
 */
import { useEffect } from "react";
import api from "@/lib/api";
import type { DraftEligiblePlayer } from "@/lovable/pages/draftroom/types";

type ApiPlayer = Partial<DraftEligiblePlayer> & {
  headshot?: string;
  headshot_url?: string;
  nhl_id?: string;
  team_name?: string;
  player_type?: string;
  minor_eligible?: boolean;
};

interface DraftLike {
  _id?: string;
  picks?: Array<{ player_id?: string }>;
}

const PAGE_SIZE = 200;
// Safety cap: 50 pages × 200 rows = 10,000 players. Today's eligible
// pool is ~3,400 (2,027 NHL + 1,368 prospects); the cap protects
// against a runaway loop if the API ever misreports `pages`.
const MAX_PAGES = 50;

export function useDraftEligiblePlayers(
  currentDraft: DraftLike | null,
  setPlayers: (players: DraftEligiblePlayer[]) => void,
) {
  useEffect(() => {
    if (!currentDraft?._id) return;
    let cancelled = false;

    async function loadAll() {
      const all: ApiPlayer[] = [];
      let page = 1;
      let totalPages = 1;
      try {
        while (page <= totalPages && page <= MAX_PAGES) {
          const res = await api.get(
            `/drafts/${currentDraft!._id}/eligible-players?limit=${PAGE_SIZE}&page=${page}`,
          );
          if (cancelled) return;
          const rows: ApiPlayer[] = (res.data?.players || []) as ApiPlayer[];
          totalPages = Number(res.data?.pages || 1);
          if (rows.length === 0) break;
          all.push(...rows);
          if (rows.length < PAGE_SIZE) break;
          page += 1;
        }
      } catch {
        // keep caller's default list
        return;
      }

      if (cancelled || all.length === 0) return;
      const draftedIds = new Set(
        (currentDraft!.picks || [])
          .map((p) => p.player_id)
          .filter(Boolean)
          .map((v) => String(v)),
      );
      setPlayers(
        all.map((p) => ({
          id: String(p.id ?? ""),
          name: String(p.name ?? ""),
          position: String(p.position ?? ""),
          nhlTeam: p.nhlTeam || "—",
          age: p.age || 0,
          league: p.league || "NHL",
          gp: p.gp || 0,
          g: p.g || 0,
          a: p.a || 0,
          pts: p.pts || 0,
          ranking: p.ranking || 0,
          drafted: draftedIds.has(String(p.id)),
          // Pass-through fields the SelectedPlayerCard / Eligible row read.
          // We cast to `any` because DraftEligiblePlayer is intentionally
          // narrow and these extras are presentation-only.
          ...(p.headshot ? { headshot: p.headshot, headshot_url: p.headshot } : {}),
          ...(p.nhl_id ? { nhl_id: p.nhl_id } : {}),
          ...(p.team_name ? { team_name: p.team_name } : {}),
          ...(p.player_type ? { player_type: p.player_type } : {}),
          minor_eligible: !!p.minor_eligible,
          // Iter 232N — Passthrough for the player status badge row.
          status_flags: (p as any).status_flags || null,
        }) as unknown as DraftEligiblePlayer),
      );
    }

    loadAll();
    return () => { cancelled = true; };
  }, [currentDraft?._id]);
}

export default useDraftEligiblePlayers;
