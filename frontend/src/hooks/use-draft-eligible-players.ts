/**
 * Iter 229d — `useDraftEligiblePlayers`
 * Extracted from DraftRoom.tsx. Fetches the eligible-players list for
 * the active draft and overlays `drafted=true` for any player whose id
 * already appears in the backend `picks[]`. Falls back to the caller's
 * default (mock) list when the API fails so the Draft Room never
 * renders blank during commissioner setup flows.
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

export function useDraftEligiblePlayers(
  currentDraft: DraftLike | null,
  setPlayers: (players: DraftEligiblePlayer[]) => void,
) {
  useEffect(() => {
    if (!currentDraft?._id) return;
    let cancelled = false;
    api
      .get(`/drafts/${currentDraft._id}/eligible-players?limit=100`)
      .then((res) => {
        if (cancelled) return;
        const real: ApiPlayer[] = (res.data?.players || []) as ApiPlayer[];
        if (real.length === 0) return;
        const draftedIds = new Set(
          (currentDraft.picks || [])
            .map((p) => p.player_id)
            .filter(Boolean)
            .map((v) => String(v)),
        );
        setPlayers(
          real.map((p) => ({
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
          }) as unknown as DraftEligiblePlayer),
        );
      })
      .catch(() => {
        /* keep caller's default list */
      });
    return () => { cancelled = true; };
  }, [currentDraft?._id]);
}

export default useDraftEligiblePlayers;
