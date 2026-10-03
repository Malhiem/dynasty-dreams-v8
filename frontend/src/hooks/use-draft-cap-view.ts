/**
 * Iter 232N.62 — Draft-room cap view hook.
 *
 * Fetches /api/drafts/{id}/cap-status, exposes:
 *   • capView         — boolean toggle (persists per-user in localStorage)
 *   • setCapView      — setter that ALSO clears the 90%-approaching alert
 *   • data            — full response payload (per-team usage rows)
 *   • myTeam          — the caller's team row (or null)
 *   • approaching     — true when ANY team on the caller's roster crosses
 *                       90% AND capView is still OFF (drives the pulsing
 *                       toggle + one-time toast)
 *   • resolveCapHit   — helper that returns the AAV to charge for a
 *                       player card (contract.aav → cap_hit → salary →
 *                       league.default_rookie_aav)
 *   • refresh         — force reload after a pick lands
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";

interface TeamCapRow {
  team_id: string;
  name: string;
  salary_used: number;
  salary_cap: number;
  remaining: number;
  percent_used: number;
  over_cap: boolean;
  approaching: boolean;
  picks_count: number;
}

interface CapStatus {
  draft_id: string;
  league_id: string;
  salary_cap_enabled: boolean;
  salary_cap: number;
  default_rookie_aav: number;
  minors_cap_treatment: string;
  approaching_pct: number;
  my_team_id: string | null;
  teams: TeamCapRow[];
}

const STORAGE_KEY = (draftId: string) => `draft_cap_view:${draftId}`;
const ACK_KEY = (draftId: string) => `draft_cap_view_acked:${draftId}`;

export default function useDraftCapView(draftId: string | null | undefined) {
  const [data, setData] = useState<CapStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [capView, setCapViewState] = useState<boolean>(() => {
    if (!draftId) return false;
    try {
      return localStorage.getItem(STORAGE_KEY(draftId)) === "1";
    } catch {
      return false;
    }
  });
  const toastFiredRef = useRef(false);

  const load = useCallback(async () => {
    if (!draftId) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/drafts/${draftId}/cap-status`);
      setData(data);
    } catch {
      // Silently ignore — non-cap leagues also return early
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [draftId]);

  useEffect(() => {
    load();
  }, [load]);

  const setCapView = useCallback(
    (next: boolean) => {
      setCapViewState(next);
      if (!draftId) return;
      try {
        localStorage.setItem(STORAGE_KEY(draftId), next ? "1" : "0");
        if (next) {
          // Enabling cap view acknowledges the approaching alert.
          localStorage.setItem(ACK_KEY(draftId), "1");
        }
      } catch {
        /* ignore */
      }
    },
    [draftId],
  );

  const myTeam = useMemo<TeamCapRow | null>(() => {
    if (!data || !data.my_team_id) return null;
    return data.teams.find((t) => t.team_id === data.my_team_id) || null;
  }, [data]);

  // Any team the user cares about crossing 90% before they've toggled
  // the view. For now we treat "my team" as the trigger (userscope) —
  // could later expand to any team.
  const approaching = useMemo(() => {
    if (!data?.salary_cap_enabled || capView) return false;
    if (!myTeam) return false;
    return myTeam.approaching;
  }, [data, myTeam, capView]);

  // One-time toast when we cross the 90% threshold and the user hasn't
  // already acknowledged (via toggling on) OR seen the toast.
  useEffect(() => {
    if (!approaching || !draftId) return;
    let acked = false;
    try {
      acked = localStorage.getItem(ACK_KEY(draftId)) === "1";
    } catch {
      /* ignore */
    }
    if (acked || toastFiredRef.current) return;
    toastFiredRef.current = true;
    toast.warning(
      `You're within ${100 - (myTeam?.percent_used ?? 90)}% of your cap ceiling — toggle Cap View to plan the rest of your draft.`,
      { duration: 8000 },
    );
  }, [approaching, draftId, myTeam]);

  const resolveCapHit = useCallback(
    (player: any): number => {
      const contractAav = Number(player?.contract?.aav);
      if (contractAav && contractAav > 0) return contractAav;
      const cap = Number(player?.cap_hit);
      if (cap && cap > 0) return cap;
      const sal = Number(player?.salary);
      if (sal && sal > 0) return sal;
      return Number(data?.default_rookie_aav ?? 950_000);
    },
    [data],
  );

  return {
    capView,
    setCapView,
    data,
    loading,
    myTeam,
    approaching,
    resolveCapHit,
    refresh: load,
    // Convenience — whether cap features apply at all
    capEnabled: Boolean(data?.salary_cap_enabled),
  };
}
