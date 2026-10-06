// @ts-nocheck
import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";

export default function useDraftSalaryState(draftId, players, currentPick) {
  const [status, setStatus] = useState(null);
  const [eligibility, setEligibility] = useState({});
  const [error, setError] = useState(false);
  const generation = useRef(0);
  const ids = players.filter(p => !p.drafted).map(p => String(p.id)).join(",");
  const refresh = useCallback(async () => {
    if (!draftId) return;
    const request = ++generation.current;
    try {
      const {data: state} = await api.get(`/drafts/${draftId}/roster-status`);
      const all = ids ? ids.split(",") : [];
      const candidates = {};
      for (let start = 0; start < all.length; start += 200) {
        if (request !== generation.current) return;
        const {data} = await api.post(`/drafts/${draftId}/salary-eligibility`, {player_ids: all.slice(start, start + 200)});
        Object.assign(candidates, data.players);
      }
      if (request !== generation.current) return;
      setStatus(state); setEligibility(candidates); setError(false);
    } catch { if (request === generation.current) setError(true); }
  }, [draftId, ids]);
  useEffect(() => { setStatus(null); setEligibility({}); }, [draftId]);
  useEffect(() => {
    let stopped = false;
    let timer;
    async function run() { await refresh(); if (!stopped) timer = setTimeout(run, 3000); }
    run();
    const focus = () => refresh();
    window.addEventListener("focus", focus);
    return () => { stopped = true; ++generation.current; clearTimeout(timer); window.removeEventListener("focus", focus); };
  }, [refresh, currentPick]);
  return { status, eligibility, error, refresh };
}
