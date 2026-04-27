import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Crown, Lock, Sparkles, Search, X, TrendingUp, TrendingDown, Minus, Scale, Plus, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { cn } from "@/lib/utils";

const useDebounced = (value, delay = 300) => {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), delay); return () => clearTimeout(t); }, [value, delay]);
  return v;
};

function PlayerSearchAdd({ onAdd, sideKey }) {
  const [q, setQ] = useState("");
  const [opts, setOpts] = useState([]);
  const [open, setOpen] = useState(false);
  const debounced = useDebounced(q, 300);
  useEffect(() => {
    if (!debounced || debounced.length < 2) { setOpts([]); return; }
    api.get(`/players?search=${encodeURIComponent(debounced)}&limit=8`)
      .then(({ data }) => setOpts(data?.players || []))
      .catch(() => setOpts([]));
  }, [debounced]);
  return (
    <div className="relative">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#71717A]" />
        <Input
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder="Add player…"
          className="pl-9 bg-[#141414] border-white/10 text-white"
          data-testid={`analyzer-add-player-${sideKey}`}
        />
      </div>
      {open && opts.length > 0 && (
        <div className="absolute z-30 mt-1 w-full bg-[#141414] border border-white/10 rounded-lg shadow-lg max-h-72 overflow-auto">
          {opts.map((p) => (
            <button
              key={p._id}
              onClick={() => { onAdd(p); setQ(""); setOpts([]); setOpen(false); }}
              className="w-full text-left px-3 py-2 hover:bg-[#1A1A1A] flex items-center justify-between"
              data-testid={`analyzer-search-result-${sideKey}-${p._id}`}
            >
              <span className="text-white text-sm">{p.name}</span>
              <span className="text-[10px] text-[#71717A]">{p.position} · {p.team}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function PickAddBlock({ onAdd, sideKey }) {
  const [round, setRound] = useState(1);
  const [year, setYear] = useState(new Date().getFullYear() + 1);
  return (
    <div className="flex items-center gap-2 p-2 rounded-lg bg-[#141414] border border-white/5">
      <Select value={String(year)} onValueChange={(v) => setYear(parseInt(v))}>
        <SelectTrigger className="w-24 bg-[#0A0A0A] border-white/10 h-8 text-xs text-white" data-testid={`analyzer-pick-year-${sideKey}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {[0,1,2,3,4].map(off => {
            const y = new Date().getFullYear() + off;
            return <SelectItem key={y} value={String(y)}>{y}</SelectItem>;
          })}
        </SelectContent>
      </Select>
      <Select value={String(round)} onValueChange={(v) => setRound(parseInt(v))}>
        <SelectTrigger className="w-20 bg-[#0A0A0A] border-white/10 h-8 text-xs text-white" data-testid={`analyzer-pick-round-${sideKey}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Array.from({ length: 12 }, (_, i) => i + 1).map(r => (
            <SelectItem key={r} value={String(r)}>R{r}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        onClick={() => onAdd({ round, year })}
        size="sm"
        variant="outline"
        className="h-8 text-xs border-white/15"
        data-testid={`analyzer-add-pick-btn-${sideKey}`}
      >
        <Plus className="h-3 w-3 mr-1" /> Add Pick
      </Button>
    </div>
  );
}

function SideBuilder({ sideKey, side, setSide }) {
  const removePlayer = (i) => setSide(s => ({ ...s, players: s.players.filter((_, idx) => idx !== i) }));
  const removePick = (i) => setSide(s => ({ ...s, picks: s.picks.filter((_, idx) => idx !== i) }));
  return (
    <Card className="border-white/10" data-testid={`analyzer-side-${sideKey}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-white text-base flex items-center gap-2">
          <span className={cn("h-6 w-6 rounded-full flex items-center justify-center text-xs font-bold",
            sideKey === "a" ? "bg-[#00D2FF]/20 text-[#00D2FF]" : "bg-[#FFB020]/20 text-[#FFB020]")}>
            {sideKey.toUpperCase()}
          </span>
          Side {sideKey.toUpperCase()} sends
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <PlayerSearchAdd
          sideKey={sideKey}
          onAdd={(p) => setSide(s => ({ ...s, players: [...s.players, p] }))}
        />
        {side.players.map((p, i) => (
          <div key={`${p._id}-${i}`} className="flex items-center justify-between p-2 rounded-lg bg-[#141414] border border-white/5"
            data-testid={`analyzer-asset-player-${sideKey}-${p._id}`}>
            <div>
              <p className="text-sm text-white">{p.name}</p>
              <p className="text-[10px] text-[#71717A]">{p.position} · {p.team}</p>
            </div>
            <Button variant="ghost" size="icon" onClick={() => removePlayer(i)}><X className="h-3 w-3" /></Button>
          </div>
        ))}

        <div className="pt-3 border-t border-white/5 space-y-2">
          <p className="text-[10px] uppercase tracking-widest text-[#71717A]">Draft Picks</p>
          <PickAddBlock
            sideKey={sideKey}
            onAdd={(pk) => setSide(s => ({ ...s, picks: [...s.picks, pk] }))}
          />
          {side.picks.map((pk, i) => (
            <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-[#141414] border border-white/5"
              data-testid={`analyzer-asset-pick-${sideKey}-${i}`}>
              <span className="text-sm text-white">{pk.year} R{pk.round}</span>
              <Button variant="ghost" size="icon" onClick={() => removePick(i)}><X className="h-3 w-3" /></Button>
            </div>
          ))}
        </div>

        <div className="pt-3 border-t border-white/5 grid grid-cols-2 gap-2 items-end">
          <div>
            <p className="text-[10px] uppercase tracking-widest text-[#71717A] mb-1">FAAB ($)</p>
            <Input
              type="number"
              min="0"
              value={side.faab}
              onChange={(e) => setSide(s => ({ ...s, faab: Math.max(0, parseInt(e.target.value || 0)) }))}
              className="bg-[#141414] border-white/10 h-8 text-xs text-white"
              data-testid={`analyzer-faab-${sideKey}`}
            />
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-widest text-[#71717A] mb-1">Salary Retained ($)</p>
            <Input
              type="number"
              min="0"
              value={side.retentionAmount}
              onChange={(e) => setSide(s => ({ ...s, retentionAmount: Math.max(0, parseInt(e.target.value || 0)) }))}
              className="bg-[#141414] border-white/10 h-8 text-xs text-white"
              data-testid={`analyzer-retention-${sideKey}`}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function PaywallModal({ onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" data-testid="analyzer-paywall-modal">
      <Card className="max-w-md w-full mx-4 border-[#FFB020]/30 bg-gradient-to-br from-[#141414] to-[#0A0A0A]">
        <CardHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-lg bg-[#FFB020]/20 flex items-center justify-center">
              <Crown className="h-5 w-5 text-[#FFB020]" />
            </div>
            <div>
              <CardTitle className="text-white">Upgrade to Pro</CardTitle>
              <p className="text-xs text-[#A1A1AA]">Trade Value Analyzer + Projections</p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-center py-4 border-y border-white/10">
            <p className="text-5xl font-bold text-[#FFB020]">$2.50<span className="text-base text-[#A1A1AA] font-normal">/mo</span></p>
            <p className="text-xs text-[#A1A1AA] mt-1">Cancel anytime · 7-day free trial · cheaper than Yahoo Fantasy Plus</p>
          </div>
          <ul className="space-y-2 text-sm text-white">
            <li className="flex items-start gap-2"><Sparkles className="h-4 w-4 text-[#FFB020] mt-0.5 shrink-0" /> Unlimited Trade Analyzer runs</li>
            <li className="flex items-start gap-2"><Sparkles className="h-4 w-4 text-[#FFB020] mt-0.5 shrink-0" /> Players + picks + FAAB + salary retention valuation</li>
            <li className="flex items-start gap-2"><Sparkles className="h-4 w-4 text-[#FFB020] mt-0.5 shrink-0" /> Rest-of-season + weekly player projections</li>
            <li className="flex items-start gap-2"><Sparkles className="h-4 w-4 text-[#FFB020] mt-0.5 shrink-0" /> Includes the Stat Comparator (unlimited)</li>
          </ul>
          <p className="text-[11px] text-[#71717A] text-center">
            You've used your 1 free trade analysis this year.
          </p>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="outline" onClick={onClose} className="border-white/15 text-white" data-testid="analyzer-paywall-close">Maybe later</Button>
            <Button className="bg-[#FFB020] text-black hover:bg-[#FFC957]" data-testid="analyzer-paywall-upgrade"
              onClick={() => toast.info("Stripe checkout coming soon — admin can toggle Pro for testing.")}>
              Upgrade
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

const verdictTone = (v) => {
  if (v === "Fair Trade") return "bg-emerald-600/20 text-emerald-400 border-emerald-500/30";
  if (v === "Slightly Lopsided") return "bg-amber-600/20 text-amber-400 border-amber-500/30";
  if (v === "Lopsided") return "bg-orange-600/20 text-orange-400 border-orange-500/30";
  return "bg-rose-600/20 text-rose-400 border-rose-500/30";
};

export default function TradeAnalyzerPage() {
  const { league } = useActiveLeague();
  const [searchParams] = useSearchParams();
  const leagueId = searchParams.get("league_id") || league?.id || null;

  const [sideA, setSideA] = useState({ players: [], picks: [], faab: 0, retentionAmount: 0 });
  const [sideB, setSideB] = useState({ players: [], picks: [], faab: 0, retentionAmount: 0 });
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [paywallOpen, setPaywallOpen] = useState(false);
  const [analyzerStatus, setAnalyzerStatus] = useState(null);

  const refreshStatus = () => {
    api.get("/users/me/analyzer-status").then(({ data }) => setAnalyzerStatus(data)).catch(() => {});
  };
  useEffect(() => { refreshStatus(); }, []);

  const buildSidePayload = (s) => ({
    players: s.players.map(p => p._id),
    picks: s.picks,
    faab: s.faab,
    salary_retentions: s.retentionAmount > 0
      ? [{ player_id: s.players[0]?._id, amount: s.retentionAmount }] : [],
  });

  const isEmptySide = (s) => !s.players.length && !s.picks.length && !s.faab;

  const runAnalyze = async () => {
    if (isEmptySide(sideA) || isEmptySide(sideB)) {
      toast.error("Add at least one asset to each side");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post("/trade-analyzer/analyze", {
        league_id: leagueId,
        side_a: buildSidePayload(sideA),
        side_b: buildSidePayload(sideB),
      });
      setResult(data);
      refreshStatus();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 402 && detail?.code === "upgrade_required") {
        setPaywallOpen(true);
      } else {
        toast.error(typeof detail === "string" ? detail : "Analyze failed");
      }
    } finally { setSubmitting(false); }
  };

  const winner = result?.winner;

  return (
    <AppLayout>
      <div className="space-y-6 max-w-6xl mx-auto" data-testid="trade-analyzer-page">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <Scale className="h-7 w-7 text-[#00D2FF]" /> Trade Value Analyzer
            </h1>
            <p className="text-sm text-[#A1A1AA] mt-1">
              Drag in players, picks, FAAB, and salary retention. We score both sides against your league's rules and call the verdict.
            </p>
          </div>
          {analyzerStatus && (
            <div className="text-right" data-testid="analyzer-status-strip">
              {analyzerStatus.is_pro ? (
                <Badge className="bg-[#FFB020] text-black">
                  <Crown className="h-3 w-3 mr-1" /> Pro · Unlimited
                </Badge>
              ) : (
                <div>
                  <p className="text-xs text-[#A1A1AA]">Free tier</p>
                  <p className="text-sm text-white">
                    <span className="text-[#00D2FF] font-semibold">{analyzerStatus.analyses_remaining}</span> / {analyzerStatus.free_analyses_per_year} analysis left this year
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Builder grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <SideBuilder sideKey="a" side={sideA} setSide={setSideA} />
          <SideBuilder sideKey="b" side={sideB} setSide={setSideB} />
        </div>

        <div className="flex items-center justify-end gap-3">
          {!analyzerStatus?.is_pro && analyzerStatus?.analyses_remaining === 0 && (
            <span className="text-xs text-[#FFB020] flex items-center gap-1.5">
              <Lock className="h-3 w-3" /> Free tier exhausted
            </span>
          )}
          <Button
            onClick={runAnalyze}
            disabled={submitting}
            className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]"
            data-testid="analyzer-run-btn"
          >
            {submitting ? "Analyzing…" : "Analyze Trade"} <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        </div>

        {/* Result */}
        {result && (
          <Card className="border-[#00D2FF]/20" data-testid="analyzer-result">
            <CardHeader className="border-b border-white/10">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center text-center">
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-[#71717A]">Side A receives value</p>
                  <p className="text-3xl font-bold text-[#00D2FF] tabular-nums" data-testid="analyzer-value-a">
                    {result.side_b.total_value.toFixed(1)}
                  </p>
                  <p className="text-[10px] text-[#71717A] mt-1">From B's outgoing assets</p>
                </div>
                <div className="flex flex-col items-center justify-center gap-2">
                  <div className={cn(
                    "px-4 py-2 rounded-lg font-bold text-base border",
                    verdictTone(result.verdict)
                  )} data-testid="analyzer-verdict">
                    {result.verdict}
                  </div>
                  <p className="text-xs text-[#A1A1AA]">
                    Fairness <span className="text-white font-semibold">{result.fairness_pct}%</span>
                  </p>
                  <div className="text-xs flex items-center gap-1">
                    {winner === "tie" ? (
                      <><Minus className="h-3 w-3 text-zinc-400" /> Even</>
                    ) : winner === "a" ? (
                      <><TrendingUp className="h-3 w-3 text-emerald-400" /> A wins by {Math.abs(result.delta).toFixed(1)}</>
                    ) : (
                      <><TrendingDown className="h-3 w-3 text-rose-400" /> B wins by {Math.abs(result.delta).toFixed(1)}</>
                    )}
                  </div>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-[#71717A]">Side B receives value</p>
                  <p className="text-3xl font-bold text-[#FFB020] tabular-nums" data-testid="analyzer-value-b">
                    {result.side_a.total_value.toFixed(1)}
                  </p>
                  <p className="text-[10px] text-[#71717A] mt-1">From A's outgoing assets</p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-5 grid grid-cols-1 md:grid-cols-2 gap-6">
              {[{ key: "a", side: result.side_a, color: "#00D2FF" }, { key: "b", side: result.side_b, color: "#FFB020" }].map(({ key, side, color }) => (
                <div key={key} className="space-y-2" data-testid={`analyzer-breakdown-${key}`}>
                  <p className="text-xs uppercase tracking-widest" style={{ color }}>Side {key.toUpperCase()} outgoing breakdown</p>
                  {side.players.map((p) => (
                    <div key={p.player_id} className="flex justify-between items-center py-1.5 border-b border-white/5">
                      <div>
                        <p className="text-sm text-white">{p.name}</p>
                        <p className="text-[10px] text-[#71717A]">{p.position} · {p.team} · {p.blended_fpg.toFixed(2)} FPG · {p.games_remaining} GR</p>
                      </div>
                      <p className="tabular-nums font-semibold text-white">{p.value.toFixed(1)}</p>
                    </div>
                  ))}
                  {side.picks.map((pk, i) => (
                    <div key={i} className="flex justify-between items-center py-1.5 border-b border-white/5">
                      <p className="text-sm text-white">{pk.label}</p>
                      <p className="tabular-nums font-semibold text-white">{pk.value.toFixed(1)}</p>
                    </div>
                  ))}
                  {side.faab > 0 && (
                    <div className="flex justify-between items-center py-1.5 border-b border-white/5">
                      <p className="text-sm text-white">${side.faab} FAAB</p>
                      <p className="tabular-nums font-semibold text-white">{side.faab_value.toFixed(1)}</p>
                    </div>
                  )}
                  {side.retention_cost > 0 && (
                    <div className="flex justify-between items-center py-1.5 border-b border-white/5">
                      <p className="text-sm text-rose-400">Salary retention cost</p>
                      <p className="tabular-nums font-semibold text-rose-400">−{side.retention_cost.toFixed(1)}</p>
                    </div>
                  )}
                  <div className="flex justify-between items-center pt-2">
                    <p className="text-xs text-[#A1A1AA]">Total</p>
                    <p className="tabular-nums text-lg font-bold" style={{ color }}>{side.total_value.toFixed(1)}</p>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>

      {paywallOpen && <PaywallModal onClose={() => setPaywallOpen(false)} />}
    </AppLayout>
  );
}
