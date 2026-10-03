// @ts-nocheck
import { useEffect, useState } from "react";
import { Trophy, Medal, Star, Loader2, Save, Gift, Sparkles, ClipboardList } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";

type TeamAwards = {
  championship_won_at?: string | null;
  division_winner_at?: string | null;
  playoffs_reached_at?: string | null;
  consolation_won_at?: string | null;
};

export function SeasonAwardsTab() {
  const { league, leagueTeams } = useActiveLeague();
  const [awards, setAwards] = useState<Record<string, TeamAwards>>({});
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);

  useEffect(() => {
    const map: Record<string, TeamAwards> = {};
    (leagueTeams || []).forEach((t: any) => {
      map[t.id] = {
        championship_won_at: t.championship_won_at || null,
        division_winner_at: t.division_winner_at || null,
        playoffs_reached_at: t.playoffs_reached_at || null,
        consolation_won_at: t.consolation_won_at || null,
      };
    });
    setAwards(map);
  }, [leagueTeams]);

  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    setLoading(true);
    api.get(`/teams?league_id=${league.id}`).then(({ data }) => {
      if (cancelled) return;
      const map: Record<string, TeamAwards> = {};
      (data || []).forEach((t: any) => {
        map[t.id] = {
          championship_won_at: t.championship_won_at || null,
          division_winner_at: t.division_winner_at || null,
          playoffs_reached_at: t.playoffs_reached_at || null,
          consolation_won_at: t.consolation_won_at || null,
        };
      });
      setAwards(map);
    }).catch(() => {}).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [league?.id]);

  const toggle = async (teamId: string, field: keyof TeamAwards, value: boolean) => {
    if (!league?.id) return;
    setSavingId(teamId + ":" + field);
    const body: any = {};
    if (field === "championship_won_at") body.championship_won = value;
    if (field === "division_winner_at") body.division_winner = value;
    if (field === "conference_winner_at") body.conference_winner = value;
    if (field === "playoffs_reached_at") body.playoffs_reached = value;
    if (field === "consolation_won_at") body.consolation_won = value;
    try {
      const { data } = await api.put(`/leagues/${league.id}/teams/${teamId}/awards`, body);
      setAwards((prev) => ({
        ...prev,
        [teamId]: {
          championship_won_at: data.championship_won_at,
          division_winner_at: data.division_winner_at,
          conference_winner_at: data.conference_winner_at,
          playoffs_reached_at: data.playoffs_reached_at,
          consolation_won_at: data.consolation_won_at,
        },
      }));
      let msg = value ? `Awarded ${field.replace("_at", "").replace(/_/g, " ")}` : `Cleared ${field.replace("_at", "").replace(/_/g, " ")}`;
      if (data.unlocked_trades > 0) msg += ` · ${data.unlocked_trades} conditional trade(s) unlocked`;
      toast.success(msg);
    } catch (e: any) {
      toast.error("Failed to update", { description: e?.response?.data?.detail || e?.message });
    } finally {
      setSavingId(null);
    }
  };

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Trophy className="h-5 w-5 text-primary" />
          Season Awards
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Mark teams with season-end awards (auto-set when playoff finals are simulated) and configure
          the consolation prize. Flipping these triggers re-evaluation of any pending conditional trades.
        </p>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="awards" className="w-full">
          <TabsList className="grid w-full sm:w-auto grid-cols-3" data-testid="season-awards-tabs">
            <TabsTrigger value="awards" data-testid="season-awards-tab-team">
              <Trophy className="h-3.5 w-3.5 mr-1.5" /> Team Awards
            </TabsTrigger>
            <TabsTrigger value="consolation" data-testid="season-awards-tab-consolation">
              <Gift className="h-3.5 w-3.5 mr-1.5" /> Consolation Prize
            </TabsTrigger>
            <TabsTrigger value="rewards" data-testid="season-awards-tab-rewards">
              <ClipboardList className="h-3.5 w-3.5 mr-1.5" /> Awarded Prizes
            </TabsTrigger>
          </TabsList>

          <TabsContent value="awards" className="mt-4 space-y-3">
            {loading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading teams…
              </div>
            )}
            {!loading && (leagueTeams || []).map((t: any) => {
              const a = awards[t.id] || {};
              return (
                <div
                  key={t.id}
                  data-testid={`season-awards-row-${t.id}`}
                  className="flex items-center gap-3 p-3 rounded-lg border border-border bg-secondary/30 hover:bg-secondary/50 transition-colors"
                >
                  <div className="h-8 w-8 rounded bg-primary/10 flex items-center justify-center text-xs font-bold text-primary shrink-0">
                    {t.logo_abbr || (t.name || "").slice(0, 3).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-sm truncate">{t.name}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {t.owner_name} · {t.wins || 0}-{t.losses || 0}-{t.ties || 0}
                      {a.consolation_won_at && (
                        <span className="ml-2 text-amber-400">· 🎖 Consolation winner</span>
                      )}
                    </p>
                  </div>

                  <AwardToggle
                    label="Playoffs"
                    icon={<Star className="h-3.5 w-3.5" />}
                    active={!!a.playoffs_reached_at}
                    onChange={(v) => toggle(t.id, "playoffs_reached_at", v)}
                    saving={savingId === `${t.id}:playoffs_reached_at`}
                    testId={`season-awards-playoffs-${t.id}`}
                  />
                  <AwardToggle
                    label="Division"
                    icon={<Medal className="h-3.5 w-3.5" />}
                    active={!!a.division_winner_at}
                    onChange={(v) => toggle(t.id, "division_winner_at", v)}
                    saving={savingId === `${t.id}:division_winner_at`}
                    testId={`season-awards-division-${t.id}`}
                  />
                  <AwardToggle
                    label="Conference"
                    icon={<Medal className="h-3.5 w-3.5" />}
                    active={!!a.conference_winner_at}
                    onChange={(v) => toggle(t.id, "conference_winner_at", v)}
                    saving={savingId === `${t.id}:conference_winner_at`}
                    testId={`season-awards-conference-${t.id}`}
                  />
                  <AwardToggle
                    label="Consolation"
                    icon={<Gift className="h-3.5 w-3.5" />}
                    active={!!a.consolation_won_at}
                    onChange={(v) => toggle(t.id, "consolation_won_at", v)}
                    saving={savingId === `${t.id}:consolation_won_at`}
                    testId={`season-awards-consolation-${t.id}`}
                  />
                  <AwardToggle
                    label="Champion"
                    icon={<Trophy className="h-3.5 w-3.5" />}
                    active={!!a.championship_won_at}
                    onChange={(v) => toggle(t.id, "championship_won_at", v)}
                    saving={savingId === `${t.id}:championship_won_at`}
                    testId={`season-awards-champion-${t.id}`}
                    highlight
                  />
                </div>
              );
            })}
            {!loading && (leagueTeams || []).length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-6">
                No teams in this league yet.
              </p>
            )}
          </TabsContent>

          <TabsContent value="consolation" className="mt-4">
            <ConsolationPrizeEditor leagueId={league?.id} />
          </TabsContent>

          <TabsContent value="rewards" className="mt-4">
            <AwardedPrizesList leagueId={league?.id} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function AwardToggle({ label, icon, active, onChange, saving, testId, highlight }: any) {
  return (
    <div className="flex flex-col items-center gap-1 min-w-[76px]">
      <Badge
        variant={active ? "default" : "outline"}
        className={`text-[10px] flex items-center gap-1 ${
          active
            ? highlight
              ? "bg-amber-500/20 text-amber-400 border-amber-500/50"
              : "bg-primary/20 text-primary border-primary/40"
            : "bg-transparent text-muted-foreground"
        }`}
      >
        {icon} {label}
      </Badge>
      <Switch
        checked={active}
        onCheckedChange={onChange}
        disabled={saving}
        className="scale-75"
        data-testid={testId}
      />
    </div>
  );
}

// ─── Consolation Prize Editor ──────────────────────────────────────
function ConsolationPrizeEditor({ leagueId }: { leagueId?: string }) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [prize, setPrize] = useState<any>({
    type: "draft_lottery_boost",
    description: "",
    lottery_boost_spots: 3,
    fallback_pick_round: 3,
    fallback_pick_year: new Date().getFullYear() + 1,
    custom_details: "",
  });

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    setLoading(true);
    api.get(`/leagues/${leagueId}/consolation-prize`)
      .then(({ data }) => {
        if (cancelled) return;
        if (data?.consolation_prize) {
          setPrize((p: any) => ({ ...p, ...data.consolation_prize }));
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [leagueId]);

  const save = async () => {
    if (!leagueId) return;
    setSaving(true);
    try {
      await api.put(`/leagues/${leagueId}/consolation-prize`, { prize });
      toast.success("Consolation prize saved", {
        description: "Will be auto-awarded when the consolation final is simulated.",
      });
    } catch (e: any) {
      toast.error("Failed to save", { description: e?.response?.data?.detail || e?.message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2 p-3 rounded-lg border border-accent/30 bg-accent/5">
        <Sparkles className="h-4 w-4 text-accent mt-0.5 shrink-0" />
        <div className="text-xs text-muted-foreground leading-relaxed">
          Configure the reward for the <strong>Consolation Bracket winner</strong>. When the consolation
          final matchup is simulated (<code>is_final: true</code>, <code>bracket: "consolation"</code>),
          this prize is automatically logged and — for lottery boosts / compensation picks — directly
          applied to the winning team's upcoming draft picks. Custom prizes are recorded for manual
          fulfillment.
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading prize…
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Prize Type</Label>
            <Select value={prize.type} onValueChange={(v) => setPrize({ ...prize, type: v })}>
              <SelectTrigger data-testid="consolation-prize-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="draft_lottery_boost">Draft Lottery Boost</SelectItem>
                <SelectItem value="compensation_pick">Compensation Pick</SelectItem>
                <SelectItem value="custom">Custom Prize</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Description (shown in feed/audit)</Label>
            <Input
              value={prize.description || ""}
              onChange={(e) => setPrize({ ...prize, description: e.target.value })}
              placeholder="e.g. Consolation champion moves up 3 lottery spots"
              data-testid="consolation-prize-description"
            />
          </div>

          {prize.type === "draft_lottery_boost" && (
            <>
              <div className="space-y-1.5">
                <Label className="text-xs">Lottery Boost Spots</Label>
                <Input
                  type="number"
                  min={1}
                  max={15}
                  value={prize.lottery_boost_spots || 0}
                  onChange={(e) => setPrize({ ...prize, lottery_boost_spots: parseInt(e.target.value || "0", 10) })}
                  data-testid="consolation-boost-spots"
                />
                <p className="text-[10px] text-muted-foreground">
                  Winner's next-year R1 pick advances by this many slots.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Fallback Pick Round</Label>
                  <Input
                    type="number"
                    min={1} max={7}
                    value={prize.fallback_pick_round || 3}
                    onChange={(e) => setPrize({ ...prize, fallback_pick_round: parseInt(e.target.value || "3", 10) })}
                    data-testid="consolation-fallback-round"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Fallback Year</Label>
                  <Input
                    type="number"
                    min={new Date().getFullYear()}
                    value={prize.fallback_pick_year || new Date().getFullYear() + 1}
                    onChange={(e) => setPrize({ ...prize, fallback_pick_year: parseInt(e.target.value, 10) })}
                    data-testid="consolation-fallback-year"
                  />
                </div>
                <p className="col-span-2 text-[10px] text-muted-foreground -mt-1">
                  Used when the winner's next R1 pick has already been traded away.
                </p>
              </div>
            </>
          )}

          {prize.type === "compensation_pick" && (
            <div className="grid grid-cols-2 gap-2 md:col-span-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Pick Round</Label>
                <Input
                  type="number" min={1} max={7}
                  value={prize.fallback_pick_round || 3}
                  onChange={(e) => setPrize({ ...prize, fallback_pick_round: parseInt(e.target.value || "3", 10) })}
                  data-testid="consolation-comp-round"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Pick Year</Label>
                <Input
                  type="number"
                  min={new Date().getFullYear()}
                  value={prize.fallback_pick_year || new Date().getFullYear() + 1}
                  onChange={(e) => setPrize({ ...prize, fallback_pick_year: parseInt(e.target.value, 10) })}
                  data-testid="consolation-comp-year"
                />
              </div>
            </div>
          )}

          {prize.type === "custom" && (
            <div className="space-y-1.5 md:col-span-2">
              <Label className="text-xs">Custom Prize Details</Label>
              <Textarea
                rows={3}
                value={prize.custom_details || ""}
                onChange={(e) => setPrize({ ...prize, custom_details: e.target.value })}
                placeholder="e.g. $25 bonus + priority waiver for first 2 weeks of next season"
                data-testid="consolation-custom-details"
              />
            </div>
          )}
        </div>
      )}

      <div className="flex justify-end">
        <Button onClick={save} disabled={saving || !leagueId} className="gap-2" data-testid="consolation-prize-save">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Save Prize
        </Button>
      </div>
    </div>
  );
}

// ─── Awarded Prizes List ──────────────────────────────────────────
function AwardedPrizesList({ leagueId }: { leagueId?: string }) {
  const [rewards, setRewards] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    setLoading(true);
    api.get(`/leagues/${leagueId}/team-rewards`)
      .then(({ data }) => { if (!cancelled) setRewards(data?.rewards || []); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [leagueId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground py-6 justify-center">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading reward history…
      </div>
    );
  }
  if (rewards.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-8">
        No prizes awarded yet. They'll appear here once a playoff final is simulated.
      </p>
    );
  }
  return (
    <div className="space-y-2" data-testid="awarded-prizes-list">
      {rewards.map((r: any) => (
        <div
          key={r._id}
          className="flex items-start gap-3 p-3 rounded-lg border border-border bg-secondary/30"
          data-testid={`awarded-prize-${r._id}`}
        >
          <Gift className="h-4 w-4 text-amber-400 mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold">
              {r.team_name || "Team"} <span className="text-muted-foreground font-normal">· {r.source?.replace(/_/g, " ")}</span>
            </p>
            <p className="text-xs text-muted-foreground">
              {r.prize?.type?.replace(/_/g, " ")} {r.prize?.lottery_boost_spots ? `(+${r.prize.lottery_boost_spots} spots)` : ""}
              {r.prize?.description ? ` — ${r.prize.description}` : ""}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              {new Date(r.awarded_at).toLocaleString()} · {r.status?.replace(/_/g, " ")}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

export default SeasonAwardsTab;
