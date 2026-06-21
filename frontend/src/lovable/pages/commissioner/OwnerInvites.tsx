// @ts-nocheck
/**
 * Iter 193 — Bulk Owner Invites for pending-team leagues.
 *
 * Pre-seed each team with an email address, then send the whole batch
 * in one click. Re-uses backend `/leagues/{id}/pending-team-invites/bulk`
 * which itself delegates to the existing SendGrid + `league_invites`
 * audit infrastructure.
 *
 * Supports two input modes:
 *   1. Inline per-row email field — fastest for small leagues.
 *   2. CSV upload (`team_name,email` per line — header row optional) —
 *      ideal for 32-team entry drafts where the commissioner already
 *      has the manifest in a spreadsheet.
 */
import { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Mail, Upload, RefreshCw, AlertTriangle, CheckCircle2 } from "lucide-react";

function statusBadgeProps(status) {
  switch (status) {
    case "accepted":
      return { label: "Accepted", className: "border-emerald-500/40 text-emerald-300 bg-emerald-500/10" };
    case "sent":
      return { label: "Sent", className: "border-blue-500/40 text-blue-300 bg-blue-500/10" };
    case "mocked":
      return { label: "Mock-sent", className: "border-purple-500/40 text-purple-300 bg-purple-500/10" };
    case "pending":
      return { label: "Pending", className: "border-amber-500/40 text-amber-300 bg-amber-500/10" };
    case "error":
      return { label: "Error", className: "border-destructive/40 text-destructive bg-destructive/10" };
    default:
      return { label: "No email", className: "border-border text-muted-foreground bg-secondary/50" };
  }
}

export default function OwnerInvites() {
  const { league } = useActiveLeague();
  const leagueId = league?.id || league?._id;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [emails, setEmails] = useState({}); // team_id → email
  const [sending, setSending] = useState(false);

  const load = async () => {
    if (!leagueId) return;
    setLoading(true);
    try {
      const r = await api.get(`/leagues/${leagueId}/pending-team-invites`);
      setData(r.data);
      const seed = {};
      (r.data?.teams || []).forEach((t) => {
        if (t.invite_email) seed[t.team_id] = t.invite_email;
      });
      setEmails(seed);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load pending teams");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [leagueId]);

  const onCsvUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !data) return;
    const text = await file.text();
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    // Skip header row when it doesn't have an @ — i.e. when row 1 is
    // literally "team_name,email" we drop it.
    const dataRows = lines[0] && !lines[0].includes("@") ? lines.slice(1) : lines;
    const teamByName = new Map(
      (data.teams || []).map((t) => [t.team_name.toLowerCase(), t]),
    );
    const teamByAbbr = new Map(
      (data.teams || []).map((t) => [t.abbreviation?.toLowerCase(), t]),
    );
    const next = { ...emails };
    let matched = 0;
    let unmatched = 0;
    for (const line of dataRows) {
      const [rawName, rawEmail] = line.split(",").map((s) => s?.trim());
      if (!rawName || !rawEmail) { unmatched++; continue; }
      const t = teamByName.get(rawName.toLowerCase())
        || teamByAbbr.get(rawName.toLowerCase());
      if (t) {
        next[t.team_id] = rawEmail;
        matched++;
      } else {
        unmatched++;
      }
    }
    setEmails(next);
    toast.success(`Mapped ${matched} email(s)${unmatched ? ` · ${unmatched} unmatched` : ""}`);
  };

  const onSubmit = async () => {
    if (!leagueId) return;
    const rows = Object.entries(emails)
      .filter(([, email]) => email && email.includes("@"))
      .map(([team_id, email]) => ({ team_id, email }));
    if (rows.length === 0) {
      toast.error("Add at least one email first");
      return;
    }
    if (!window.confirm(`Send invite emails to ${rows.length} owner(s)?`)) return;
    setSending(true);
    try {
      const r = await api.post(`/leagues/${leagueId}/pending-team-invites/bulk`, { rows });
      const sent = r.data?.sent ?? 0;
      const errCount = (r.data?.errors || []).length;
      toast.success(`Sent ${sent} invite(s)${errCount ? ` · ${errCount} error(s)` : ""}`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Bulk invite failed");
    } finally {
      setSending(false);
    }
  };

  const stats = useMemo(() => {
    const teams = data?.teams || [];
    return {
      total: teams.length,
      accepted: teams.filter((t) => t.status === "accepted").length,
      sent: teams.filter((t) => ["sent", "mocked"].includes(t.status)).length,
      noEmail: teams.filter((t) => t.status === "no_email").length,
    };
  }, [data]);

  if (!leagueId) {
    return (
      <div className="p-6" data-testid="owner-invites-no-league">
        <p className="text-sm text-muted-foreground">Select a league first.</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto" data-testid="owner-invites">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Owner Invites</h1>
          <p className="text-sm text-muted-foreground">
            {data?.league_name ? `${data.league_name} — ` : ""}
            Pre-seed each team with the owner's email, then send everything in one click.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="cursor-pointer">
            <input type="file" accept=".csv" onChange={onCsvUpload} className="hidden" data-testid="owner-invites-csv-input" />
            <Button variant="outline" size="sm" asChild>
              <span><Upload className="h-4 w-4 mr-1.5" /> CSV upload</span>
            </Button>
          </label>
          <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="owner-invites-refresh">
            <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Summary pills */}
      <div className="flex flex-wrap gap-2 text-sm">
        <Badge variant="outline" className="px-3 py-1" data-testid="owner-invites-stat-total">{stats.total} teams</Badge>
        <Badge variant="outline" className="border-emerald-500/40 text-emerald-300 bg-emerald-500/10 px-3 py-1" data-testid="owner-invites-stat-accepted">
          {stats.accepted} accepted
        </Badge>
        <Badge variant="outline" className="border-blue-500/40 text-blue-300 bg-blue-500/10 px-3 py-1" data-testid="owner-invites-stat-sent">
          {stats.sent} invited
        </Badge>
        <Badge variant="outline" className="border-amber-500/40 text-amber-300 bg-amber-500/10 px-3 py-1" data-testid="owner-invites-stat-no-email">
          {stats.noEmail} need email
        </Badge>
      </div>

      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Mail className="h-4 w-4" /> Per-team owner emails
          </CardTitle>
          <Button onClick={onSubmit} disabled={sending} data-testid="owner-invites-send-all">
            {sending ? "Sending…" : "Invite All"}
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-xs text-muted-foreground py-8 text-center">Loading…</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="owner-invites-table">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th className="text-left py-2 w-12">#</th>
                    <th className="text-left py-2">Team</th>
                    <th className="text-left py-2 w-56">Owner email</th>
                    <th className="text-right py-2 w-32">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.teams || []).map((t) => {
                    const badge = statusBadgeProps(t.status);
                    const accepted = t.status === "accepted";
                    return (
                      <tr
                        key={t.team_id}
                        className="border-b border-border/40"
                        data-testid={`owner-invites-row-${t.team_id}`}
                      >
                        <td className="py-2 text-muted-foreground">{t.draft_position ?? "—"}</td>
                        <td className="py-2">
                          <span className="font-semibold">{t.team_name}</span>
                          {t.abbreviation && (
                            <span className="text-muted-foreground ml-2 text-xs">{t.abbreviation}</span>
                          )}
                          {accepted && t.owner_name && (
                            <span className="text-xs text-emerald-300 ml-2">· {t.owner_name}</span>
                          )}
                        </td>
                        <td className="py-2">
                          <Input
                            type="email"
                            value={emails[t.team_id] || ""}
                            onChange={(e) => setEmails((prev) => ({ ...prev, [t.team_id]: e.target.value }))}
                            disabled={accepted}
                            placeholder="owner@example.com"
                            className="h-8 text-sm"
                            data-testid={`owner-invites-email-${t.team_id}`}
                          />
                        </td>
                        <td className="py-2 text-right">
                          <Badge variant="outline" className={`text-[10px] ${badge.className}`}>
                            {accepted && <CheckCircle2 className="h-3 w-3 mr-1 inline" />}
                            {!accepted && t.status === "error" && <AlertTriangle className="h-3 w-3 mr-1 inline" />}
                            {badge.label}
                          </Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        💡 Tip: CSV format is <code className="text-foreground/80">team_name,email</code> per line.
        Matching is case-insensitive against team name or abbreviation.
      </p>

      <div className="pt-2">
        <Link to="/commissioner/ops-console" className="text-xs text-primary hover:underline">
          ← Back to Ops Console
        </Link>
      </div>
    </div>
  );
}
