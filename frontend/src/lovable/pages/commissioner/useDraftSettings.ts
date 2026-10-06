// @ts-nocheck
import { useState, useEffect } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

export function useDraftSettings(activeLeague) {
  const [draftType, setDraftType] = useState<string>("startup");
  const [firstDraftCompleted, setFirstDraftCompleted] = useState<boolean>(false);
  // Iter 143 — first-time draft gating + persistence (moved here so it
  // can reference `activeLeague` after its declaration)
  useEffect(() => {
    if (!activeLeague?.id) return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/leagues/${activeLeague.id}`);
        if (cancelled) return;
        if (data?.first_draft_completed) setFirstDraftCompleted(true);
        if (data?.next_draft_type) setDraftType(data.next_draft_type);
        else if (!data?.first_draft_completed) setDraftType("startup");
        else setDraftType("redraft");
      } catch {/* noop */}
    })();
    return () => { cancelled = true; };
  }, [activeLeague?.id]);
  const persistDraftType = (v: string) => {
    setDraftType(v);
    if (activeLeague?.id) {
      api.put(`/leagues/${activeLeague.id}/next-draft-type`, { draft_type: v })
        .catch((e) => toast.error(e?.response?.data?.detail || "Failed to save draft type"));
    }
  };

  const [selectedPlayerCriteria, setSelectedPlayerCriteria] = useState<string[]>(["all"]);
  const [draftRounds, setDraftRounds] = useState(5);
  const [roundTimes, setRoundTimes] = useState<Record<number, string>>({});
  const [expandedDraft, setExpandedDraft] = useState<string | null>(null);
  const [expandedDraftResults, setExpandedDraftResults] = useState<string | null>(null);
  const [createDraftPickTrading, setCreateDraftPickTrading] = useState(true);
  const [draftClockEnabled, setDraftClockEnabled] = useState(true);
  const [draftClockStart, setDraftClockStart] = useState("09:00");
  const [draftClockEnd, setDraftClockEnd] = useState("23:00");
  const completedDraftResults = [
    { draftId: "draft-3", pick: 1, round: 1, team: "Ice Crushers", player: "Connor Bedard", position: "C" },
    { draftId: "draft-3", pick: 2, round: 1, team: "Glacier Kings", player: "Matvei Michkov", position: "RW" },
    { draftId: "draft-3", pick: 3, round: 1, team: "Northern Lights", player: "Adam Fantilli", position: "C" },
    { draftId: "draft-3", pick: 4, round: 1, team: "Blizzard", player: "Leo Carlsson", position: "C" },
    { draftId: "draft-3", pick: 5, round: 1, team: "Tundra Kings", player: "Will Smith", position: "C" },
    { draftId: "draft-3", pick: 6, round: 2, team: "Tundra Kings", player: "Zach Benson", position: "LW" },
    { draftId: "draft-3", pick: 7, round: 2, team: "Blizzard", player: "Ryan Leonard", position: "RW" },
    { draftId: "draft-3", pick: 8, round: 2, team: "Northern Lights", player: "Dalibor Dvorsky", position: "C" },
    { draftId: "draft-3", pick: 9, round: 2, team: "Glacier Kings", player: "Nate Danielson", position: "C" },
    { draftId: "draft-3", pick: 10, round: 2, team: "Ice Crushers", player: "Oliver Moore", position: "C" },
  ];

  // Iter 227 — Replace the previous hardcoded `scheduledDrafts` mock with a
  // live fetch from `/api/drafts?league_id=...`. New leagues start empty
  // (the TFHL "3 saved drafts" bug). Re-fetched after the Create Draft
  // wire-up below persists a new draft.
  const [scheduledDrafts, setScheduledDrafts] = useState([]);

  const reloadScheduledDrafts = async () => {
    if (!activeLeague?.id) {
      setScheduledDrafts([]);
      return;
    }
    try {
      const { data } = await api.get(`/drafts`, { params: { league_id: activeLeague.id } });
      // Iter 228d — Normalize draft rows for display:
      //   • formatSeconds: turn raw seconds (e.g. 7200) into "2 hr" / "30 min"
      //   • titleCase: capitalize "all" → "All", "auto-select" → "Auto-select"
      //   • split scheduled_time ISO into separate date + time strings
      const formatSeconds = (s) => {
        const n = parseInt(s, 10);
        if (!Number.isFinite(n) || n <= 0) return "—";
        if (n >= 3600 && n % 3600 === 0) return `${n / 3600} hr`;
        if (n >= 3600) return `${(n / 3600).toFixed(1)} hr`;
        if (n >= 60) return `${Math.round(n / 60)} min`;
        return `${n} sec`;
      };
      const titleCase = (v) => {
        if (Array.isArray(v)) return v.map(titleCase).join(", ");
        if (!v) return v;
        const s = String(v).replace(/-/g, " ").replace(/_/g, " ");
        return s.charAt(0).toUpperCase() + s.slice(1);
      };
      const splitDateTime = (iso) => {
        if (!iso) return { date: "—", time: "—" };
        try {
          const dt = new Date(iso);
          if (isNaN(dt.getTime())) return { date: String(iso), time: "—" };
          return {
            date: dt.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }),
            time: dt.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }),
          };
        } catch { return { date: String(iso), time: "—" }; }
      };
      const rows = (Array.isArray(data) ? data : data?.drafts || []).map((d) => {
        const { date, time } = splitDateTime(d.scheduled_time || d.scheduled_date);
        return {
          id: d.id || d._id,
          name: d.name || d.title || "Untitled draft",
          type: titleCase(d.type || d.draft_type || "snake draft"),
          format: d.format || (d.snake_draft ? "Snake Draft" : "Linear Draft"),
          rounds: d.rounds || d.total_rounds || 0,
          timePerPick: formatSeconds(d.time_per_pick || d.timePerPick),
          // Iter 228n — Raw fields so the Edit Draft dialog can
          // pre-fill date pickers + numeric inputs without re-parsing.
          scheduledISO: d.scheduled_time || d.scheduled_date || null,
          timePerPickSeconds: Number(d.time_per_pick || d.timePerPick || 3600),
          excludePreviouslyDrafted: !!d.exclude_previously_drafted,
          minorsEligibilityRequired: !!d.minors_eligibility_required,
          // Iter 228o — Raw fields for the expanded Edit Draft dialog.
          draftType: d.draft_type || d.type || "entry",
          snakeDraft: d.snake_draft !== undefined ? !!d.snake_draft : true,
          // Backend stores player_criteria as a list (modern) or string (legacy).
          playerCriteriaRaw: d.player_criteria,
          missedPickActionKey: d.missed_pick_action || "auto-select",
          deferUserOptions: Array.isArray(d.defer_user_options)
            ? d.defer_user_options
            : ["auto-best", "auto-queue", "pick-anytime"],
          roundTimeOverrides: Array.isArray(d.round_time_overrides) ? d.round_time_overrides : [],
          playerCriteria: titleCase(d.player_criteria || "all"),
          missedPickAction: titleCase(d.missed_pick_action || "auto-select best available"),
          scheduledDate: date,
          scheduledTime: time,
          status: (d.status || "scheduled"),
          completedDate: d.completed_at || d.completedDate || null,
          pickTradingEnabled: !!d.pick_trading_enabled,
          tradingWindowOpens: d.trading_window_opens || null,
        };
      });
      setScheduledDrafts(rows);
    } catch {
      setScheduledDrafts([]);
    }
  };

  useEffect(() => {
    reloadScheduledDrafts();
  }, [activeLeague?.id]);

  const playerCriteriaOptions = [
    { value: "all", label: "All Players" },
    { value: "rookies", label: "Rookies Only" },
    { value: "prospects", label: "Prospects Only" },
    { value: "nhl", label: "NHL Rostered Only" },
    { value: "unsigned", label: "Unsigned / Draft Eligible" },
  ];

  return { draftType, firstDraftCompleted, persistDraftType, selectedPlayerCriteria, setSelectedPlayerCriteria, draftRounds, setDraftRounds, roundTimes, setRoundTimes, expandedDraft, setExpandedDraft, expandedDraftResults, setExpandedDraftResults, createDraftPickTrading, setCreateDraftPickTrading, draftClockEnabled, setDraftClockEnabled, draftClockStart, setDraftClockStart, draftClockEnd, setDraftClockEnd, completedDraftResults, scheduledDrafts, reloadScheduledDrafts, playerCriteriaOptions };
}
