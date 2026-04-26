import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { AppLayout } from "@/components/layout/AppLayout";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Star, Search, ChevronLeft, ChevronRight, ArrowUp, ArrowDown,
  ArrowUpDown, Calendar, FileText,
} from "lucide-react";
import { useActiveLeague } from "@/hooks/use-active-league";
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from "@/components/ui/tooltip";

const VIEWS = [
  { value: "available", label: "All Available Players (default)" },
  { value: "all", label: "All Players" },
  { value: "available_or_own", label: "Available + Own Team" },
  { value: "watchlist_or_own", label: "Watch List + Own Team" },
  { value: "owned", label: "All Owned Players" },
  { value: "waivers", label: "Waiver Wire" },
  { value: "trade_block", label: "Trade Block" },
  { value: "nhl_available", label: "NHL + Available" },
  { value: "nhl_taken", label: "NHL + Taken" },
  { value: "injured_available", label: "Injured + Available" },
  { value: "injured_taken", label: "Injured + Taken" },
  { value: "minors_available", label: "Minors-Eligible + Available" },
  { value: "minors_taken", label: "Minors-Eligible + Taken" },
  { value: "watchlist", label: "Watch List" },
  { value: "exclude_own", label: "All Except Own Team" },
];

const POSITIONS = [
  { value: "all", label: "All Positions" },
  { value: "C", label: "Centers (C)" },
  { value: "LW", label: "Left Wing (LW)" },
  { value: "RW", label: "Right Wing (RW)" },
  { value: "W", label: "Wingers (LW + RW)" },
  { value: "LHD", label: "Left D (LHD)" },
  { value: "RHD", label: "Right D (RHD)" },
  { value: "D", label: "All Defensemen" },
  { value: "SKT", label: "Skaters (non-G)" },
  { value: "G", label: "Goaltenders" },
];

const TIMEFRAMES = [
  { value: "season", label: "Season Totals" },
  { value: "today", label: "Today" },
  { value: "7d", label: "Last 7 Days" },
  { value: "14d", label: "Last 14 Days" },
  { value: "30d", label: "Last 30 Days" },
  { value: "60d", label: "Last 60 Days" },
  { value: "90d", label: "Last 90 Days" },
];

// All league-tracked stat columns (in display order). Each row maps to a sortable
// backend field when supported.
const STAT_COLS = [
  { key: "G",     label: "G",   sort: "goals" },
  { key: "A",     label: "A",   sort: "assists" },
  { key: "PTS",   label: "PTS", sort: "points" },
  { key: "+/-",   label: "+/-", sort: "plus_minus" },
  { key: "SOG",   label: "SOG", sort: null },
  { key: "PPP",   label: "PPP", sort: null },
  { key: "SHP",   label: "SHP", sort: null },
  { key: "HIT",   label: "HIT", sort: null },
  { key: "BLK",   label: "BLK", sort: null },
  { key: "FOW",   label: "FOW", sort: null },
];

const NHL_TEAMS = [
  "ANA","BOS","BUF","CGY","CAR","CHI","COL","CBJ","DAL","DET","EDM","FLA",
  "LAK","MIN","MTL","NSH","NJD","NYI","NYR","OTT","PHI","PIT","SEA","SJS",
  "STL","TBL","TOR","UTA","VAN","VGK","WPG","WSH",
];

function buildQueryFromView(view, leagueId, position, search, nhlTeam, fantasyTeamId, page, ownTeamId, timeframe, sortBy, sortDir) {
  const p = new URLSearchParams();
  if (leagueId) p.append("league_id", leagueId);
  if (search) p.append("search", search);
  if (position && position !== "all") p.append("position", position);
  if (nhlTeam && nhlTeam !== "all") p.append("nhl_team", nhlTeam);
  if (fantasyTeamId && fantasyTeamId !== "all") p.append("fantasy_team_id", fantasyTeamId);
  if (timeframe) p.append("timeframe", timeframe);
  if (sortBy) p.append("sort_by", sortBy);
  if (sortDir) p.append("sort_dir", sortDir);
  p.append("page", String(page));
  p.append("limit", "50");

  switch (view) {
    case "all": break;
    case "available":
      p.append("availability", "free_agent"); break;
    case "available_or_own": break;
    case "watchlist_or_own":
      p.append("availability", "watchlist_or_own"); break;
    case "owned":
      p.append("availability", "owned"); break;
    case "waivers":
      p.append("availability", "waivers"); break;
    case "trade_block":
      p.append("availability", "trade_block"); break;
    case "nhl_available":
      p.append("availability", "free_agent"); break;
    case "nhl_taken":
      p.append("availability", "owned"); break;
    case "injured_available":
      p.append("availability", "free_agent"); p.append("injured", "true"); break;
    case "injured_taken":
      p.append("availability", "owned"); p.append("injured", "true"); break;
    case "minors_available":
      p.append("availability", "free_agent"); p.append("minors_eligible", "true"); break;
    case "minors_taken":
      p.append("availability", "owned"); p.append("minors_eligible", "true"); break;
    case "watchlist":
      p.append("availability", "watchlist"); break;
    case "exclude_own":
      if (ownTeamId) p.append("exclude_team_id", ownTeamId);
      break;
    default: break;
  }
  return p.toString();
}

function StarToggle({ player, onToggle }) {
  const inWL = !!player.is_in_watchlist;
  return (
    <button
      type="button"
      onClick={() => onToggle(player)}
      className={`h-7 w-7 rounded-full inline-flex items-center justify-center transition-colors ${
        inWL ? "text-amber-300 hover:bg-amber-400/15" : "text-muted-foreground hover:text-amber-300 hover:bg-amber-400/10"
      }`}
      data-testid={`watchlist-toggle-${player._id}`}
      aria-label={inWL ? "Remove from watch list" : "Add to watch list"}
    >
      <Star className="h-4 w-4" fill={inWL ? "currentColor" : "none"} />
    </button>
  );
}

function OwnedCell({ player }) {
  if (!player.owned_by_team_id) {
    return <span className="text-emerald-400 text-xs font-bold">FA</span>;
  }
  return (
    <Link
      to={`/teams/${player.owned_by_team_id}`}
      className="text-cyan-300 text-xs font-bold hover:underline"
      title={player.owned_by_team_name}
    >
      {player.owned_by_team_abbr}
    </Link>
  );
}

function PctCell({ pct }) {
  if (pct == null) return <span className="text-muted-foreground">—</span>;
  const tone = pct >= 75 ? "text-emerald-300" : pct >= 25 ? "text-cyan-300" : "text-amber-300";
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className={`text-xs font-semibold cursor-help ${tone}`}>{pct}%</span>
        </TooltipTrigger>
        <TooltipContent side="top" className="text-[11px]">{pct}% owned in league</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

function ChangeCell({ delta }) {
  if (delta == null) return <span className="text-muted-foreground text-xs">—</span>;
  const tone = delta > 0 ? "text-emerald-300" : delta < 0 ? "text-rose-400" : "text-muted-foreground";
  const Arrow = delta > 0 ? ArrowUp : delta < 0 ? ArrowDown : null;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className={`text-xs font-semibold inline-flex items-center gap-0.5 cursor-help ${tone}`}>
            {Arrow && <Arrow className="h-3 w-3" />}
            {delta > 0 ? "+" : ""}{delta}%
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="text-[11px]">
          7-day ownership change across DD
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

function StartPctCell({ pct }) {
  if (pct == null) return <span className="text-muted-foreground text-xs">—</span>;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="text-xs font-semibold text-violet-300 cursor-help">{pct}%</span>
        </TooltipTrigger>
        <TooltipContent side="top" className="text-[11px]">
          Estimated % of leagues starting this player. Refines as active-lineup tracking is rolled out.
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/** Document icon with a 3-bar signal strength based on news age band. */
function NewsSignal({ player }) {
  const signal = player.news_signal;
  if (!signal) return <span className="text-muted-foreground text-xs">—</span>;
  const palette = signal === "fresh"
    ? { color: "text-emerald-400", bars: 3 }
    : signal === "stale"
      ? { color: "text-amber-300", bars: 2 }
      : { color: "text-rose-400", bars: 1 };
  const heights = [3, 6, 9];
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <a
            href={player.news_url || "#"}
            target="_blank" rel="noreferrer"
            className={`inline-flex items-center gap-1 ${palette.color}`}
            data-testid={`players-news-signal-${player._id}`}
            onClick={(e) => { if (!player.news_url) e.preventDefault(); }}
          >
            <FileText className="h-3.5 w-3.5" />
            <span className="inline-flex items-end gap-[1px] h-3">
              {heights.map((h, i) => (
                <span
                  key={i}
                  className={`w-[3px] rounded-sm ${i < palette.bars ? "bg-current" : "bg-current/25"}`}
                  style={{ height: `${h}px` }}
                />
              ))}
            </span>
          </a>
        </TooltipTrigger>
        <TooltipContent side="top" className="text-[11px] max-w-[280px]">
          <div className="font-semibold">{player.news_headline}</div>
          <div className="text-muted-foreground mt-1">
            {player.news_age_days} days old · {signal === "fresh" ? "Recent" : signal === "stale" ? "Aging" : "Stale"}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/** Sortable header cell: click to toggle asc/desc, indicates active sort. */
function SortHeader({ label, sortKey, currentSort, currentDir, onSort, align = "center" }) {
  const isActive = currentSort === sortKey;
  const Icon = !isActive ? ArrowUpDown : currentDir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th
      className={`p-2 text-${align} text-xs uppercase tracking-wider text-muted-foreground ${sortKey ? "cursor-pointer select-none hover:text-foreground" : ""}`}
      onClick={() => sortKey && onSort(sortKey)}
      data-testid={sortKey ? `players-sort-${sortKey}` : undefined}
    >
      <span className={`inline-flex items-center gap-1 ${isActive ? "text-primary" : ""}`}>
        {label}
        {sortKey && <Icon className="h-3 w-3 opacity-60" />}
      </span>
    </th>
  );
}

export default function PlayersPage() {
  const navigate = useNavigate();
  const { league: activeLeague, leagueId, myTeam, leagueTeams } = useActiveLeague();
  const ownTeamId = myTeam?.id;

  const [view, setView] = useState("available");
  const [position, setPosition] = useState("all");
  const [nhlTeam, setNhlTeam] = useState("all");
  const [fantasyTeamId, setFantasyTeamId] = useState("all");
  const [search, setSearch] = useState("");
  const [timeframe, setTimeframe] = useState("season");
  const [sortBy, setSortBy] = useState("points");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(1);

  const [players, setPlayers] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [timeframeSupported, setTimeframeSupported] = useState(true);

  useEffect(() => { setPage(1); }, [view, position, nhlTeam, fantasyTeamId, search, timeframe]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const qs = buildQueryFromView(view, leagueId, position, search, nhlTeam, fantasyTeamId, page, ownTeamId, timeframe, sortBy, sortDir);
    api.get(`/players?${qs}`)
      .then(({ data }) => {
        if (cancelled) return;
        let list = data.players || [];
        let totalCount = data.total ?? list.length;
        let totalPages = data.pages ?? 1;
        setTimeframeSupported(!!data.timeframe_supported);
        if (view === "available_or_own" && ownTeamId) {
          list = list.filter((p) => !p.owned_by_team_id || p.owned_by_team_id === ownTeamId);
          totalCount = list.length;
          totalPages = 1;
        }
        setPlayers(list);
        setTotal(totalCount);
        setPages(totalPages);
      })
      .catch(() => { if (!cancelled) { setPlayers([]); setTotal(0); setPages(1); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [view, leagueId, position, nhlTeam, fantasyTeamId, search, page, ownTeamId, timeframe, sortBy, sortDir]);

  const toggleWatchlist = async (player) => {
    try {
      const { data } = await api.post(`/watchlist/toggle`, {
        player_id: player._id, league_id: leagueId,
      });
      setPlayers((prev) => prev.map((p) =>
        p._id === player._id ? { ...p, is_in_watchlist: data.in_watchlist } : p,
      ));
    } catch (e) { /* ignore */ }
  };

  const handleSort = (key) => {
    if (sortBy === key) {
      setSortDir((d) => d === "asc" ? "desc" : "asc");
    } else {
      setSortBy(key);
      setSortDir("desc");
    }
  };

  const fantasyTeamOptions = useMemo(() => {
    const items = [{ value: "all", label: "All Fantasy Teams" }];
    (leagueTeams || []).forEach((t) => {
      items.push({ value: t.id, label: `${t.logo_abbr || ""} · ${t.name}`.trim() });
    });
    return items;
  }, [leagueTeams]);

  return (
    <AppLayout>
      <div className="max-w-[1500px] mx-auto px-2" data-testid="players-page">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <h1 className="font-heading text-4xl font-bold tracking-tight text-white">PLAYERS</h1>
            <p className="text-[#A1A1AA] text-sm">
              {activeLeague ? `Filtered against ${activeLeague.name}` : "Browse every NHL player"}
              {" · "}{total.toLocaleString()} matches
            </p>
          </div>
        </div>

        {/* Filter bar */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-2 mb-4 items-center">
          <div className="md:col-span-3">
            <Select value={view} onValueChange={setView}>
              <SelectTrigger className="h-9 text-xs bg-[#1A1A1A] border-white/10" data-testid="players-view-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {VIEWS.map((v) => <SelectItem key={v.value} value={v.value}>{v.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="md:col-span-2">
            <Select value={position} onValueChange={setPosition}>
              <SelectTrigger className="h-9 text-xs bg-[#1A1A1A] border-white/10" data-testid="players-position-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {POSITIONS.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="md:col-span-2">
            <Select value={nhlTeam} onValueChange={setNhlTeam}>
              <SelectTrigger className="h-9 text-xs bg-[#1A1A1A] border-white/10" data-testid="players-nhl-select">
                <SelectValue placeholder="NHL Team" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All NHL Teams</SelectItem>
                {NHL_TEAMS.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="md:col-span-2">
            <Select value={fantasyTeamId} onValueChange={setFantasyTeamId}>
              <SelectTrigger className="h-9 text-xs bg-[#1A1A1A] border-white/10" data-testid="players-fantasy-team-select">
                <SelectValue placeholder="Fantasy Team" />
              </SelectTrigger>
              <SelectContent>
                {fantasyTeamOptions.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="md:col-span-2">
            <Select value={timeframe} onValueChange={setTimeframe}>
              <SelectTrigger className="h-9 text-xs bg-[#1A1A1A] border-white/10" data-testid="players-timeframe-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIMEFRAMES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="md:col-span-1 relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Search…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-7 h-9 text-xs bg-[#1A1A1A] border-white/10"
              data-testid="players-search-input"
            />
          </div>
        </div>

        {!timeframeSupported && timeframe !== "season" && (
          <div className="mb-3 px-3 py-2 rounded-md bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs" data-testid="players-timeframe-banner">
            Timeframe filtering for "{TIMEFRAMES.find((t) => t.value === timeframe)?.label}" is rolling out — currently showing season totals while per-game stats backfill.
          </div>
        )}

        {/* Table */}
        <div className="surface overflow-x-auto" data-testid="players-table-wrap">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 bg-secondary/30">
                <th className="p-2 w-10" />
                <SortHeader label="Player"  sortKey="name"     currentSort={sortBy} currentDir={sortDir} onSort={handleSort} align="left" />
                <SortHeader label="Pos"     sortKey="position" currentSort={sortBy} currentDir={sortDir} onSort={handleSort} />
                <SortHeader label="Team"    sortKey="team"     currentSort={sortBy} currentDir={sortDir} onSort={handleSort} />
                <th className="p-2 text-center text-xs uppercase tracking-wider text-muted-foreground">Owned</th>
                <SortHeader label="OWN%"     sortKey="league_pct" currentSort={sortBy} currentDir={sortDir} onSort={handleSort} />
                <SortHeader label="% Chg 7d" sortKey="pct_change" currentSort={sortBy} currentDir={sortDir} onSort={handleSort} />
                <SortHeader label="% Start"  sortKey="start_pct"  currentSort={sortBy} currentDir={sortDir} onSort={handleSort} />
                {STAT_COLS.map((c) => (
                  <SortHeader key={c.key} label={c.label} sortKey={c.sort} currentSort={sortBy} currentDir={sortDir} onSort={handleSort} />
                ))}
                <th className="p-2 text-center text-xs uppercase tracking-wider text-muted-foreground">Sched</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={8 + STAT_COLS.length + 1} className="p-8 text-center text-muted-foreground">Loading…</td></tr>
              )}
              {!loading && players.length === 0 && (
                <tr><td colSpan={8 + STAT_COLS.length + 1} className="p-8 text-center text-muted-foreground">No players match these filters.</td></tr>
              )}
              {!loading && players.map((p) => {
                const stats = p.category_breakdown || p.stats || {};
                const cell = (key) => {
                  if (key === "PTS") return p.points ?? ((stats.G ?? 0) + (stats.A ?? 0));
                  if (key === "+/-") return p.plus_minus ?? stats["+/-"] ?? 0;
                  if (key === "G") return p.goals ?? stats.G ?? 0;
                  if (key === "A") return p.assists ?? stats.A ?? 0;
                  return stats[key] ?? p[key?.toLowerCase()] ?? 0;
                };
                return (
                  <tr key={p._id} className="border-b border-white/5 hover:bg-secondary/10" data-testid={`players-row-${p._id}`}>
                    <td className="p-2">
                      <StarToggle player={p} onToggle={toggleWatchlist} />
                    </td>
                    <td className="p-2">
                      <div className="flex items-center gap-1.5">
                        <Link to={`/players/${p._id}`} className="font-medium text-white hover:text-primary">{p.name}</Link>
                        {p.news_signal && <NewsSignal player={p} />}
                      </div>
                    </td>
                    <td className="p-2 text-center text-xs text-muted-foreground">{p.position}</td>
                    <td className="p-2 text-center text-xs text-muted-foreground">{p.team}</td>
                    <td className="p-2 text-center"><OwnedCell player={p} /></td>
                    <td className="p-2 text-center"><PctCell pct={p.league_pct} /></td>
                    <td className="p-2 text-center"><ChangeCell delta={p.pct_change_7d} /></td>
                    <td className="p-2 text-center"><StartPctCell pct={p.start_pct} /></td>
                    {STAT_COLS.map((c) => (
                      <td key={c.key} className={`p-2 text-center text-xs ${c.key === "PTS" ? "text-cyan-300 font-bold" : ""}`}>
                        {cell(c.key)}
                      </td>
                    ))}
                    <td className="p-2 text-center">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              onClick={() => navigate(`/players/${p._id}`)}
                              className="text-muted-foreground hover:text-cyan-300"
                              data-testid={`players-schedule-btn-${p._id}`}
                            >
                              <Calendar className="h-3.5 w-3.5" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="text-[11px]">
                            View {p.team} upcoming schedule
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {pages > 1 && (
          <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
            <span>Page {page} / {pages} · {total.toLocaleString()} players</span>
            <div className="flex gap-1">
              <Button
                variant="outline" size="sm" className="h-7 text-xs"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
                data-testid="players-prev-page"
              >
                <ChevronLeft className="h-3 w-3" />
              </Button>
              <Button
                variant="outline" size="sm" className="h-7 text-xs"
                disabled={page >= pages}
                onClick={() => setPage(page + 1)}
                data-testid="players-next-page"
              >
                <ChevronRight className="h-3 w-3" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
