// @ts-nocheck
import { useEffect, useMemo, useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { X, TrendingUp, TrendingDown } from "lucide-react";
import { useTradeBuilder } from "@/lovable/state/TradeBuilderContext";

/**
 * Conditional Pick Upgrade / Downgrade builder.
 *
 * Flow per user spec:
 *   1) (implicit) User clicks "+ Pick upgrade" or "+ Pick downgrade" — sets
 *      the direction for the row.
 *   2) IF — define the condition (player OR team, including fantasy-point
 *      production).
 *   3) THEN — pick the existing draft pick that gets rewritten and the new
 *      round/year it becomes when the condition fires.
 *
 * Window-bridge contract:
 *   window.__addPickUpgrade("upgrade" | "downgrade")
 *   window.__getPickUpgrades()
 */

const PLAYER_METRIC_OPTIONS = [
  { value: "fantasy_points",      label: "Fantasy points (season)", bool: false, defaultThreshold: 200 },
  { value: "live_fantasy_points", label: "Fantasy points (live)",   bool: false, defaultThreshold: 200 },
  { value: "nhl_points",          label: "NHL points (G+A)",        bool: false, defaultThreshold: 60 },
  { value: "nhl_goals",           label: "NHL goals",               bool: false, defaultThreshold: 30 },
  { value: "nhl_assists",         label: "NHL assists",             bool: false, defaultThreshold: 40 },
  { value: "nhl_wins",            label: "NHL wins (goalie)",       bool: false, defaultThreshold: 30 },
  { value: "games_played",        label: "Games played",            bool: false, defaultThreshold: 60 },
];

const TEAM_METRIC_OPTIONS = [
  { value: "won_championship",   label: "wins the championship",        bool: true,  defaultThreshold: 1 },
  { value: "won_conference",     label: "wins their conference",        bool: true,  defaultThreshold: 1 },
  { value: "won_division",       label: "wins their division",          bool: true,  defaultThreshold: 1 },
  { value: "made_playoffs",      label: "makes the playoffs",           bool: true,  defaultThreshold: 1 },
  { value: "won_consolation",    label: "wins the consolation bracket", bool: true,  defaultThreshold: 1 },
  { value: "won_draft_lottery",  label: "wins the draft lottery",       bool: true,  defaultThreshold: 1 },
  { value: "team_wins",          label: "team wins",                    bool: false, defaultThreshold: 8 },
  { value: "team_losses",        label: "team losses",                  bool: false, defaultThreshold: 8 },
  { value: "team_rank",          label: "team rank (lower = better)",   bool: false, defaultThreshold: 6 },
  { value: "team_points_for",    label: "team fantasy points-for",      bool: false, defaultThreshold: 1500 },
];

// Pick-protection metrics — auto-bind to the THEN pick_id at submit time.
const PICK_METRIC_OPTIONS = [
  { value: "pick_slot",  label: "pick lands in top-N slots", bool: false, defaultThreshold: 3 },
];

const ROUND_LABELS = ["", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th"];

const NEXT_4_YEARS = (() => {
  const now = new Date();
  const start = now.getMonth() >= 6 ? now.getFullYear() + 1 : now.getFullYear();
  return [start, start + 1, start + 2, start + 3];
})();

function metricsFor(subjectType) {
  if (subjectType === "team") return TEAM_METRIC_OPTIONS;
  if (subjectType === "pick") return PICK_METRIC_OPTIONS;
  return PLAYER_METRIC_OPTIONS;
}

function metricMeta(metric, subjectType) {
  const list = metricsFor(subjectType);
  return list.find((o) => o.value === metric) || list[0];
}

export function PickUpgradeEditor() {
  const ctx = useTradeBuilder();
  const tradePicks = ctx?.picks || [];
  const tradeAssets = ctx?.assets || [];
  const partners = ctx?.partners || [];

  const [rows, setRows] = useState([]);

  useEffect(() => {
    window.__addPickUpgrade = (direction = "upgrade") => {
      const dir = direction === "downgrade" ? "downgrade" : "upgrade";
      setRows((prev) => [...prev, {
        id: `pu_${Date.now()}_${prev.length}`,
        direction: dir,
        // Step 2 — IF
        subject_type: "team",
        team_id: ctx?.myTeamId || "",
        player_id: "",
        metric: "won_championship",
        operator: "eq",
        threshold: 1,
        // Step 3 — THEN
        pick_id: tradePicks[0]?.pick?.pickId || tradePicks[0]?.pick?.id || "",
        new_round: dir === "upgrade" ? 1 : null,  // resolved once pick is chosen
        new_year: null,
      }]);
    };

    window.__getPickUpgrades = () =>
      rows
        .filter((r) => r.pick_id && r.new_round
          && (r.subject_type === "team" ? r.team_id
            : r.subject_type === "pick" ? r.pick_id
            : r.player_id))
        .map((r) => {
          const cond = {
            subject_type: r.subject_type,
            subject: "offered",
            operator: r.operator || "gte",
            metric: r.metric,
            threshold: Number(r.threshold ?? 1),
          };
          if (r.subject_type === "team") cond.team_id = r.team_id;
          else if (r.subject_type === "pick") cond.pick_id = r.pick_id;  // auto-bound to THEN pick
          else cond.player_id = r.player_id;
          return {
            pick_id: r.pick_id,
            new_round: Number(r.new_round),
            new_year: r.new_year ? Number(r.new_year) : null,
            condition: cond,
          };
        });

    return () => {
      delete window.__addPickUpgrade;
      delete window.__getPickUpgrades;
    };
  }, [rows, tradePicks, ctx?.myTeamId]);

  const update = (id, patch) =>
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const remove = (id) => setRows((prev) => prev.filter((r) => r.id !== id));

  const teamOptions = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const p of partners) {
      if (!p?.id || seen.has(p.id)) continue;
      seen.add(p.id);
      out.push({ id: p.id, name: p.name });
    }
    return out;
  }, [partners]);

  const playerOptions = useMemo(() => {
    const out = [];
    for (const a of tradeAssets) {
      if (!a?.player) continue;
      out.push({
        id: a.player.id,
        name: a.player.name || "Unknown player",
        team: a.player.team,
        position: a.player.position,
      });
    }
    return out;
  }, [tradeAssets]);

  const pickOptions = useMemo(() =>
    tradePicks.map((p) => ({
      id: p.pick.pickId || p.pick.id,
      label: `${p.pick.year} R${p.pick.round} (from ${p.pick.ownerTeamName || "?"})`,
    })),
  [tradePicks]);

  /** Build context-aware suggested triggers. Each entry, when applied,
   * sets the row's IF fields. THEN fields are left to the user. */
  const suggestedTriggers = useMemo(() => {
    const out = [];
    if (ctx?.myTeamId) {
      out.push({
        key: "champ-me",
        label: "If my team wins the cup",
        patch: {
          subject_type: "team", team_id: ctx.myTeamId, player_id: "",
          metric: "won_championship", operator: "eq", threshold: 1,
        },
      });
      out.push({
        key: "lottery-me",
        label: "If my team wins the lottery",
        patch: {
          subject_type: "team", team_id: ctx.myTeamId, player_id: "",
          metric: "won_draft_lottery", operator: "eq", threshold: 1,
        },
      });
      out.push({
        key: "rank-bottom-me",
        label: "If my team finishes bottom-3",
        patch: {
          subject_type: "team", team_id: ctx.myTeamId, player_id: "",
          metric: "team_rank", operator: "gte", threshold: 10,
        },
      });
    }
    const partner = teamOptions.find((t) => t.id !== ctx?.myTeamId);
    if (partner) {
      out.push({
        key: "rank-bottom-partner",
        label: `If ${partner.name} finishes bottom-3`,
        patch: {
          subject_type: "team", team_id: partner.id, player_id: "",
          metric: "team_rank", operator: "gte", threshold: 10,
        },
      });
    }
    if (playerOptions.length) {
      const p = playerOptions[0];
      out.push({
        key: "fp-200",
        label: `If ${p.name} hits 200+ fantasy points`,
        patch: {
          subject_type: "player", player_id: p.id, team_id: "",
          metric: "fantasy_points", operator: "gte", threshold: 200,
        },
      });
    }
    if (pickOptions.length) {
      out.push({
        key: "pick-top-3",
        label: "If pick lands top-3 (lottery protection)",
        patch: {
          subject_type: "pick", team_id: "", player_id: "",
          metric: "pick_slot", operator: "lte", threshold: 3,
        },
      });
    }
    return out;
  }, [ctx?.myTeamId, teamOptions, playerOptions, pickOptions]);

  const applySuggestion = (rowId, patch) => update(rowId, patch);

  if (rows.length === 0) {
    return (
      <div
        className="text-[11px] text-muted-foreground italic border border-dashed border-border rounded-md px-3 py-2"
        data-testid="pick-upgrades-empty"
      >
        {tradePicks.length === 0
          ? "Add a draft pick to this trade first, then click + Pick upgrade or + Pick downgrade to attach a player- or team-based trigger."
          : "Click + Pick upgrade or + Pick downgrade to define an IF/THEN clause that rewrites a pick when a player- or team-performance threshold lands."}
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="pick-upgrades-list">
      {rows.map((r, i) => {
        const pickRow = tradePicks.find((p) => (p.pick.pickId || p.pick.id) === r.pick_id);
        const currentRound = Number(pickRow?.pick?.round || 0);
        const meta = metricMeta(r.metric, r.subject_type);
        const isBool = !!meta?.bool;

        // Constrain new_round options by direction
        const validRounds = Array.from({ length: 10 }, (_, idx) => idx + 1).filter((rd) => {
          if (!currentRound) return true;
          if (r.direction === "upgrade")   return rd < currentRound;
          if (r.direction === "downgrade") return rd > currentRound;
          return true;
        });
        const directionIcon = r.direction === "upgrade" ? TrendingUp : TrendingDown;
        const DirectionIcon = directionIcon;

        return (
          <div
            key={r.id}
            data-testid={`pick-upgrade-row-${i}`}
            className="bg-card border border-border rounded-md p-3 space-y-2.5"
          >
            <div className="flex items-center justify-between">
              <Badge
                data-testid={`pick-upgrade-direction-${i}`}
                variant="outline"
                className={`text-[10px] h-4 gap-1 ${
                  r.direction === "upgrade"
                    ? "border-emerald-500/50 text-emerald-500"
                    : "border-rose-500/50 text-rose-500"
                }`}
              >
                <DirectionIcon className="h-2.5 w-2.5" />
                Pick {r.direction}
              </Badge>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => remove(r.id)}
                data-testid={`pick-upgrade-remove-${i}`}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>

            {/* IF — condition */}
            <div className="space-y-1.5">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                IF — condition met
              </p>

              {/* Suggested triggers chip row */}
              {suggestedTriggers.length > 0 && (
                <div
                  className="flex flex-wrap gap-1 pb-1"
                  data-testid={`pick-upgrade-suggestions-${i}`}
                >
                  {suggestedTriggers.map((s) => (
                    <button
                      key={s.key}
                      type="button"
                      data-testid={`pick-upgrade-suggestion-${s.key}-${i}`}
                      onClick={() => applySuggestion(r.id, s.patch)}
                      className="px-2 py-0.5 rounded-full text-[10px] border border-primary/30 bg-primary/5 text-primary hover:bg-primary/15 transition-colors"
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              )}

              <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                <Select
                  value={r.subject_type}
                  onValueChange={(v) => {
                    const list = metricsFor(v);
                    const m = list[0]?.value;
                    update(r.id, {
                      subject_type: v,
                      metric: m,
                      operator: list[0]?.bool ? "eq" : "gte",
                      threshold: list[0]?.defaultThreshold ?? 50,
                      player_id: v === "player" ? r.player_id : "",
                      team_id: v === "team" ? (r.team_id || ctx?.myTeamId || "") : "",
                    });
                  }}
                >
                  <SelectTrigger
                    data-testid={`pick-upgrade-subject-type-${i}`}
                    className="h-7 w-[110px] text-[11px]"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="team">Team</SelectItem>
                    <SelectItem value="player">Player</SelectItem>
                    <SelectItem value="pick">Pick</SelectItem>
                  </SelectContent>
                </Select>

                {r.subject_type === "team" && (
                  <Select value={r.team_id} onValueChange={(v) => update(r.id, { team_id: v })}>
                    <SelectTrigger
                      data-testid={`pick-upgrade-team-${i}`}
                      className="h-7 w-[160px] text-[11px]"
                    >
                      <SelectValue placeholder="Select team" />
                    </SelectTrigger>
                    <SelectContent>
                      {teamOptions.map((t) => (
                        <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                {r.subject_type === "player" && (
                  <Select value={r.player_id} onValueChange={(v) => update(r.id, { player_id: v })}>
                    <SelectTrigger
                      data-testid={`pick-upgrade-player-${i}`}
                      className="h-7 w-[200px] text-[11px]"
                    >
                      <SelectValue placeholder={playerOptions.length ? "Select player" : "Add a player to the trade first"} />
                    </SelectTrigger>
                    <SelectContent>
                      {playerOptions.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name}{p.team ? ` · ${p.team}` : ""}{p.position ? ` (${p.position})` : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                {r.subject_type === "pick" && (
                  <span
                    className="text-[11px] text-muted-foreground italic"
                    data-testid={`pick-upgrade-pick-bound-${i}`}
                  >
                    Auto-bound to the pick selected below
                  </span>
                )}

                <Select
                  value={r.metric}
                  onValueChange={(v) => {
                    const opt = metricsFor(r.subject_type).find((o) => o.value === v);
                    update(r.id, {
                      metric: v,
                      operator: opt?.bool ? "eq" : (r.subject_type === "pick" ? "lte" : "gte"),
                      threshold: opt?.defaultThreshold ?? r.threshold ?? 50,
                    });
                  }}
                >
                  <SelectTrigger
                    data-testid={`pick-upgrade-metric-${i}`}
                    className="h-7 w-[230px] text-[11px]"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {metricsFor(r.subject_type).map((m) => (
                      <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {!isBool && (
                  <>
                    {r.subject_type === "pick" ? (
                      <span className="text-muted-foreground">≤</span>
                    ) : (
                      <Select value={r.operator} onValueChange={(v) => update(r.id, { operator: v })}>
                        <SelectTrigger
                          data-testid={`pick-upgrade-operator-${i}`}
                          className="h-7 w-[58px] text-[11px]"
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="gte">≥</SelectItem>
                          <SelectItem value="lte">≤</SelectItem>
                          <SelectItem value="eq">=</SelectItem>
                        </SelectContent>
                      </Select>
                    )}
                    {r.subject_type === "pick" ? (
                      <Select
                        value={String(r.threshold ?? 3)}
                        onValueChange={(v) => update(r.id, { threshold: Number(v) })}
                      >
                        <SelectTrigger
                          data-testid={`pick-upgrade-threshold-${i}`}
                          className="h-7 w-[110px] text-[11px]"
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {[2, 3, 4, 5, 6, 7, 8, 10, 15].map((n) => (
                            <SelectItem key={n} value={String(n)}>top {n}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <Input
                        type="number"
                        data-testid={`pick-upgrade-threshold-${i}`}
                        className="h-7 w-[80px] text-[11px]"
                        value={r.threshold ?? 0}
                        onChange={(e) => update(r.id, { threshold: Number(e.target.value) })}
                      />
                    )}
                  </>
                )}
                {isBool && (
                  <span className="text-[11px] text-muted-foreground italic">must be true</span>
                )}
              </div>
            </div>

            {/* THEN — pick to award */}
            <div className="space-y-1.5">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                THEN — pick to be awarded
              </p>
              <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                <Select value={r.pick_id} onValueChange={(v) => update(r.id, { pick_id: v })}>
                  <SelectTrigger
                    data-testid={`pick-upgrade-pick-${i}`}
                    className="h-7 w-[220px] text-[11px]"
                  >
                    <SelectValue placeholder={tradePicks.length === 0 ? "Add picks to the trade first" : "Select pick"} />
                  </SelectTrigger>
                  <SelectContent>
                    {tradePicks.map((p) => {
                      const pid = p.pick.pickId || p.pick.id;
                      return (
                        <SelectItem key={pid} value={pid}>
                          {p.pick.year} R{p.pick.round} (from {p.pick.ownerTeamName || "?"})
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
                <span className="text-muted-foreground">becomes</span>
                <Select
                  value={r.new_round ? String(r.new_round) : ""}
                  onValueChange={(v) => update(r.id, { new_round: Number(v) })}
                >
                  <SelectTrigger
                    data-testid={`pick-upgrade-new-round-${i}`}
                    className="h-7 w-[110px] text-[11px]"
                  >
                    <SelectValue placeholder="Round" />
                  </SelectTrigger>
                  <SelectContent>
                    {validRounds.length === 0 && (
                      <SelectItem disabled value="__none__">
                        {r.direction === "upgrade" ? "Already a 1st" : "Already a 10th"}
                      </SelectItem>
                    )}
                    {validRounds.map((rd) => (
                      <SelectItem key={rd} value={String(rd)}>{ROUND_LABELS[rd]} round</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select
                  value={r.new_year ? String(r.new_year) : "__same__"}
                  onValueChange={(v) => update(r.id, { new_year: v === "__same__" ? null : Number(v) })}
                >
                  <SelectTrigger
                    data-testid={`pick-upgrade-new-year-${i}`}
                    className="h-7 w-[120px] text-[11px]"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__same__">Same year</SelectItem>
                    {NEXT_4_YEARS.map((y) => (
                      <SelectItem key={y} value={String(y)}>{y}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
