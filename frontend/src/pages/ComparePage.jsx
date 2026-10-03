import { useEffect, useMemo, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Crown, Lock, Sparkles, ArrowLeftRight, Search, X, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { cn } from "@/lib/utils";

const useDebounced = (value, delay = 300) => {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
};

function PlayerPicker({ slot, value, onPick, disabled }) {
  const [search, setSearch] = useState("");
  const [options, setOptions] = useState([]);
  const [open, setOpen] = useState(false);
  const debounced = useDebounced(search, 300);

  useEffect(() => {
    if (!debounced || debounced.length < 2) { setOptions([]); return; }
    api.get(`/players?search=${encodeURIComponent(debounced)}&limit=8`)
      .then(({ data }) => setOptions(data?.players || []))
      .catch(() => setOptions([]));
  }, [debounced]);

  if (value) {
    return (
      <div
        className="flex items-center justify-between p-4 rounded-xl bg-[#141414] border border-white/10"
        data-testid={`compare-player-${slot}-selected`}
      >
        <div className="flex items-center gap-3">
          <div className="h-12 w-12 rounded-lg bg-[#1A1A1A] border border-white/10 flex items-center justify-center text-sm font-bold text-[#00D2FF]">
            {value.team || "?"}
          </div>
          <div>
            <p className="font-semibold text-white">{value.name}</p>
            <p className="text-xs text-[#A1A1AA]">{value.position} · {value.team}</p>
          </div>
        </div>
        <Button
          variant="ghost" size="icon"
          onClick={() => onPick(null)}
          data-testid={`compare-player-${slot}-clear`}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <div className="relative">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#71717A]" />
        <Input
          value={search}
          disabled={disabled}
          placeholder={`Search ${slot === "a" ? "Player A" : "Player B"}…`}
          onChange={(e) => { setSearch(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          className="pl-9 bg-[#141414] border-white/10 text-white"
          data-testid={`compare-player-${slot}-search`}
        />
      </div>
      {open && options.length > 0 && (
        <div className="absolute z-30 mt-1 w-full bg-[#141414] border border-white/10 rounded-lg shadow-lg max-h-80 overflow-auto">
          {options.map((p) => (
            <button
              key={p._id}
              type="button"
              onClick={() => { onPick(p); setOpen(false); setSearch(""); setOptions([]); }}
              className="w-full text-left p-2.5 hover:bg-[#1A1A1A] flex items-center gap-3 border-b border-white/5"
              data-testid={`compare-player-${slot}-option-${p._id}`}
            >
              <div className="h-9 w-9 rounded bg-[#1A1A1A] border border-white/5 flex items-center justify-center text-xs font-bold text-[#00D2FF]">
                {p.team || "?"}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-white truncate">{p.name}</p>
                <p className="text-xs text-[#A1A1AA]">{p.position} · {p.team}</p>
              </div>
              <span className="text-xs text-[#A1A1AA] tabular-nums">{p.points || 0}P</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const STAT_KEYS_SKATER = [
  ["games_played", "GP"], ["goals", "G"], ["assists", "A"], ["points", "PTS"],
  ["plus_minus", "+/-"], ["shots", "SOG"], ["ppg", "PPG"], ["ppp", "PPP"], ["pim", "PIM"],
];
const STAT_KEYS_GOALIE = [
  ["games_played", "GP"], ["wins", "W"], ["losses", "L"], ["shutouts", "SO"],
  ["saves", "SV"], ["goals_against", "GA"],
];

function StatRow({ label, a, b, kind = "higher_better" }) {
  const aN = a ?? 0; const bN = b ?? 0;
  let aWin = false, bWin = false;
  if (aN !== bN) {
    if (kind === "higher_better") { aWin = aN > bN; bWin = bN > aN; }
    else { aWin = aN < bN; bWin = bN < aN; }
  }
  return (
    <div className="grid grid-cols-[1fr,auto,1fr] items-center gap-4 py-2 border-b border-white/5">
      <div className={cn("text-right tabular-nums text-sm", aWin ? "text-emerald-400 font-semibold" : "text-white")}>
        {typeof aN === "number" ? aN.toLocaleString() : aN}
      </div>
      <div className="text-[10px] uppercase tracking-widest text-[#71717A] text-center px-2">{label}</div>
      <div className={cn("text-left tabular-nums text-sm", bWin ? "text-emerald-400 font-semibold" : "text-white")}>
        {typeof bN === "number" ? bN.toLocaleString() : bN}
      </div>
    </div>
  );
}

function PaywallModal({ remaining, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" data-testid="paywall-modal">
      <Card className="max-w-md w-full mx-4 border-[#FFB020]/30 bg-gradient-to-br from-[#141414] to-[#0A0A0A]">
        <CardHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-lg bg-[#FFB020]/20 flex items-center justify-center">
              <Crown className="h-5 w-5 text-[#FFB020]" />
            </div>
            <div>
              <CardTitle className="text-white">Upgrade to Pro</CardTitle>
              <p className="text-xs text-[#A1A1AA]">Stat Comparator</p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-center py-4 border-y border-white/10">
            <p className="text-5xl font-bold text-[#FFB020]">$2.50<span className="text-base text-[#A1A1AA] font-normal">/mo</span></p>
            <p className="text-xs text-[#A1A1AA] mt-1">Cancel anytime · 7-day free trial</p>
          </div>
          <ul className="space-y-2 text-sm text-white">
            <li className="flex items-start gap-2"><Sparkles className="h-4 w-4 text-[#FFB020] mt-0.5 shrink-0" /> Unlimited Stat Comparator runs</li>
            <li className="flex items-start gap-2"><Sparkles className="h-4 w-4 text-[#FFB020] mt-0.5 shrink-0" /> Compare any two players · any season · your league's scoring</li>
            <li className="flex items-start gap-2"><Sparkles className="h-4 w-4 text-[#FFB020] mt-0.5 shrink-0" /> Priority access to upcoming Pro tools</li>
          </ul>
          <p className="text-[11px] text-[#71717A] text-center">
            You've used all {remaining === 0 ? "3" : remaining} of your free comparisons this month.
          </p>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="outline" onClick={onClose} className="border-white/15 text-white" data-testid="paywall-close">
              Maybe later
            </Button>
            <Button className="bg-[#FFB020] text-black hover:bg-[#FFC957]" data-testid="paywall-upgrade" onClick={() => toast.info("Stripe checkout coming soon — admin can toggle Pro for testing.")}>
              Upgrade
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function ComparePage() {
  const navigate = useNavigate();
  const { league } = useActiveLeague();
  const [searchParams] = useSearchParams();
  const leagueId = searchParams.get("league_id") || league?.id || null;

  const [playerA, setPlayerA] = useState(null);
  const [playerB, setPlayerB] = useState(null);
  const [seasonA, setSeasonA] = useState("current");
  const [seasonB, setSeasonB] = useState("current");
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [proStatus, setProStatus] = useState(null);
  const [paywallOpen, setPaywallOpen] = useState(false);

  // Pre-fill player A if `?a=...` is in the URL (from "Compare" button on profile)
  useEffect(() => {
    const aId = searchParams.get("a");
    if (aId && !playerA) {
      api.get(`/players/${aId}`).then(({ data }) => setPlayerA(data)).catch(() => {});
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch pro status on mount + after each compare
  const refreshProStatus = () => {
    api.get("/users/me/pro-status").then(({ data }) => setProStatus(data)).catch(() => {});
  };
  useEffect(() => { refreshProStatus(); }, []);

  const seasonOptions = useMemo(() => {
    const base = ["current"];
    const yrs = [];
    for (let y = 2014; y <= 2025; y++) yrs.push(`${y}-${String(y + 1).slice(-2)}`);
    return [...base, ...yrs];
  }, []);

  const runCompare = async () => {
    if (!playerA || !playerB) {
      toast.error("Pick both players first");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post("/comparisons/compare", {
        player_a_id: playerA._id,
        player_b_id: playerB._id,
        season_a: seasonA,
        season_b: seasonB,
        league_id: leagueId,
      });
      setResult(data);
      refreshProStatus();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 402 && detail?.code === "upgrade_required") {
        setPaywallOpen(true);
      } else {
        toast.error(typeof detail === "string" ? detail : "Compare failed");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const isGoalie = result?.player_a?.is_goalie || result?.player_b?.is_goalie;
  const statKeys = isGoalie ? STAT_KEYS_GOALIE : STAT_KEYS_SKATER;

  return (
    <AppLayout>
      <div className="space-y-6 max-w-6xl mx-auto" data-testid="compare-page">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <ArrowLeftRight className="h-7 w-7 text-[#00D2FF]" /> Stat Comparator
            </h1>
            <p className="text-sm text-[#A1A1AA] mt-1">
              Pit any two players head-to-head against your league's scoring rules.
            </p>
          </div>
          {proStatus && (
            <div className="text-right" data-testid="pro-status-strip">
              <Badge className="bg-[#00D2FF]/15 text-[#00D2FF] border border-[#00D2FF]/30">
                Unlimited
              </Badge>
            </div>
          )}
        </div>

        {/* Picker */}
        <Card className="border-white/10">
          <CardContent className="p-5">
            <div className="grid grid-cols-1 md:grid-cols-[1fr,auto,1fr] gap-5 items-start">
              <div className="space-y-3">
                <p className="text-[10px] uppercase tracking-widest text-[#71717A]">Player A</p>
                <PlayerPicker slot="a" value={playerA} onPick={setPlayerA} disabled={submitting} />
                {playerA && (
                  <Select value={seasonA} onValueChange={setSeasonA}>
                    <SelectTrigger className="bg-[#141414] border-white/10 text-white" data-testid="compare-season-a">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {seasonOptions.map((s) => (
                        <SelectItem key={s} value={s}>{s === "current" ? "Current Season" : s}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>

              <div className="hidden md:flex items-center justify-center pt-12">
                <div className="h-12 w-12 rounded-full bg-[#00D2FF]/10 border border-[#00D2FF]/30 flex items-center justify-center text-[#00D2FF] font-bold">
                  vs
                </div>
              </div>

              <div className="space-y-3">
                <p className="text-[10px] uppercase tracking-widest text-[#71717A]">Player B</p>
                <PlayerPicker slot="b" value={playerB} onPick={setPlayerB} disabled={submitting} />
                {playerB && (
                  <Select value={seasonB} onValueChange={setSeasonB}>
                    <SelectTrigger className="bg-[#141414] border-white/10 text-white" data-testid="compare-season-b">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {seasonOptions.map((s) => (
                        <SelectItem key={s} value={s}>{s === "current" ? "Current Season" : s}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>

            <div className="mt-5 flex items-center justify-end gap-3">
              <Button
                onClick={runCompare}
                disabled={!playerA || !playerB || submitting}
                className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]"
                data-testid="compare-run-btn"
              >
                {submitting ? "Comparing…" : "Compare"}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Result */}
        {result && (
          <Card className="border-[#00D2FF]/20" data-testid="compare-result">
            <CardHeader className="border-b border-white/10">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center text-center">
                <div>
                  <p className="text-xs text-[#A1A1AA]">{result.player_a.season}</p>
                  <p className="text-xl font-bold text-white truncate">{result.player_a.name}</p>
                  <p className="text-[10px] text-[#71717A]">{result.player_a.position} · {result.player_a.team}</p>
                  <p className="text-3xl font-bold text-[#00D2FF] mt-2 tabular-nums" data-testid="compare-fpts-a">
                    {result.player_a.fantasy_points.toFixed(1)}
                  </p>
                  <p className="text-[10px] text-[#A1A1AA]">FPTS · {result.player_a.fpts_per_game}/GP</p>
                </div>
                <div className="flex items-center justify-center">
                  <div className={cn(
                    "px-4 py-2 rounded-lg font-bold text-lg",
                    result.winner === "tie" ? "bg-zinc-700 text-white" :
                    result.winner === "a" ? "bg-emerald-600/20 text-emerald-400 border border-emerald-500/30" :
                    "bg-rose-600/20 text-rose-400 border border-rose-500/30"
                  )}>
                    {result.winner === "tie" ? <><Minus className="inline h-4 w-4 mr-1" /> Tie</> :
                     result.winner === "a" ? <><TrendingUp className="inline h-4 w-4 mr-1" /> A by {Math.abs(result.fpts_diff).toFixed(1)}</> :
                     <><TrendingDown className="inline h-4 w-4 mr-1" /> B by {Math.abs(result.fpts_diff).toFixed(1)}</>}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-[#A1A1AA]">{result.player_b.season}</p>
                  <p className="text-xl font-bold text-white truncate">{result.player_b.name}</p>
                  <p className="text-[10px] text-[#71717A]">{result.player_b.position} · {result.player_b.team}</p>
                  <p className="text-3xl font-bold text-[#00D2FF] mt-2 tabular-nums" data-testid="compare-fpts-b">
                    {result.player_b.fantasy_points.toFixed(1)}
                  </p>
                  <p className="text-[10px] text-[#A1A1AA]">FPTS · {result.player_b.fpts_per_game}/GP</p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-5">
              <div className="space-y-1">
                {statKeys.map(([key, label]) => {
                  const aVal = result.player_a.stats?.[key] ?? 0;
                  const bVal = result.player_b.stats?.[key] ?? 0;
                  const kind = key === "goals_against" || key === "losses" || key === "pim" ? "lower_better" : "higher_better";
                  return <StatRow key={key} label={label} a={aVal} b={bVal} kind={kind} />;
                })}
                <StatRow label="FPTS" a={result.player_a.fantasy_points} b={result.player_b.fantasy_points} />
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {paywallOpen && (
        <PaywallModal
          remaining={proStatus?.comparisons_remaining ?? 0}
          onClose={() => setPaywallOpen(false)}
        />
      )}
    </AppLayout>
  );
}
