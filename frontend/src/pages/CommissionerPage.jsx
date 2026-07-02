import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Settings, Shield, Users, Calendar, DollarSign, Gavel, Play, Trash2, AlertTriangle, CheckCircle2, Clock, Sparkles, Loader2, ClipboardList, Gift } from "lucide-react";
import { Link } from "react-router-dom";
import DraftStatusStrip from "@/components/DraftStatusStrip";
import { cn } from "@/lib/utils";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

export default function CommissionerPage() {
  const { user } = useAuth();
  const [leagues, setLeagues] = useState([]);
  const [selectedLeague, setSelectedLeague] = useState(null);
  const [teams, setTeams] = useState([]);
  const [pendingClaims, setPendingClaims] = useState([]);
  const [pendingTrades, setPendingTrades] = useState([]);
  const [matchupInfo, setMatchupInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);
  const [premium, setPremium] = useState(null);
  const [upgrading, setUpgrading] = useState(false);
  // Iter 232k — Draft-tab countdown state. `nextDraft` is the closest
  // upcoming draft (status != completed/cancelled). `bonusCount`
  // mirrors `nextDraft.bonus_picks.length` so the pill can render
  // "N bonus picks configured" without a second render round-trip.
  const [nextDraft, setNextDraft] = useState(null);
  const [nextDraftBonusCount, setNextDraftBonusCount] = useState(0);

  useEffect(() => {
    const init = async () => {
      try {
        const { data } = await api.get("/leagues?my_leagues=true");
        const commissionerLeagues = data.filter(l => l.commissioner_id === user?.id);
        setLeagues(commissionerLeagues);
        if (commissionerLeagues.length > 0) {
          setSelectedLeague(commissionerLeagues[0]);
        }
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    init();
  }, [user]);

  useEffect(() => {
    if (!selectedLeague) return;
    const fetch = async () => {
      try {
        const [teamsRes, claimsRes, tradesRes, weekRes, premiumRes, draftsRes] = await Promise.all([
          api.get(`/teams?league_id=${selectedLeague.id}`),
          api.get(`/waivers/claims?league_id=${selectedLeague.id}&status=pending`),
          api.get(`/trades?league_id=${selectedLeague.id}&status=pending`),
          api.get(`/matchups/${selectedLeague.id}/current-week`).catch(() => ({ data: { week: 1, matchups: [] } })),
          api.get(`/leagues/${selectedLeague.id}/premium`).catch(() => ({ data: null })),
          // Iter 232k — Pull the drafts list so the Draft tab card
          // can surface the *next* scheduled draft's countdown +
          // config snapshot. Falls back to an empty list on error
          // so a broken drafts endpoint doesn't break the whole page.
          api.get(`/drafts?league_id=${selectedLeague.id}`).catch(() => ({ data: [] })),
        ]);
        setTeams(teamsRes.data);
        setPendingClaims(claimsRes.data);
        setPendingTrades(tradesRes.data);
        setMatchupInfo(weekRes.data);
        setPremium(premiumRes.data);
        // Find the next upcoming draft (scheduled | active | preview),
        // sorted by `scheduled_at` ascending. Completed drafts are
        // filtered out so the pill doesn't show yesterday's league.
        const drafts = Array.isArray(draftsRes.data)
          ? draftsRes.data
          : (draftsRes.data?.drafts || []);
        const now = Date.now();
        const upcoming = drafts
          .filter((d) => {
            const s = String(d.status || "").toLowerCase();
            return s !== "completed" && s !== "cancelled" && s !== "archived";
          })
          .map((d) => {
            // Iter 232k — Different draft rows use either `scheduled_at`
            // or `scheduled_time` depending on when they were created.
            // Normalise to a single `_scheduled_at_ms` field so the
            // downstream sort + strip render don't have to care.
            const raw = d.scheduled_at || d.scheduled_time || null;
            return {
              ...d,
              scheduled_at: raw, // canonicalise for the strip prop
              _scheduled_at_ms: raw ? Date.parse(raw) : null,
            };
          })
          .filter((d) => d._scheduled_at_ms !== null)
          // Prefer future drafts; if all are past-scheduled + still
          // active, sort by the freshest one anyway so we surface
          // whichever the commissioner is currently running.
          .sort((a, b) => {
            const aFuture = a._scheduled_at_ms >= now ? 0 : 1;
            const bFuture = b._scheduled_at_ms >= now ? 0 : 1;
            if (aFuture !== bFuture) return aFuture - bFuture;
            return a._scheduled_at_ms - b._scheduled_at_ms;
          });
        const next = upcoming[0] || null;
        setNextDraft(next);
        // If we found a next draft, also pull its bonus-picks so the
        // pill can show "N bonus picks configured". Silent failure
        // (e.g. non-commissioner would 403) simply leaves the count
        // at 0.
        if (next?._id || next?.id) {
          try {
            const draftId = next._id || next.id;
            const { data: bpData } = await api.get(`/drafts/${draftId}/bonus-picks`);
            setNextDraftBonusCount((bpData?.bonus_picks || []).length);
          } catch { setNextDraftBonusCount(0); }
        } else {
          setNextDraftBonusCount(0);
        }
      } catch (e) { console.error(e); }
    };
    fetch();
  }, [selectedLeague]);

  const handleUpgradePremium = async () => {
    if (!selectedLeague) return;
    setUpgrading(true);
    try {
      const { data } = await api.post(`/payments/create`, {
        package_type: "league_premium",
        league_id: selectedLeague.id,
        origin_url: window.location.origin,
      });
      if (data?.url) window.location.href = data.url;
    } catch (e) {
      alert(formatApiError(e));
      setUpgrading(false);
    }
  };

  const handleProcessWaivers = async () => {
    if (!selectedLeague) return;
    setProcessing(true);
    try {
      const { data } = await api.post(`/waivers/process?league_id=${selectedLeague.id}`);
      alert(`Processed ${data.processed} claims!\n${data.results?.map(r => `${r.player}: Won by ${r.winner} ($${r.bid})`).join("\n") || ""}`);
      const claimsRes = await api.get(`/waivers/claims?league_id=${selectedLeague.id}&status=pending`);
      setPendingClaims(claimsRes.data);
    } catch (e) { alert(formatApiError(e)); }
    setProcessing(false);
  };

  const handleGenerateSchedule = async () => {
    if (!selectedLeague) return;
    setGenerating(true);
    try {
      const { data } = await api.post("/matchups/generate-schedule", { league_id: selectedLeague.id, num_weeks: 18 });
      alert(data.message);
      const weekRes = await api.get(`/matchups/${selectedLeague.id}/current-week`);
      setMatchupInfo(weekRes.data);
    } catch (e) { alert(formatApiError(e)); }
    setGenerating(false);
  };

  const handleSimulateWeek = async () => {
    if (!selectedLeague || !matchupInfo) return;
    setSimulating(true);
    try {
      const { data } = await api.post("/matchups/simulate-week", { league_id: selectedLeague.id, week: matchupInfo.week });
      alert(`Week ${matchupInfo.week} simulated!\n${data.results?.map(r => `${r.home} ${r.home_score} - ${r.away_score} ${r.away}`).join("\n") || ""}`);
      const [teamsRes, weekRes] = await Promise.all([
        api.get(`/teams?league_id=${selectedLeague.id}`),
        api.get(`/matchups/${selectedLeague.id}/current-week`),
      ]);
      setTeams(teamsRes.data);
      setMatchupInfo(weekRes.data);
    } catch (e) { alert(formatApiError(e)); }
    setSimulating(false);
  };

  const handleVetoTrade = async (tradeId) => {
    try {
      await api.post(`/trades/${tradeId}/vote`, { vote: "veto" });
      const tradesRes = await api.get(`/trades?league_id=${selectedLeague.id}&status=pending`);
      setPendingTrades(tradesRes.data);
    } catch (e) { alert(formatApiError(e)); }
  };

  if (loading) {
    return <AppLayout><div className="flex items-center justify-center h-[60vh] text-[#A1A1AA]">Loading...</div></AppLayout>;
  }

  if (leagues.length === 0) {
    return (
      <AppLayout>
        <div className="text-center py-20">
          <Shield className="h-16 w-16 text-[#52525B] mx-auto mb-4" />
          <h2 className="text-xl text-white mb-2">No Commissioner Access</h2>
          <p className="text-[#A1A1AA]">You are not a commissioner of any league</p>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="space-y-6" data-testid="commissioner-page">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Shield className="h-6 w-6 text-[#00D2FF]" />
              Commissioner Tools
            </h1>
            <p className="text-[#A1A1AA]">Manage your league settings, matchups, waivers, and trades</p>
          </div>
          {leagues.length > 1 && (
            <Select value={selectedLeague?.id} onValueChange={(v) => setSelectedLeague(leagues.find(l => l.id === v))}>
              <SelectTrigger className="w-48 bg-[#141414] border-white/10 text-white"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-[#141414] border-white/10">
                {leagues.map(l => <SelectItem key={l.id} value={l.id} className="text-white">{l.name}</SelectItem>)}
              </SelectContent>
            </Select>
          )}
        </div>

        {/* Overview Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="border-white/10">
            <CardContent className="p-5">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-[#00D2FF]/20 flex items-center justify-center"><Users className="h-5 w-5 text-[#00D2FF]" /></div>
                <div>
                  <p className="text-sm text-[#A1A1AA]">Teams</p>
                  <p className="text-xl font-bold text-white" data-testid="teams-count">{teams.length}/{selectedLeague?.max_teams}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-white/10">
            <CardContent className="p-5">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-[#FF9F0A]/20 flex items-center justify-center"><Clock className="h-5 w-5 text-[#FF9F0A]" /></div>
                <div>
                  <p className="text-sm text-[#A1A1AA]">Pending Claims</p>
                  <p className="text-xl font-bold text-white" data-testid="claims-count">{pendingClaims.length}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-white/10">
            <CardContent className="p-5">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-[#FF3B30]/20 flex items-center justify-center"><Gavel className="h-5 w-5 text-[#FF3B30]" /></div>
                <div>
                  <p className="text-sm text-[#A1A1AA]">Pending Trades</p>
                  <p className="text-xl font-bold text-white" data-testid="trades-count">{pendingTrades.length}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-white/10">
            <CardContent className="p-5">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-[#34C759]/20 flex items-center justify-center"><Calendar className="h-5 w-5 text-[#34C759]" /></div>
                <div>
                  <p className="text-sm text-[#A1A1AA]">Current Week</p>
                  <p className="text-xl font-bold text-white">{matchupInfo?.week || "—"}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <Tabs defaultValue="season">
          <TabsList>
            <TabsTrigger value="season">Season Management</TabsTrigger>
            <TabsTrigger value="draft" data-testid="commissioner-draft-tab-trigger">Draft</TabsTrigger>
            <TabsTrigger value="waivers">Waivers ({pendingClaims.length})</TabsTrigger>
            <TabsTrigger value="trades">Trades ({pendingTrades.length})</TabsTrigger>
            <TabsTrigger value="teams">Teams ({teams.length})</TabsTrigger>
            <TabsTrigger value="premium" data-testid="premium-tab-trigger">Premium</TabsTrigger>
          </TabsList>

          {/* Season Management */}
          <TabsContent value="season" className="space-y-4 mt-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card className="border-white/10">
                <CardHeader>
                  <CardTitle className="text-white flex items-center gap-2"><Calendar className="h-5 w-5 text-[#00D2FF]" />Schedule</CardTitle>
                  <CardDescription className="text-[#A1A1AA]">Generate or manage the season schedule</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Button className="w-full bg-[#00D2FF] text-black hover:bg-[#33DBFF]" onClick={handleGenerateSchedule} disabled={generating} data-testid="generate-schedule-btn">
                    <Calendar className="h-4 w-4 mr-2" />{generating ? "Generating..." : "Generate 18-Week Schedule"}
                  </Button>
                  <p className="text-xs text-[#A1A1AA]">Creates round-robin matchups for all teams. Warning: replaces existing schedule.</p>
                </CardContent>
              </Card>

              <Card className="border-white/10">
                <CardHeader>
                  <CardTitle className="text-white flex items-center gap-2"><Play className="h-5 w-5 text-[#34C759]" />Simulation</CardTitle>
                  <CardDescription className="text-[#A1A1AA]">Simulate the current week&apos;s matchups</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Button className="w-full bg-[#34C759] text-black hover:bg-[#34C759]/80" onClick={handleSimulateWeek} disabled={simulating} data-testid="simulate-week-btn">
                    <Play className="h-4 w-4 mr-2" />{simulating ? "Simulating..." : `Simulate Week ${matchupInfo?.week || 1}`}
                  </Button>
                  <p className="text-xs text-[#A1A1AA]">Calculates fantasy points from rosters and determines W/L results.</p>
                </CardContent>
              </Card>
            </div>

            {/* League Info */}
            <Card className="border-white/10">
              <CardHeader>
                <CardTitle className="text-white">League Settings</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div><Label className="text-[#A1A1AA] text-xs">Format</Label><p className="text-white font-medium capitalize">{selectedLeague?.format?.replace('_', ' ')}</p></div>
                  <div><Label className="text-[#A1A1AA] text-xs">Scoring</Label><p className="text-white font-medium capitalize">{selectedLeague?.scoring_format?.replace(/_/g, ' ')}</p></div>
                  <div><Label className="text-[#A1A1AA] text-xs">Draft Type</Label><p className="text-white font-medium capitalize">{selectedLeague?.draft_type}</p></div>
                  <div><Label className="text-[#A1A1AA] text-xs">Roster Spots</Label><p className="text-white font-medium">{selectedLeague?.roster_spots}</p></div>
                  <div><Label className="text-[#A1A1AA] text-xs">Entry Fee</Label><p className="text-white font-medium">{selectedLeague?.entry_fee ? `$${selectedLeague.entry_fee}` : "Free"}</p></div>
                  <div><Label className="text-[#A1A1AA] text-xs">Salary Cap</Label><p className="text-white font-medium">{selectedLeague?.salary_cap ? `$${selectedLeague.salary_cap}` : "Disabled"}</p></div>
                  <div><Label className="text-[#A1A1AA] text-xs">Privacy</Label><p className="text-white font-medium">{selectedLeague?.is_private ? "Private" : "Public"}</p></div>
                  <div><Label className="text-[#A1A1AA] text-xs">Status</Label><Badge className="mt-1">{selectedLeague?.status}</Badge></div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Iter 232j — Draft tab surfaces the draft management flows
              (Scheduled Drafts + bonus picks + draft order + auction
              settings + lottery) directly at the /commissioner top
              level. The full editing UI lives at
              /commissioner/settings?tab=draft (Lovable Commissioner
              Settings) so this tab is a curated launchpad rather than
              a duplicate — cheap to render, deep-links preserve state,
              and reviewers no longer have to hunt through League
              Administration to find compensation/expansion picks. */}
          <TabsContent value="draft" className="space-y-4 mt-4" data-testid="commissioner-draft-tab-content">
            <Card className="border-white/10">
              <CardHeader>
                <CardTitle className="text-white flex items-center gap-2">
                  <Gavel className="h-5 w-5 text-[#00D2FF]" />
                  Draft Management
                </CardTitle>
                <CardDescription className="text-[#A1A1AA]">
                  Schedule drafts, edit settings, and grant compensation or expansion picks.
                </CardDescription>
                {/* Iter 232k — Live status strip. When the league has
                    a scheduled draft on the books, this pill turns
                    the tab from a passive launchpad into a game-day
                    dashboard: countdown + config snapshot at a glance. */}
                <DraftStatusStrip
                  nextDraft={nextDraft}
                  bonusCount={nextDraftBonusCount}
                  teamCount={teams.length}
                  maxTeams={selectedLeague?.max_teams}
                  unclaimedSeats={
                    (selectedLeague?.max_teams || teams.length) -
                    teams.filter((t) => t.owner_id).length
                  }
                />
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <Link
                    to="/commissioner/settings?tab=draft"
                    className="group flex items-start gap-3 rounded-lg border border-white/10 bg-white/[0.03] p-4 hover:bg-white/[0.06] transition-colors"
                    data-testid="commissioner-draft-open-scheduled"
                  >
                    <ClipboardList className="h-5 w-5 text-[#00D2FF] shrink-0 mt-0.5" />
                    <div>
                      <p className="text-white font-medium">Scheduled Drafts</p>
                      <p className="text-xs text-[#A1A1AA] mt-0.5">
                        Create, edit, or reschedule drafts. Configure snake/linear, rounds, timer, and player pool criteria.
                      </p>
                    </div>
                  </Link>
                  <Link
                    to="/commissioner/settings?tab=draft"
                    className="group flex items-start gap-3 rounded-lg border border-white/10 bg-white/[0.03] p-4 hover:bg-white/[0.06] transition-colors"
                    data-testid="commissioner-draft-open-bonus-picks"
                  >
                    <Gift className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-white font-medium">Bonus Picks (Compensation / Expansion)</p>
                      <p className="text-xs text-[#A1A1AA] mt-0.5">
                        Grant extra picks to specific teams — pre- or mid-draft. Insert at end of a round or a specific overall pick.
                      </p>
                    </div>
                  </Link>
                  <Link
                    to="/commissioner/settings?tab=draft"
                    className="group flex items-start gap-3 rounded-lg border border-white/10 bg-white/[0.03] p-4 hover:bg-white/[0.06] transition-colors"
                    data-testid="commissioner-draft-open-order"
                  >
                    <Users className="h-5 w-5 text-[#34C759] shrink-0 mt-0.5" />
                    <div>
                      <p className="text-white font-medium">Draft Order</p>
                      <p className="text-xs text-[#A1A1AA] mt-0.5">
                        Set the pick order for the next draft — manual, lottery, or by reverse standings.
                      </p>
                    </div>
                  </Link>
                  <Link
                    to="/commissioner/settings?tab=draft"
                    className="group flex items-start gap-3 rounded-lg border border-white/10 bg-white/[0.03] p-4 hover:bg-white/[0.06] transition-colors"
                    data-testid="commissioner-draft-open-lottery"
                  >
                    <Sparkles className="h-5 w-5 text-purple-400 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-white font-medium">Lottery &amp; Chat Settings</p>
                      <p className="text-xs text-[#A1A1AA] mt-0.5">
                        Configure the lottery odds, prospect-only draft toggle, and in-draft chat behavior.
                      </p>
                    </div>
                  </Link>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Waivers */}
          <TabsContent value="waivers" className="space-y-4 mt-4">
            <Card className="border-white/10">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-white">Pending Waiver Claims</CardTitle>
                  {pendingClaims.length > 0 && (
                    <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]" onClick={handleProcessWaivers} disabled={processing} data-testid="process-waivers-btn">
                      <Gavel className="h-4 w-4 mr-2" />{processing ? "Processing..." : "Process All Claims"}
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {pendingClaims.length === 0 ? (
                  <p className="text-[#A1A1AA] text-center py-8">No pending claims</p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow className="border-white/10">
                        <TableHead className="text-[#A1A1AA]">Team</TableHead>
                        <TableHead className="text-[#A1A1AA]">Player</TableHead>
                        <TableHead className="text-right text-[#A1A1AA]">Bid</TableHead>
                        <TableHead className="text-[#A1A1AA]">Drop</TableHead>
                        <TableHead className="text-[#A1A1AA]">Submitted</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {pendingClaims.map(claim => (
                        <TableRow key={claim._id} className="border-white/10">
                          <TableCell className="text-white font-medium">{claim.team_name}</TableCell>
                          <TableCell><span className="text-white">{claim.player_name}</span> <Badge variant="outline" className="ml-1 text-xs">{claim.player_position}</Badge></TableCell>
                          <TableCell className="text-right font-semibold text-[#00D2FF]">${claim.bid_amount}</TableCell>
                          <TableCell className="text-[#A1A1AA]">{claim.drop_player_name || "—"}</TableCell>
                          <TableCell className="text-[#A1A1AA] text-sm">{new Date(claim.created_at).toLocaleDateString()}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Trades */}
          <TabsContent value="trades" className="space-y-4 mt-4">
            <Card className="border-white/10">
              <CardHeader><CardTitle className="text-white">Pending Trades</CardTitle></CardHeader>
              <CardContent>
                {pendingTrades.length === 0 ? (
                  <p className="text-[#A1A1AA] text-center py-8">No pending trades</p>
                ) : pendingTrades.map(trade => (
                  <div key={trade._id} className="p-4 rounded-lg bg-[#1A1A1A]/30 mb-3">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-[#FF9F0A] border-[#FF9F0A]/30"><Clock className="h-3 w-3 mr-1" />Pending</Badge>
                        <span className="text-white font-medium">{trade.proposer_team_name} ↔ {trade.target_team_name}</span>
                      </div>
                      <div className="flex gap-2">
                        <Button variant="outline" size="sm" className="text-[#FF3B30] border-[#FF3B30]/30" onClick={() => handleVetoTrade(trade._id)} data-testid={`veto-${trade._id}`}>
                          <AlertTriangle className="h-3.5 w-3.5 mr-1" />Veto
                        </Button>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <p className="text-[#A1A1AA] mb-1">{trade.proposer_team_name} sends:</p>
                        {(trade.assets_offered || []).map((a, i) => <p key={i} className="text-white">{a.player_name || `${a.pick_year} ${a.pick_round}`}</p>)}
                      </div>
                      <div>
                        <p className="text-[#A1A1AA] mb-1">{trade.target_team_name} sends:</p>
                        {(trade.assets_requested || []).map((a, i) => <p key={i} className="text-white">{a.player_name || `${a.pick_year} ${a.pick_round}`}</p>)}
                      </div>
                    </div>
                    <p className="text-xs text-[#A1A1AA] mt-2">Votes: {trade.votes?.approve || 0} approve / {trade.votes?.veto || 0} veto</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Teams */}
          <TabsContent value="teams" className="mt-4">
            <Card className="border-white/10">
              <CardHeader><CardTitle className="text-white">League Teams</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow className="border-white/10">
                      <TableHead className="text-[#A1A1AA]">Team</TableHead>
                      <TableHead className="text-[#A1A1AA]">Owner</TableHead>
                      <TableHead className="text-center text-[#A1A1AA]">W</TableHead>
                      <TableHead className="text-center text-[#A1A1AA]">L</TableHead>
                      <TableHead className="text-center text-[#A1A1AA]">T</TableHead>
                      <TableHead className="text-right text-[#A1A1AA]">PF</TableHead>
                      <TableHead className="text-right text-[#A1A1AA]">PA</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {teams.map(team => (
                      <TableRow key={team.id} className="border-white/10">
                        <TableCell className="text-white font-medium">{team.name}</TableCell>
                        <TableCell className="text-[#A1A1AA]">{team.owner_name}</TableCell>
                        <TableCell className="text-center text-white">{team.wins}</TableCell>
                        <TableCell className="text-center text-white">{team.losses}</TableCell>
                        <TableCell className="text-center text-white">{team.ties}</TableCell>
                        <TableCell className="text-right text-white">{team.points_for?.toFixed(1) || 0}</TableCell>
                        <TableCell className="text-right text-white">{team.points_against?.toFixed(1) || 0}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="premium" className="space-y-4 mt-4">
            <Card data-testid="premium-tab-card">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-[#00D2FF]" />
                  League Premium
                  {premium?.premium && (
                    <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/40 ml-2">
                      ACTIVE
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription>
                  Unlock advanced commissioner tools for this league with a one-time payment.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                {!premium ? (
                  <div className="text-sm text-[#A1A1AA]">Loading premium status…</div>
                ) : (
                  <>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {(premium.features || []).map((f) => {
                        const unlocked = (premium.unlocked_features || []).includes(f.id);
                        return (
                          <div
                            key={f.id}
                            data-testid={`premium-feature-${f.id}`}
                            className={cn(
                              "p-3 rounded-lg border flex items-start gap-3",
                              unlocked
                                ? "border-emerald-500/40 bg-emerald-500/5"
                                : "border-white/10 bg-white/5"
                            )}
                          >
                            <CheckCircle2
                              size={18}
                              className={unlocked ? "text-emerald-400 mt-0.5" : "text-[#52525B] mt-0.5"}
                            />
                            <div>
                              <div className="text-white text-sm font-semibold">{f.name}</div>
                              <div className="text-[#A1A1AA] text-xs">{f.description}</div>
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {premium.premium ? (
                      <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-300">
                        Premium active for <strong>{selectedLeague?.name}</strong>. All features
                        unlocked.
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-4 flex-wrap pt-2 border-t border-white/5">
                        <div>
                          <div className="text-2xl font-bold text-white">
                            ${premium.price_usd?.toFixed(2)}
                            <span className="text-[#A1A1AA] text-sm font-normal"> one-time</span>
                          </div>
                          <div className="text-[#A1A1AA] text-xs">
                            Unlocks every premium feature for {selectedLeague?.name}
                          </div>
                        </div>
                        <Button
                          data-testid="upgrade-premium-btn"
                          onClick={handleUpgradePremium}
                          disabled={upgrading}
                          className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]"
                        >
                          {upgrading ? (
                            <><Loader2 size={16} className="mr-2 animate-spin" /> Redirecting…</>
                          ) : (
                            <>Upgrade to Premium</>
                          )}
                        </Button>
                      </div>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
}
