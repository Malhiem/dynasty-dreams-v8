import { useCallback, useEffect } from "react";
import api from "@/lib/api";
import { useHistoryRequest } from "../history/useHistoryRequest";

// A franchise URL owns its league context. Resolve it through the authorized
// trophy response before loading league history or changing global selection.
export function useTrophyRoomHistory(leagueId?: string | null, teamId?: string | null, onLeagueResolved?: (id: string) => void) {
  const loadTeam = useCallback((signal: AbortSignal) => api.get(`/teams/${teamId}/trophy-room`, {signal}).then(res => res.data), [teamId]);
  const teamRequest = useHistoryRequest<any>(teamId || null, loadTeam);
  const resolvedLeagueId = teamId ? teamRequest.data?.league_id : leagueId;
  const loadLeague = useCallback((signal: AbortSignal) => api.get(`/leagues/${resolvedLeagueId}/trophy-room`, {signal}).then(res => res.data), [resolvedLeagueId]);
  const loadDrafts = useCallback((signal: AbortSignal) => api.get(`/leagues/${resolvedLeagueId}/draft-hall-of-awards`, {signal}).then(res => res.data?.drafts || []), [resolvedLeagueId]);
  const leagueRequest = useHistoryRequest<any>(resolvedLeagueId || null, loadLeague);
  const draftRequest = useHistoryRequest<any[]>(resolvedLeagueId && !teamId ? resolvedLeagueId : null, loadDrafts);
  useEffect(() => {
    if (teamId && resolvedLeagueId && leagueRequest.data) onLeagueResolved?.(resolvedLeagueId);
  }, [teamId, resolvedLeagueId, leagueRequest.data, onLeagueResolved]);
  return {
    data: leagueRequest.data, teamData: teamRequest.data, draftRequest,
    loading: leagueRequest.loading || teamRequest.loading,
    error: teamRequest.error || leagueRequest.error,
    retry: () => {teamRequest.retry(); leagueRequest.retry();},
  };
}
