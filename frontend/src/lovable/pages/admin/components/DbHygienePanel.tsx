/* Iter 231ag — Platform admin DB Hygiene panel.

   Surfaces counts of suspect rows (test prefixes, @example.com users,
   zombie drafts, orphan leagues, polluting player names) and a one-
   click "Sweep now" button. Same regex the conftest uses; gated to
   platform admins server-side (this UI also disables the button if
   the user isn't a platform admin, but server enforces the truth).
*/
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, RefreshCw, Trash2, AlertTriangle, Database, Users, ListChecks, FileX, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

interface ReportCounts {
  polluting_players: number;
  ephemeral_leagues: number;
  test_users: number;
  zombie_drafts: number;
  orphan_leagues: number;
  orphan_teams: number;
  total_players: number;
  total_leagues: number;
  total_users: number;
  total_drafts: number;
  total_teams: number;
}

interface SweepResult {
  ran_at: string;
  ran_by: string;
  before: ReportCounts;
  after: ReportCounts;
  deletions: Record<string, number>;
}

const BUCKETS: Array<{
  key: keyof Pick<ReportCounts,
    "polluting_players" | "ephemeral_leagues" | "test_users" |
    "zombie_drafts" | "orphan_leagues" | "orphan_teams"
  >;
  label: string;
  description: string;
  icon: typeof Database;
  totalKey: keyof ReportCounts;
}> = [
  {
    key: "polluting_players",
    label: "Polluting players",
    description: "Test-seed names (ForceP-*, NHL Veteran Forward …) or rows tagged _test_seed=True",
    icon: Database,
    totalKey: "total_players",
  },
  {
    key: "ephemeral_leagues",
    label: "Ephemeral leagues",
    description: "Test prefixes (iter*-, TEST_*) or rows tagged _test_seed=True",
    icon: ListChecks,
    totalKey: "total_leagues",
  },
  {
    key: "test_users",
    label: "Test users",
    description: "@example.com domain (RFC-reserved test domain) or tagged _test_seed=True",
    icon: Users,
    totalKey: "total_users",
  },
  {
    key: "zombie_drafts",
    label: "Zombie drafts",
    description: "status=active with empty team_abbrs (would crash the pick-timer worker)",
    icon: FileX,
    totalKey: "total_drafts",
  },
  {
    key: "orphan_leagues",
    label: "Orphan leagues",
    description: "commissioner_id no longer resolves to a real user",
    icon: AlertTriangle,
    totalKey: "total_leagues",
  },
  {
    key: "orphan_teams",
    label: "Orphan teams",
    description: "league_id no longer resolves to a real league",
    icon: AlertTriangle,
    totalKey: "total_teams",
  },
];

export const DbHygienePanel = () => {
  const [report, setReport] = useState<ReportCounts | null>(null);
  const [loading, setLoading] = useState(true);
  const [sweeping, setSweeping] = useState(false);
  const [lastSweep, setLastSweep] = useState<SweepResult | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get<ReportCounts>("/admin/db-hygiene/report");
      setReport(data);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Couldn't load DB hygiene report");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const totalIssues = report
    ? BUCKETS.reduce((sum, b) => sum + (report[b.key] || 0), 0)
    : 0;

  const runSweep = async () => {
    if (!window.confirm(
      `Run the database hygiene sweep now? This will permanently delete ${totalIssues} suspect rows ` +
      `+ all their dependent teams / drafts / claims / budgets / invites. This cannot be undone.`
    )) {
      return;
    }
    setSweeping(true);
    try {
      const { data } = await api.post<SweepResult>("/admin/db-hygiene/sweep");
      setLastSweep(data);
      setReport(data.after);
      const swept = Object.values(data.deletions).reduce((a, b) => a + (b || 0), 0);
      toast.success(`Sweep complete — removed ${swept} rows across all buckets.`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Sweep failed");
    } finally {
      setSweeping(false);
    }
  };

  return (
    <Card data-testid="db-hygiene-panel">
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-sky-400" />
              Database Hygiene
            </CardTitle>
            <p className="text-xs text-muted-foreground max-w-2xl">
              Surfaces suspect rows that test files leak into the live preview DB —
              test-prefix players, @example.com users, zombie drafts, orphan leagues.
              Same regexes the pytest conftest uses; cascades are honoured (deleting a
              league wipes its teams/drafts/claims). Platform admins only.
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={load}
              disabled={loading || sweeping}
              data-testid="db-hygiene-refresh-btn"
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              <span className="ml-1.5">Refresh</span>
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={runSweep}
              disabled={loading || sweeping || totalIssues === 0}
              className="bg-red-500 hover:bg-red-600 text-white"
              data-testid="db-hygiene-sweep-btn"
            >
              {sweeping ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
              <span className="ml-1.5">
                {totalIssues === 0 ? "All clean" : `Sweep now (${totalIssues})`}
              </span>
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {report && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {BUCKETS.map((bucket) => {
              const count = report[bucket.key] || 0;
              const total = (report[bucket.totalKey] as number) || 0;
              const pct = total > 0 ? ((count / total) * 100).toFixed(1) : "0";
              const Icon = bucket.icon;
              return (
                <div
                  key={bucket.key}
                  className={`rounded-md border p-3 space-y-2 ${
                    count > 0 ? "border-red-500/40 bg-red-500/5" : "border-emerald-500/30 bg-emerald-500/5"
                  }`}
                  data-testid={`db-hygiene-bucket-${bucket.key}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Icon className={`h-4 w-4 ${count > 0 ? "text-red-400" : "text-emerald-400"}`} />
                      <span className="text-xs font-medium">{bucket.label}</span>
                    </div>
                    <Badge
                      variant="outline"
                      className={count > 0
                        ? "border-red-500/40 text-red-300 bg-red-500/10"
                        : "border-emerald-500/40 text-emerald-300 bg-emerald-500/10"}
                    >
                      {count}
                    </Badge>
                  </div>
                  <p className="text-[10px] text-muted-foreground leading-snug">{bucket.description}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {count} / {total} ({pct}%)
                  </p>
                </div>
              );
            })}
          </div>
        )}

        {lastSweep && (
          <div
            className="rounded-md border border-sky-500/30 bg-sky-500/5 p-3 text-xs space-y-1"
            data-testid="db-hygiene-last-sweep"
          >
            <p className="font-medium text-sky-300">
              Last sweep — {new Date(lastSweep.ran_at).toLocaleString()} by {lastSweep.ran_by}
            </p>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-muted-foreground">
              {Object.entries(lastSweep.deletions)
                .filter(([, v]) => (v as number) > 0)
                .map(([k, v]) => (
                  <span key={k}>
                    {k.replace(/_/g, " ")}: <span className="text-foreground">{v as number}</span>
                  </span>
                ))}
              {Object.values(lastSweep.deletions).every((v) => (v as number) === 0) && (
                <span className="italic">Nothing to remove — DB was already clean.</span>
              )}
            </div>
          </div>
        )}

        {report && totalIssues === 0 && !lastSweep && (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-xs text-emerald-200">
            <ShieldCheck className="inline h-3.5 w-3.5 mr-1" />
            Database is clean — no pollution detected across any bucket.
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default DbHygienePanel;
