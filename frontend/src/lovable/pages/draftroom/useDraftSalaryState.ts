// @ts-nocheck
import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";

export default function useDraftSalaryState(draftId, players, currentPick) {
  const [status, setStatus] = useState(null);
  const [eligibility, setEligibility] = useState({});
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  const controller = useRef(null);
  const ids = players.filter(p => !p.drafted).map(p => String(p.id)).join(",");
  const refreshRoster = useCallback(async () => {
    if (!draftId) return;
    const request = ++generation.current;
    controller.current?.abort();
    const pending = new AbortController();
    controller.current = pending;
    try {
      const {data} = await api.get(`/drafts/${draftId}/roster-status`, {signal: pending.signal});
      if (request !== generation.current) return;
      setStatus(data);
      setError(false);
      return data;
    } catch { if (request === generation.current) setError(true); }
  }, [draftId]);
  const refresh = useCallback(async () => {
    setRevision(value => value + 1);
    return refreshRoster();
  }, [refreshRoster]);
  useEffect(() => { setStatus(null); setEligibility({}); setError(false); }, [draftId]);
  useEffect(() => {
    let stopped = false;
    let timer;
    async function run() {
      await refreshRoster();
      if (!stopped) timer = setTimeout(run, 3000);
    }
    run();
    const focus = () => refresh();
    window.addEventListener("focus", focus);
    return () => {
      stopped = true;
      ++generation.current;
      controller.current?.abort();
      clearTimeout(timer);
      window.removeEventListener("focus", focus);
    };
  }, [refreshRoster, refresh, currentPick]);
  useEffect(() => {
    if (!draftId) return;
    let stopped = false;
    let timer;
    const pending = new AbortController();
    const all = ids ? ids.split(",") : [];
    setEligibility({});
    async function run() {
      const candidates = {};
      try {
        for (let start = 0; start < all.length; start += 200) {
          const {data} = await api.post(`/drafts/${draftId}/salary-eligibility`,
            {player_ids: all.slice(start, start + 200)}, {signal: pending.signal});
          if (stopped) return;
          Object.assign(candidates, data.players);
          setEligibility({...candidates});
        }
      } catch { /* Missing eligibility stays unavailable until the next refresh. */ }
      if (!stopped) timer = setTimeout(run, 3000);
    }
    run();
    return () => { stopped = true; pending.abort(); clearTimeout(timer); };
  }, [draftId, ids, currentPick, revision]);
  return { status, eligibility, error, refresh };
}
