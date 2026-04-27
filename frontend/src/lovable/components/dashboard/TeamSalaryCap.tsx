// @ts-nocheck
import { useEffect, useState } from "react";
import { DollarSign } from "lucide-react";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";

const formatCurrency = (val: number) => `$${(val / 1_000_000).toFixed(1)}M`;

interface Props {
  teamId?: string;
  /** Bumps when the underlying roster changes so the cap re-fetches. */
  refreshKey?: number;
}

const TeamSalaryCap = ({ teamId, refreshKey }: Props) => {
  const { league, myTeam } = useActiveLeague();
  const resolvedTeamId = teamId || myTeam?.id;

  const [compliance, setCompliance] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!resolvedTeamId) return;
    let cancelled = false;
    setLoading(true);
    api.get(`/teams/${resolvedTeamId}/compliance`)
      .then(({ data }) => { if (!cancelled) setCompliance(data); })
      .catch(() => { if (!cancelled) setCompliance(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [resolvedTeamId, refreshKey]);

  // ── Cap-disabled empty state ───────────────────────────────────
  if (compliance && !compliance.salary_cap_enabled) {
    return (
      <div className="stat-card p-0 overflow-hidden" data-testid="team-salary-cap-card">
        <div className="p-6 border-b border-border">
          <div className="flex items-center gap-2">
            <DollarSign className="h-5 w-5 text-muted-foreground" />
            <h3 className="text-lg font-semibold">Salary Cap</h3>
          </div>
        </div>
        <div className="p-6 text-sm text-muted-foreground">
          Salary cap is <span className="font-semibold text-foreground">disabled</span> for this league. Commissioners can enable it in League Administration → Rosters.
        </div>
      </div>
    );
  }

  if (loading || !compliance) {
    return (
      <div className="stat-card p-0 overflow-hidden" data-testid="team-salary-cap-card">
        <div className="p-6 border-b border-border">
          <div className="flex items-center gap-2">
            <DollarSign className="h-5 w-5 text-accent" />
            <h3 className="text-lg font-semibold">Salary Cap</h3>
          </div>
        </div>
        <div className="p-6 text-sm text-muted-foreground italic">Loading cap…</div>
      </div>
    );
  }

  const capLimit = Number(compliance.salary_cap || 0);
  const capUsed = Number(compliance.salary_used || 0);
  const capRemaining = capLimit - capUsed;
  const overCap = capRemaining < 0;
  const overReason = (compliance.reasons || []).find((r: any) => r.code === "over_salary_cap");

  const items = [
    { label: "Cap Limit", value: formatCurrency(capLimit), accent: false },
    { label: "Cap Used", value: formatCurrency(capUsed), accent: false },
    {
      label: overCap ? "Over Cap By" : "Cap Remaining",
      value: formatCurrency(Math.abs(capRemaining)),
      accent: true,
      negative: overCap,
    },
  ];

  return (
    <div className="stat-card p-0 overflow-hidden" data-testid="team-salary-cap-card">
      <div className="p-6 border-b border-border">
        <div className="flex items-center gap-2">
          <DollarSign className={`h-5 w-5 ${overCap ? "text-destructive" : "text-accent"}`} />
          <h3 className="text-lg font-semibold">Salary Cap</h3>
          {overCap && (
            <span className="ml-auto text-[10px] uppercase tracking-widest font-bold text-destructive">
              ⚠ Over Cap
            </span>
          )}
        </div>
      </div>

      <div className="p-6">
        <div className="mb-6">
          <div className="flex justify-between text-xs text-muted-foreground mb-2">
            <span>Used: {formatCurrency(capUsed)}</span>
            <span>Limit: {formatCurrency(capLimit)}</span>
          </div>
          <div className="h-3 rounded-full bg-secondary overflow-hidden" data-testid="salary-cap-bar">
            <div
              className={`h-full rounded-full transition-all ${overCap ? "bg-destructive" : "bg-primary"}`}
              style={{ width: `${capLimit > 0 ? Math.min((capUsed / capLimit) * 100, 100) : 0}%` }}
            />
          </div>
          {overReason && (
            <p className="text-xs text-destructive mt-2 font-medium" data-testid="salary-cap-over-detail">
              {overReason.detail}
            </p>
          )}
        </div>

        <div className="grid grid-cols-3 gap-4">
          {items.map((item) => (
            <div key={item.label} className="text-center p-3 rounded-lg bg-secondary/30">
              <p className="text-xs text-muted-foreground mb-1">{item.label}</p>
              <p
                className={`text-sm font-bold ${
                  item.accent
                    ? item.negative
                      ? "text-destructive"
                      : "text-success"
                    : "text-foreground"
                }`}
              >
                {item.negative ? "−" : ""}
                {item.value}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default TeamSalaryCap;
