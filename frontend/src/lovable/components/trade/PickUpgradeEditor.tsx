// @ts-nocheck
import { useEffect, useMemo, useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { X, TrendingUp, TrendingDown } from "lucide-react";
import { useTradeBuilder } from "@/lovable/state/TradeBuilderContext";

/**
 * A "pick upgrade" is the conditional trade unit: pick a SUBJECT (player or
 * team), define the performance threshold, then say which pick gets rewritten
 * (and to what) when the threshold lands.
 *
 * Window-bridge contract (matches existing TradeConditionsEditor pattern):
 *   window.__addPickUpgrade()        — add an empty row
 *   window.__getPickUpgrades()       — read serializable rows for the proposal
 */

const PLAYER_METRIC_OPTIONS = [
  { value: "nhl_points",          label: "NHL points (G+A)", bool: false },
  { value: "nhl_goals",           label: "NHL goals",        bool: false },
  { value: "nhl_assists",         label: "NHL assists",      bool: false },
  { value: "nhl_wins",            label: "NHL wins (goalie)", bool: false },
  { value: "games_played",        label: "Games played",     bool: false },
  { value: "fantasy_points",      label: "Fantasy points (season)", bool: false },
  { value: "live_fantasy_points", label: "Fantasy points (live)",   bool: false },
];

const TEAM_METRIC_OPTIONS = [
  { value: "won_championship", label: "wins the championship",      bool: true },
  { value: "won_conference",   label: "wins their conference",      bool: true },
  { value: "won_division",     label: "wins their division",        bool: true },
  { value: "made_playoffs",    label: "makes the playoffs",         bool: true },
  { value: "won_consolation",  label: "wins the consolation bracket", bool: true },
  { value: "team_wins",        label: "team wins",                  bool: false },
  { value: "team_losses",      label: "team losses",                bool: false },
  { value: "team_rank",        label: "team rank (lower = better)", bool: false },
  { value: "team_points_for",  label: "team points-for",            bool: false },
];

const ROUND_LABELS = ["", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th"];

const NEXT_4_YEARS = (() => {
  const now = new Date();
  const start = now.getMonth() >= 6 ? now.getFullYear() + 1 : now.getFullYear();
  return [start, start + 1, start + 2, start + 3];
})();

function isBoolMetric(metric, subjectType) {
  if (subjectType === "team") {
    const m = TEAM_METRIC_OPTIONS.find((o) => o.value === metric);
    return !!m?.bool;
  }
  return false;
}

export function PickUpgradeEditor() {
  const ctx = useTradeBuilder();
  const tradePicks = ctx?.picks || [];
  const tradeAssets = ctx?.assets || [];   // [{ player, retainSalary, ... }]
  const partners = ctx?.partners || [];

  const [rows, setRows] = useState([]);

  useEffect(() => {
    window.__addPickUpgrade = () => {
      setRows((prev) => [...prev, {
        id: `pu_${Date.now()}_${prev.length}`,
        subject_type: "team",  // Step 1 default
        // Step 1 fields:
        team_id: ctx?.myTeamId || "",     // when subject_type=team
        player_id: "",                    // when subject_type=player
        metric: "won_championship",
        operator: "eq",
        threshold: 1,
        // Step 2 — pick to mutate
        pick_id: tradePicks[0]?.pick?.pickId || tradePicks[0]?.pick?.id || "",
        // Step 3 — what the pick becomes
        new_round: 1,
        new_year: null,
      }]);
    };
    window.__getPickUpgrades = () =>
      rows
        .filter((r) => r.pick_id && r.new_round
          && (r.subject_type === "team" ? r.team_id : r.player_id))
        .map((r) => {
          const cond = {
            subject_type: r.subject_type,
            subject: "offered",
            operator: r.operator || "gte",
            metric: r.metric,
            threshold: Number(r.threshold ?? 1),
            description: r.description,
          };
          if (r.subject_type === "team") cond.team_id = r.team_id;
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

  // Players currently in the trade — both directions
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

  if (rows.length === 0) {
    return (
      <div
        className="text-[11px] text-muted-foreground italic border border-dashed border-border rounded-md px-3 py-2"
        data-testid="pick-upgrades-empty"
      >
        {tradePicks.length === 0
          ? "Add a draft pick to this trade first, then click + Pick upgrade to attach a player- or team-based trigger."
          : "Click + Pick upgrade to walk through 1) pick a player or team condition, 2) pick which draft pick gets rewritten, 3) pick what the new round/year becomes."}
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="pick-upgrades-list">
      {rows.map((r, i) => {
        const pickRow = tradePicks.find((p) => (p.pick.pickId || p.pick.id) === r.pick_id);
        const currentRound = Number(pickRow?.pick?.round || 0);
        const newRound = Number(r.new_round || 0);
        const direction =
          currentRound && newRound
            ? newRound < currentRound ? "upgrade"
            : newRound > currentRound ? "downgrade"
            : "same"
            : null;
        const metricOptions = r.subject_type === "team" ? TEAM_METRIC_OPTIONS : PLAYER_METRIC_OPTIONS;
        const bool = isBoolMetric(r.metric, r.subject_type);

        return (
          <div
            key={r.id}
            data-testid={`pick-upgrade-row-${i}`}
            className="bg-card border border-border rounded-md p-3 space-y-2.5"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-primary/40 text-primary">
                  Conditional trade {i + 1}
                </Badge>
                {direction === "upgrade" && (
                  <Badge variant="outline" className="border-emerald-500/50 text-emerald-500 text-[10px] h-4 gap-1">
                    <TrendingUp className="h-2.5 w-2.5" />Upgrade
                  </Badge>
                )}
                {direction === "downgrade" && (
                  <Badge variant="outline" className="border-rose-500/50 text-rose-500 text-[10px] h-4 gap-1">
                    <TrendingDown className="h-2.5 w-2.5" />Downgrade
                  </Badge>
                )}
              </div>
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

            {/* Step 1 — Player or team condition */}
            <div className="space-y-1.5">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                Step 1 · Choose the condition
              </p>
              <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                <Select
                  value={r.subject_type}
                  onValueChange={(v) => update(r.id, {
                    subject_type: v,
                    metric: v === "team" ? "won_championship" : "nhl_points",
                    operator: v === "team" ? "eq" : "gte",
                    threshold: v === "team" ? 1 : 50,
                    player_id: v === "player" ? r.player_id : "",
                    team_id: v === "team" ? (r.team_id || ctx?.myTeamId || "") : "",
                  })}
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
                  </SelectContent>
                </Select>

                {r.subject_type === "team" ? (
                  <Select
                    value={r.team_id}
                    onValueChange={(v) => update(r.id, { team_id: v })}
                  >
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
                ) : (
                  <Select
                    value={r.player_id}
                    onValueChange={(v) => update(r.id, { player_id: v })}
                  >
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

                <Select
                  value={r.metric}
                  onValueChange={(v) => {
                    const opt = (r.subject_type === "team" ? TEAM_METRIC_OPTIONS : PLAYER_METRIC_OPTIONS)
                      .find((o) => o.value === v);
                    update(r.id, {
                      metric: v,
                      operator: opt?.bool ? "eq" : (r.operator || "gte"),
                      threshold: opt?.bool ? 1 : (r.threshold || 50),
                    });
                  }}
                >
                  <SelectTrigger
                    data-testid={`pick-upgrade-metric-${i}`}
                    className="h-7 w-[200px] text-[11px]"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {metricOptions.map((m) => (
                      <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {!bool && (
                  <>
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
                    <Input
                      type="number"
                      data-testid={`pick-upgrade-threshold-${i}`}
                      className="h-7 w-[80px] text-[11px]"
                      value={r.threshold ?? 0}
                      onChange={(e) => update(r.id, { threshold: Number(e.target.value) })}
                    />
                  </>
                )}
                {bool && (
                  <span className="text-[11px] text-muted-foreground italic">must be true</span>
                )}
              </div>
            </div>

            {/* Step 2 — Pick to upgrade/downgrade */}
            <div className="space-y-1.5">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                Step 2 · Pick affected by this condition
              </p>
              <Select value={r.pick_id} onValueChange={(v) => update(r.id, { pick_id: v })}>
                <SelectTrigger
                  data-testid={`pick-upgrade-pick-${i}`}
                  className="h-7 w-full max-w-[360px] text-[11px]"
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
            </div>

            {/* Step 3 — What the pick becomes */}
            <div className="space-y-1.5">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                Step 3 · If condition met, the pick becomes
              </p>
              <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                <Select
                  value={String(r.new_round)}
                  onValueChange={(v) => update(r.id, { new_round: Number(v) })}
                >
                  <SelectTrigger
                    data-testid={`pick-upgrade-new-round-${i}`}
                    className="h-7 w-[110px] text-[11px]"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ROUND_LABELS.slice(1).map((lbl, idx) => (
                      <SelectItem key={idx + 1} value={String(idx + 1)}>{lbl} round</SelectItem>
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
