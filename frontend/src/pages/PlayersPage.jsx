import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { AppLayout } from "@/components/layout/AppLayout";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Star, Search, ChevronLeft, ChevronRight } from "lucide-react";
import { useActiveLeague } from "@/hooks/use-active-league";
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from "@/components/ui/tooltip";

/**
 * Players page
 *
 * Powerful filtered listing of every NHL player relative to the active
 * league. Supports the full set of filtered views the commissioner asked
 * for (free agents, owned, watchlist, trade block, waivers, injured,
 * minors-eligible, etc.) plus position / NHL-team / fantasy-team filters
 * and a star (watchlist) column.
 */

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

// All league-tracked categories (matches PlayerRoster). Order = column order.
const STAT_COLS = ["G", "A", "PTS", "+/-", "SOG", "PPP", "SHP", "HIT", "BLK", "FOW"];

const NHL_TEAMS = [
  "ANA","BOS","BUF","CGY","CAR","CHI","COL","CBJ","DAL","DET","EDM","FLA",
  "LAK","MIN","MTL","NSH","NJD","NYI","NYR","OTT","PHI","PIT","SEA","SJS",
  "STL","TBL","TOR","UTA","VAN","VGK","WPG","WSH",
];

function buildQueryFromView(view, leagueId, position, search, nhlTeam, fantasyTeamId, page, ownTeamId) {
  const p = new URLSearchParams();
  if (leagueId) p.append("league_id", leagueId);
  if (search) p.append("search", search);
  if (position && position !== "all") p.append("position", position);
  if (nhlTeam && nhlTeam !== "all") p.append("nhl_team", nhlTeam);
  if (fantasyTeamId && fantasyTeamId !== "all") p.append("fantasy_team_id", fantasyTeamId);
  p.append("page", String(page));
  p.append("limit", "50");

  // Map our high-level views onto backend params
  switch (view) {
    case "all": break;
    case "available":
      p.append("availability", "free_agent"); break;
    case "available_or_own":
      // Backend doesn't have a single op for this, use availability=all and let
      // the page render anything that's either FA or owned by the user's team.
      // To keep it server-side, we issue free_agent + own roster client-side.
      // Simpler: fall back to "all" and post-filter.
      break;
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

export default function PlayersPage() {
  const navigate = useNavigate();
  const { league: activeLeague, leagueId, myTeam, leagueTeams } = useActiveLeague();
  const ownTeamId = myTeam?.id;

  const [view, setView] = useState("available");
  const [position, setPosition] = useState("all");
  const [nhlTeam, setNhlTeam] = useState("all");
  const [fantasyTeamId, setFantasyTeamId] = useState("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const [players, setPlayers] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(false);

  // Reset to page 1 when filters change
  useEffect(() => { setPage(1); }, [view, position, nhlTeam, fantasyTeamId, search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const qs = buildQueryFromView(view, leagueId, position, search, nhlTeam, fantasyTeamId, page, ownTeamId);
    api.get(`/players?${qs}`)
      .then(({ data }) => {
        if (cancelled) return;
        let list = data.players || [];
        let totalCount = data.total ?? list.length;
        let totalPages = data.pages ?? 1;
        // Client-side post-filter for "Available + Own Team" (API can't union the two sets cheaply)
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
  }, [view, leagueId, position, nhlTeam, fantasyTeamId, search, page, ownTeamId]);

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

  const fantasyTeamOptions = useMemo(() => {
    const items = [{ value: "all", label: "All Fantasy Teams" }];
    (leagueTeams || []).forEach((t) => {
      items.push({ value: t.id, label: `${t.logo_abbr || ""} · ${t.name}`.trim() });
    });
    return items;
  }, [leagueTeams]);

  return (
    <AppLayout>
      <div className="max-w-[1400px] mx-auto px-2" data-testid="players-page">
        {/* Header */}
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
          <div className="md:col-span-4">
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
          <div className="md:col-span-2 relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Search name…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-7 h-9 text-xs bg-[#1A1A1A] border-white/10"
              data-testid="players-search-input"
            />
          </div>
        </div>

        {/* Table */}
        <div className="surface overflow-x-auto" data-testid="players-table-wrap">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 bg-secondary/30">
                <th className="p-2 w-10" />
                <th className="p-2 text-left text-xs uppercase tracking-wider text-muted-foreground">Player</th>
                <th className="p-2 text-center text-xs uppercase tracking-wider text-muted-foreground">Pos</th>
                <th className="p-2 text-center text-xs uppercase tracking-wider text-muted-foreground">Team</th>
                <th className="p-2 text-center text-xs uppercase tracking-wider text-muted-foreground">Owned</th>
                <th className="p-2 text-center text-xs uppercase tracking-wider text-muted-foreground">OWN%</th>
                {STAT_COLS.map((c) => (
                  <th key={c} className="p-2 text-center text-xs uppercase tracking-wider text-muted-foreground">{c}</th>
                ))}
                <th className="p-2 text-center text-xs uppercase tracking-wider text-muted-foreground">Status</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={6 + STAT_COLS.length + 1} className="p-8 text-center text-muted-foreground">Loading…</td></tr>
              )}
              {!loading && players.length === 0 && (
                <tr><td colSpan={6 + STAT_COLS.length + 1} className="p-8 text-center text-muted-foreground">No players match these filters.</td></tr>
              )}
              {!loading && players.map((p) => {
                const stats = p.category_breakdown || p.stats || {};
                const cell = (cat) => {
                  if (cat === "PTS") return p.points ?? ((stats.G ?? 0) + (stats.A ?? 0));
                  if (cat === "+/-") return p.plus_minus ?? stats["+/-"] ?? 0;
                  if (cat === "G") return p.goals ?? stats.G ?? 0;
                  if (cat === "A") return p.assists ?? stats.A ?? 0;
                  return stats[cat] ?? p[cat?.toLowerCase()] ?? 0;
                };
                return (
                  <tr key={p._id} className="border-b border-white/5 hover:bg-secondary/10" data-testid={`players-row-${p._id}`}>
                    <td className="p-2">
                      <StarToggle player={p} onToggle={toggleWatchlist} />
                    </td>
                    <td className="p-2">
                      <Link to={`/players/${p._id}`} className="font-medium text-white hover:text-primary">{p.name}</Link>
                    </td>
                    <td className="p-2 text-center text-xs text-muted-foreground">{p.position}</td>
                    <td className="p-2 text-center text-xs text-muted-foreground">{p.team}</td>
                    <td className="p-2 text-center"><OwnedCell player={p} /></td>
                    <td className="p-2 text-center"><PctCell pct={p.league_pct} /></td>
                    {STAT_COLS.map((c) => (
                      <td key={c} className={`p-2 text-center text-xs ${c === "PTS" ? "text-cyan-300 font-bold" : ""}`}>
                        {cell(c)}
                      </td>
                    ))}
                    <td className="p-2 text-center text-[10px] space-x-1">
                      {p.is_on_trade_block && <span className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300">BLOCK</span>}
                      {p.is_on_waivers && <span className="px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-300">WAIV</span>}
                      {p.injury_status && p.injury_status !== "Healthy" && (
                        <span className="px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-300">INJ</span>
                      )}
                      {p.minors_eligible && <span className="px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-300">MINORS</span>}
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
