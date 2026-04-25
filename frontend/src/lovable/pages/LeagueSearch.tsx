// @ts-nocheck
import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Search, Users, Trophy, DollarSign, Lock, Loader2, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";

const FORMAT_LABEL = {
  dynasty: "Dynasty",
  keeper: "Keeper",
  best_ball: "Best Ball",
  redraft: "Redraft",
};

export default function LeagueSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [format, setFormat] = useState("all");
  const [leagues, setLeagues] = useState([]);
  const [loading, setLoading] = useState(false);
  const [joinTarget, setJoinTarget] = useState(null);
  const [teamName, setTeamName] = useState("");
  const [joining, setJoining] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.set("q", q.trim());
      if (format && format !== "all") params.set("format", format);
      const { data } = await api.get(`/public-leagues?${params.toString()}`);
      setLeagues(data?.leagues || []);
    } catch (e) {
      toast.error("Failed to load public leagues", { description: e?.response?.data?.detail || e?.message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const onSubmit = async (e) => { e.preventDefault(); await load(); };

  const submitJoin = async () => {
    if (!joinTarget?.id || !teamName.trim()) return;
    setJoining(true);
    try {
      const { data } = await api.post(`/leagues/${joinTarget.id}/join-public`, { team_name: teamName.trim() });
      toast.success(`Joined ${data.league_name}!`, { description: `Team "${teamName.trim()}" created.` });
      setJoinTarget(null);
      setTeamName("");
      await load();
      navigate(`/?league_id=${data.league_id}`);
    } catch (e) {
      toast.error("Failed to join", { description: e?.response?.data?.detail || e?.message });
    } finally {
      setJoining(false);
    }
  };

  return (
    <AppLayout>
      <div className="container py-6 space-y-6" data-testid="league-search-page">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-3xl font-black tracking-tight flex items-center gap-2">
              <Search className="h-7 w-7 text-primary" />
              LEAGUE SEARCH
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Browse public leagues and claim a team. Private leagues are hidden — you'll need an invite link or code to join those.
            </p>
          </div>
        </div>

        <Card className="bg-card border-border">
          <CardContent className="pt-6">
            <form onSubmit={onSubmit} className="flex flex-col sm:flex-row gap-3 items-end">
              <div className="flex-1 space-y-1.5">
                <Label className="text-xs">Search by name</Label>
                <Input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="e.g. Ice Kings, Frozen Dynasty…"
                  data-testid="league-search-query"
                />
              </div>
              <div className="w-full sm:w-48 space-y-1.5">
                <Label className="text-xs">Format</Label>
                <Select value={format} onValueChange={setFormat}>
                  <SelectTrigger data-testid="league-search-format"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All formats</SelectItem>
                    <SelectItem value="dynasty">Dynasty</SelectItem>
                    <SelectItem value="keeper">Keeper</SelectItem>
                    <SelectItem value="best_ball">Best Ball</SelectItem>
                    <SelectItem value="redraft">Redraft</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button type="submit" disabled={loading} data-testid="league-search-submit">
                {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Search className="h-4 w-4 mr-2" />}
                Search
              </Button>
            </form>
          </CardContent>
        </Card>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : leagues.length === 0 ? (
          <Card className="bg-card border-border">
            <CardContent className="pt-12 pb-12 text-center">
              <Search className="h-10 w-10 mx-auto text-muted-foreground mb-3 opacity-40" />
              <p className="text-sm text-muted-foreground">No public leagues found.</p>
              <p className="text-xs text-muted-foreground mt-1">
                Try clearing the filters, or ask a commissioner for a private invite link.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {leagues.map((l) => (
              <Card key={l.id} className="bg-card border-border hover:border-primary/40 transition-colors" data-testid={`league-search-card-${l.id}`}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base leading-tight">{l.name}</CardTitle>
                    {l.already_member ? (
                      <Badge variant="outline" className="text-[10px] border-emerald-500/40 text-emerald-400 shrink-0">
                        <CheckCircle2 className="h-2.5 w-2.5 mr-1" /> Member
                      </Badge>
                    ) : l.is_full ? (
                      <Badge variant="outline" className="text-[10px] border-destructive/40 text-destructive shrink-0">
                        FULL
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-[10px] border-primary/40 text-primary shrink-0">
                        {l.open_spots} OPEN
                      </Badge>
                    )}
                  </div>
                  <CardDescription className="text-xs flex items-center gap-2 flex-wrap">
                    <span>{(FORMAT_LABEL[l.format] || l.format || "").toUpperCase()}</span>
                    <span>·</span>
                    <span className="uppercase">{(l.scoring_format || "").replace(/_/g, " ")}</span>
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1"><Users className="h-3 w-3" />{l.current_teams}/{l.max_teams}</span>
                    {l.salary_cap_enabled && (
                      <span className="flex items-center gap-1"><DollarSign className="h-3 w-3" />${(l.salary_cap || 0)}M cap</span>
                    )}
                    {l.keepers_allowed > 0 && (
                      <span className="flex items-center gap-1"><Trophy className="h-3 w-3" />{l.keepers_allowed} keepers</span>
                    )}
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    Commissioner: <span className="text-foreground font-medium">{l.commissioner_name || "—"}</span>
                    {l.entry_fee ? <span className="ml-2">· ${l.entry_fee} buy-in</span> : null}
                  </div>
                  <Button
                    className="w-full"
                    size="sm"
                    disabled={l.is_full || l.already_member}
                    onClick={() => { setJoinTarget(l); setTeamName(""); }}
                    data-testid={`league-search-join-${l.id}`}
                  >
                    {l.already_member ? "Already a member" : l.is_full ? "League full" : "Join League"}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        <Card className="bg-card/50 border-border/50" data-testid="league-search-private-hint">
          <CardContent className="pt-5 pb-5 flex items-start gap-3">
            <Lock className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
            <div className="text-xs text-muted-foreground leading-relaxed">
              <strong className="text-foreground">Looking for a private league?</strong> Private leagues never appear here.
              Ask the commissioner for an invite link or code, then{" "}
              <a href="/" className="text-primary hover:underline">join via the dashboard</a>.
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Join Dialog */}
      <Dialog open={!!joinTarget} onOpenChange={(open) => { if (!open) setJoinTarget(null); }}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle>Join {joinTarget?.name}</DialogTitle>
            <DialogDescription>Pick a team name. You can rename it later.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label className="text-xs">Team Name</Label>
            <Input
              autoFocus
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
              placeholder="e.g. Frozen Five, Ice Breakers…"
              maxLength={80}
              data-testid="league-search-team-name"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setJoinTarget(null)}>Cancel</Button>
            <Button
              onClick={submitJoin}
              disabled={joining || !teamName.trim()}
              data-testid="league-search-confirm-join"
            >
              {joining ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Confirm Join
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
