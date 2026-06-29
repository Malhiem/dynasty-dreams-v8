// @ts-nocheck
/* Iter 231ai — Live prospect-pool wiring.
   Was: 8 hardcoded mock prospects.
   Now: fetches the 1,368-prospect pool from /api/prospects with year +
   position filters, name search, and a per-user Watchlist that hits
   /api/prospects/watchlist add/remove endpoints.
*/
import { useEffect, useState, useMemo, useCallback } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, Star, StarOff, Loader2, MapPin, Ruler, Weight, Calendar } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

interface Prospect {
  id: string;
  name: string;
  position: string;
  team: string;
  team_name: string;
  amateur_league: string;
  draft_year: number | null;
  draft_round: number | null;
  draft_pick_overall: number | null;
  drafted_by_team: string;
  drafted_by_team_name: string;
  country_code: string;
  height_inches: number | null;
  weight_lbs: number | null;
  age: number | null;
  season: string | null;
  points: number;
  games_played: number;
  in_watchlist: boolean;
}

interface FilterOpts {
  years: number[];
  positions: string[];
  drafted_by_teams: string[];
}

const ALL = "_all_"; // Select uses non-empty sentinel.

const Prospects = () => {
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [watchlist, setWatchlist] = useState<Prospect[]>([]);
  const [filters, setFilters] = useState<FilterOpts>({ years: [], positions: [], drafted_by_teams: [] });
  const [year, setYear] = useState<string>(ALL);
  const [position, setPosition] = useState<string>(ALL);
  const [draftedBy, setDraftedBy] = useState<string>(ALL);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [watchBusy, setWatchBusy] = useState<Record<string, boolean>>({});

  const loadFilters = useCallback(async () => {
    try {
      const { data } = await api.get<FilterOpts>("/prospects/filters");
      setFilters(data);
      // Default to most-recent year so the first paint is sensible.
      if (data.years.length && year === ALL) {
        setYear(String(data.years[0]));
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Couldn't load prospect filters");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadProspects = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { limit: "200" };
      if (year !== ALL) params.year = year;
      if (position !== ALL) params.position = position;
      if (draftedBy !== ALL) params.drafted_by = draftedBy;
      if (search.trim()) params.search = search.trim();
      const { data } = await api.get<{ prospects: Prospect[] }>("/prospects", { params });
      setProspects(data.prospects || []);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Couldn't load prospects");
    } finally {
      setLoading(false);
    }
  }, [year, position, draftedBy, search]);

  const loadWatchlist = useCallback(async () => {
    try {
      const { data } = await api.get<{ prospects: Prospect[] }>("/prospects/watchlist");
      setWatchlist(data.prospects || []);
    } catch (e: any) {
      // Soft fail — empty watchlist isn't fatal.
      console.warn("Watchlist load failed", e?.message);
    }
  }, []);

  useEffect(() => {
    loadFilters();
    loadWatchlist();
  }, [loadFilters, loadWatchlist]);

  useEffect(() => {
    // Debounce search by 250ms so we don't fire a request on every keystroke.
    const t = setTimeout(() => { loadProspects(); }, 250);
    return () => clearTimeout(t);
  }, [loadProspects]);

  const toggleWatch = async (p: Prospect) => {
    setWatchBusy((s) => ({ ...s, [p.id]: true }));
    try {
      if (p.in_watchlist) {
        await api.delete(`/prospects/watchlist/${p.id}`);
        toast.success(`Removed ${p.name} from watchlist`);
      } else {
        await api.post(`/prospects/watchlist/${p.id}`);
        toast.success(`Added ${p.name} to watchlist`);
      }
      // Reflect the new state in both lists without a full reload.
      setProspects((rows) => rows.map((r) => r.id === p.id ? { ...r, in_watchlist: !r.in_watchlist } : r));
      await loadWatchlist();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Couldn't update watchlist");
    } finally {
      setWatchBusy((s) => ({ ...s, [p.id]: false }));
    }
  };

  const watchlistIds = useMemo(() => new Set(watchlist.map((p) => p.id)), [watchlist]);

  return (
    <AppLayout>
      <div className="container py-8 space-y-6" data-testid="prospects-page">
        <div>
          <h1 className="text-2xl font-bold">Prospect Rankings</h1>
          <p className="text-muted-foreground">
            Last 6 NHL draft classes — {filters.years.length > 0 && (
              <>
                <span className="text-accent">{filters.years[filters.years.length - 1]}</span> through{" "}
                <span className="text-accent">{filters.years[0]}</span>
              </>
            )}
          </p>
        </div>

        {/* ─── Filter bar ─── */}
        <Card className="bg-card border-border">
          <CardContent className="p-4 flex flex-col md:flex-row md:items-center gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name…"
                className="pl-9"
                data-testid="prospects-search-input"
              />
            </div>
            <Select value={year} onValueChange={setYear}>
              <SelectTrigger className="w-full md:w-40" data-testid="prospects-year-select">
                <SelectValue placeholder="Draft year" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All years</SelectItem>
                {filters.years.map((y) => (
                  <SelectItem key={y} value={String(y)}>{y}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={position} onValueChange={setPosition}>
              <SelectTrigger className="w-full md:w-32" data-testid="prospects-position-select">
                <SelectValue placeholder="Position" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All positions</SelectItem>
                {filters.positions.map((p) => (
                  <SelectItem key={p} value={p}>{p}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={draftedBy} onValueChange={setDraftedBy}>
              <SelectTrigger className="w-full md:w-36" data-testid="prospects-team-select">
                <SelectValue placeholder="Drafted by" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All teams</SelectItem>
                {filters.drafted_by_teams.map((t) => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </CardContent>
        </Card>

        <Tabs defaultValue="rankings" className="space-y-4">
          <TabsList className="bg-secondary">
            <TabsTrigger value="rankings" data-testid="prospects-tab-all">Top Prospects ({prospects.length})</TabsTrigger>
            <TabsTrigger value="watchlist" data-testid="prospects-tab-watchlist">
              <Star className="h-3.5 w-3.5 mr-1" />
              Watchlist ({watchlist.length})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="rankings">
            {loading ? (
              <ProspectListSkeleton />
            ) : prospects.length === 0 ? (
              <EmptyState>No prospects match your filters.</EmptyState>
            ) : (
              <div className="grid gap-3" data-testid="prospects-rankings-list">
                {prospects.map((p, i) => (
                  <ProspectCard
                    key={p.id}
                    prospect={p}
                    rank={i + 1}
                    busy={!!watchBusy[p.id]}
                    onToggleWatch={() => toggleWatch(p)}
                  />
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="watchlist">
            {watchlist.length === 0 ? (
              <EmptyState>
                You haven&apos;t added any prospects yet. Click <Star className="inline h-3.5 w-3.5 mx-1" />
                on a prospect card to watch them.
              </EmptyState>
            ) : (
              <div className="grid gap-3" data-testid="prospects-watchlist-list">
                {watchlist.map((p, i) => (
                  <ProspectCard
                    key={p.id}
                    prospect={{ ...p, in_watchlist: true }}
                    rank={i + 1}
                    busy={!!watchBusy[p.id]}
                    onToggleWatch={() => toggleWatch(p)}
                  />
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
};

const ProspectListSkeleton = () => (
  <div className="grid gap-3">
    {Array.from({ length: 6 }).map((_, i) => (
      <Skeleton key={i} className="h-28 w-full" />
    ))}
  </div>
);

const EmptyState = ({ children }: { children: React.ReactNode }) => (
  <Card className="bg-card border-border">
    <CardContent className="py-12 text-center text-muted-foreground text-sm">
      {children}
    </CardContent>
  </Card>
);

const POSITION_COLOR: Record<string, string> = {
  C: "bg-violet-500/15 text-violet-300 border-violet-500/30",
  LW: "bg-blue-500/15 text-blue-300 border-blue-500/30",
  RW: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  D: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  G: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  F: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
};

const ProspectCard = ({
  prospect: p,
  rank,
  busy,
  onToggleWatch,
}: {
  prospect: Prospect;
  rank: number;
  busy: boolean;
  onToggleWatch: () => void;
}) => {
  const posColor = POSITION_COLOR[p.position] || POSITION_COLOR.F;
  const heightFmt = p.height_inches
    ? `${Math.floor(p.height_inches / 12)}'${p.height_inches % 12}"`
    : null;
  const teamLogo = p.drafted_by_team
    ? `https://assets.nhle.com/logos/nhl/svg/${p.drafted_by_team}_dark.svg`
    : null;
  return (
    <Card
      className="bg-card border-border hover:border-primary/30 transition-colors"
      data-testid={`prospect-card-${p.id}`}
    >
      <CardContent className="p-4">
        <div className="flex items-start gap-4">
          {/* Rank badge */}
          <div
            className={`h-10 w-10 shrink-0 rounded-lg flex items-center justify-center font-display text-lg ${
              rank <= 3 ? "bg-accent/20 text-accent" : "bg-secondary text-muted-foreground"
            }`}
          >
            {rank}
          </div>

          {/* Drafting team logo (live NHL CDN). Falls back to a coloured tile if missing. */}
          <div className="h-14 w-14 shrink-0 rounded-lg bg-gradient-to-br from-secondary to-muted flex items-center justify-center overflow-hidden">
            {teamLogo ? (
              <img
                src={teamLogo}
                alt={p.drafted_by_team}
                className="h-12 w-12 object-contain"
                onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
              />
            ) : (
              <span className="text-xs font-bold">{p.position}</span>
            )}
          </div>

          {/* Main details */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <h3 className="font-semibold text-base truncate">{p.name}</h3>
              <Badge variant="outline" className={`${posColor} text-[10px]`}>{p.position}</Badge>
              {p.draft_year && (
                <Badge variant="outline" className="border-sky-500/30 text-sky-300 bg-sky-500/10 text-[10px]">
                  Draft {p.draft_year} • Rd {p.draft_round}, #{p.draft_pick_overall}
                </Badge>
              )}
            </div>

            <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
              {p.drafted_by_team_name && (
                <span className="flex items-center gap-1">
                  <span className="font-medium text-foreground">{p.drafted_by_team}</span>
                  <span>—</span>
                  <span>{p.drafted_by_team_name}</span>
                </span>
              )}
              {p.team_name && (
                <span className="truncate">
                  Amateur: <span className="text-foreground">{p.team_name}</span>
                </span>
              )}
            </div>

            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground mt-2">
              {p.country_code && (
                <span className="flex items-center gap-1">
                  <MapPin className="h-3 w-3" />
                  {p.country_code}
                </span>
              )}
              {heightFmt && (
                <span className="flex items-center gap-1">
                  <Ruler className="h-3 w-3" />
                  {heightFmt}
                </span>
              )}
              {p.weight_lbs && (
                <span className="flex items-center gap-1">
                  <Weight className="h-3 w-3" />
                  {p.weight_lbs} lbs
                </span>
              )}
              {p.season && (
                <span className="flex items-center gap-1">
                  <Calendar className="h-3 w-3" />
                  {p.season}
                </span>
              )}
            </div>
          </div>

          {/* Watch button */}
          <Button
            size="sm"
            variant={p.in_watchlist ? "default" : "outline"}
            disabled={busy}
            onClick={onToggleWatch}
            className={p.in_watchlist ? "bg-amber-500 hover:bg-amber-600 text-black gap-1.5" : "gap-1.5"}
            data-testid={`prospect-watch-btn-${p.id}`}
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : (
              p.in_watchlist
                ? <Star className="h-3.5 w-3.5 fill-current" />
                : <StarOff className="h-3.5 w-3.5" />
            )}
            {p.in_watchlist ? "Watching" : "Watch"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

export default Prospects;
