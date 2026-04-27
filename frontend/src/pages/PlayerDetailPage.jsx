import { useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowLeft, User, Trophy, Target, TrendingUp, Shield, Zap, Clock, Newspaper, ExternalLink, Globe, ArrowRightLeft, Home as HomeIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import PlayerBioBar from "@/lovable/components/PlayerBioBar";

const positionLabels = { C: "Center", LW: "Left Wing", RW: "Right Wing", D: "Defenseman", G: "Goalie" };
const positionColors = {
  C: "bg-blue-600 text-blue-100",
  LW: "bg-emerald-600 text-emerald-100",
  RW: "bg-teal-600 text-teal-100",
  D: "bg-amber-600 text-amber-100",
  G: "bg-purple-600 text-purple-100",
};

const formatTimeAgo = (iso) => {
  if (!iso) return "—";
  try {
    const ms = Date.now() - new Date(iso).getTime();
    if (ms < 0) return "just now";
    const m = Math.floor(ms / 60000);
    if (m < 1) return "just now";
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    if (d < 30) return `${d}d ago`;
    return new Date(iso).toLocaleDateString();
  } catch {
    return "—";
  }
};

function StatBar({ label, value, max, suffix = "" }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-[#A1A1AA]">{label}</span>
        <span className="text-white font-semibold">{value}{suffix}</span>
      </div>
      <Progress value={Math.min(pct, 100)} className="h-1.5" />
    </div>
  );
}

function StatCard({ icon: Icon, label, value, color }) {
  return (
    <Card className="border-white/10">
      <CardContent className="p-5 flex items-center gap-3">
        <div className="h-10 w-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${color}20` }}>
          <Icon className="h-5 w-5" style={{ color }} />
        </div>
        <div>
          <p className="text-sm text-[#A1A1AA]">{label}</p>
          <p className="text-xl font-bold text-white">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export default function PlayerDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { league } = useActiveLeague();
  const leagueId = searchParams.get("league_id") || league?.id || null;

  const [player, setPlayer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("overview");

  // Tab data
  const [news, setNews] = useState([]);
  const [recentGames, setRecentGames] = useState([]);
  const [history, setHistory] = useState({ seasons: [], is_goalie: false });
  const [perf, setPerf] = useState(null);
  const [crossLeague, setCrossLeague] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [usage, setUsage] = useState([]);
  const [projections, setProjections] = useState(null);

  useEffect(() => {
    if (!id) return;
    const fetchAll = async () => {
      setLoading(true);
      try {
        const [p, n, g] = await Promise.all([
          api.get(`/players/${id}${leagueId ? `?league_id=${leagueId}` : ""}`),
          api.get(`/players/${id}/news?limit=20`),
          api.get(`/players/${id}/recent-games${leagueId ? `?league_id=${leagueId}&limit=10` : "?limit=10"}`),
        ]);
        setPlayer(p.data);
        setNews(n.data?.news || []);
        setRecentGames(g.data?.games || []);
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    fetchAll();
  }, [id, leagueId]);

  // Lazy-load each tab the first time it's opened
  useEffect(() => {
    if (!id) return;
    if (tab === "stats" && history.seasons.length === 0) {
      api.get(`/players/${id}/historical-stats${leagueId ? `?league_id=${leagueId}` : ""}`)
         .then(({ data }) => setHistory(data || { seasons: [] })).catch(() => {});
    }
    if (tab === "performance" && !perf) {
      api.get(`/players/${id}/recent-performance${leagueId ? `?league_id=${leagueId}` : ""}`)
         .then(({ data }) => setPerf(data)).catch(() => {});
    }
    if (tab === "cross-league" && crossLeague.length === 0) {
      api.get(`/players/${id}/cross-league-ownership`)
         .then(({ data }) => setCrossLeague(data?.leagues || [])).catch(() => {});
    }
    if (tab === "transactions" && transactions.length === 0) {
      api.get(`/players/${id}/transactions${leagueId ? `?league_id=${leagueId}` : ""}`)
         .then(({ data }) => setTransactions(data?.transactions || [])).catch(() => {});
    }
    if (tab === "projections" && !projections) {
      api.get(`/players/${id}/projections${leagueId ? `?league_id=${leagueId}` : ""}`)
         .then(({ data }) => setProjections(data)).catch(() => {});
    }
    // Player Usage on Overview — auto-load alongside the page
    if (leagueId && usage.length === 0 && tab === "overview") {
      api.get(`/players/${id}/usage?league_id=${leagueId}`)
         .then(({ data }) => setUsage(data?.weeks || [])).catch(() => {});
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, id, leagueId]);

  if (loading) {
    return <AppLayout><div className="flex items-center justify-center h-[60vh] text-[#A1A1AA]">Loading player...</div></AppLayout>;
  }
  if (!player) {
    return (
      <AppLayout>
        <div className="text-center py-20">
          <User className="h-16 w-16 text-[#52525B] mx-auto mb-4" />
          <h2 className="text-xl text-white mb-2">Player not found</h2>
          <Button variant="outline" onClick={() => navigate("/players")} className="text-white border-white/10">Back to Players</Button>
        </div>
      </AppLayout>
    );
  }

  const isGoalie = player.position === "G";
  const teamName = player.team_name || player.team || "";

  return (
    <AppLayout>
      <div className="space-y-6" data-testid="player-detail-page">
        <button onClick={() => navigate(-1)} className="flex items-center gap-2 text-[#A1A1AA] hover:text-white" data-testid="player-detail-back">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>

        {/* Header */}
        <Card className="border-white/10 overflow-hidden">
          <div className="bg-gradient-to-r from-[#00D2FF]/10 to-transparent p-6">
            <div className="flex flex-col md:flex-row items-start md:items-center gap-6">
              <div className="h-24 w-24 rounded-2xl bg-[#1A1A1A] flex items-center justify-center text-3xl font-bold text-[#00D2FF] border border-white/10">
                {player.team || "?"}
              </div>
              <div className="flex-1">
                <h1 className="text-3xl font-bold text-white mb-1" data-testid="player-name">{player.name}</h1>
                <div className="flex flex-wrap items-center gap-3">
                  <Badge className={cn("text-sm px-3 py-1", positionColors[player.position])}>{positionLabels[player.position] || player.position}</Badge>
                  <span className="text-[#A1A1AA]">{teamName}</span>
                  <span className="text-[#A1A1AA]">#{player.nhl_id || ""}</span>
                </div>
                {player.shoots && <p className="text-sm text-[#A1A1AA] mt-2">Shoots: {player.shoots === "L" ? "Left" : "Right"}</p>}
              </div>
              <div className="text-right flex items-start gap-3">
                <Button
                  variant="outline"
                  className="text-white border-white/15 hover:border-[#00D2FF]"
                  onClick={() => navigate(`/compare?a=${player._id}${leagueId ? `&league_id=${leagueId}` : ""}`)}
                  data-testid="compare-player-btn"
                >
                  Compare
                </Button>
                <div>
                  <p className="text-sm text-[#A1A1AA]">Fantasy Points</p>
                  <p className="text-4xl font-bold text-[#00D2FF]" data-testid="fantasy-points">
                    {player.fantasy_points != null
                      ? player.fantasy_points.toFixed(1)
                      : ((player.goals || 0) * 3 + (player.assists || 0) * 2 + (player.plus_minus || 0)).toFixed(1)}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </Card>

        {/* Bio bar */}
        <PlayerBioBar player={player} />

        {/* Latest news strip — always visible above the tabs */}
        {news.length > 0 && (
          <Card className="border-white/10" data-testid="player-latest-news">
            <CardContent className="p-4 flex items-start gap-3">
              <div className="h-9 w-9 rounded-lg bg-[#FFB020]/15 flex items-center justify-center shrink-0">
                <Newspaper className="h-4 w-4 text-[#FFB020]" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2 mb-0.5">
                  <p className="text-[10px] uppercase tracking-widest text-[#A1A1AA]">Latest news</p>
                  <span className="text-[10px] text-[#A1A1AA]" data-testid="player-latest-news-time">
                    {formatTimeAgo(news[0].published_at)}
                  </span>
                </div>
                <p className="text-sm text-white font-semibold truncate">{news[0].headline}</p>
                {news[0].summary && (
                  <p className="text-xs text-[#A1A1AA] mt-1 line-clamp-2">{news[0].summary}</p>
                )}
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="text-[11px] text-[#71717A]">{news[0].source || "—"}</span>
                  {news[0].url && (
                    <a
                      href={news[0].url} target="_blank" rel="noopener noreferrer"
                      className="text-[11px] text-[#00D2FF] inline-flex items-center gap-1 hover:underline"
                    >
                      Read <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Tabs */}
        <Tabs value={tab} onValueChange={setTab} className="space-y-4">
          <TabsList className="bg-[#141414] border border-white/10 flex-wrap h-auto p-1">
            <TabsTrigger value="overview" data-testid="tab-overview">Overview</TabsTrigger>
            <TabsTrigger value="stats" data-testid="tab-stats">Stats</TabsTrigger>
            <TabsTrigger value="performance" data-testid="tab-performance">Recent Performance</TabsTrigger>
            <TabsTrigger value="projections" data-testid="tab-projections">Projections</TabsTrigger>
            <TabsTrigger value="cross-league" data-testid="tab-cross-league">Cross-League Ownership</TabsTrigger>
            <TabsTrigger value="transactions" data-testid="tab-transactions">Fantasy Transactions</TabsTrigger>
            <TabsTrigger value="news" data-testid="tab-news">News</TabsTrigger>
          </TabsList>

          {/* OVERVIEW: existing key stats + recent games + Player Usage */}
          <TabsContent value="overview" className="space-y-6">
            {/* Key Stats */}
            <div className={cn("grid gap-4", isGoalie ? "grid-cols-2 md:grid-cols-4" : "grid-cols-2 md:grid-cols-5")}>
              {isGoalie ? (
                <>
                  <StatCard icon={Trophy} label="Wins" value={player.wins || 0} color="#34C759" />
                  <StatCard icon={Shield} label="Save %" value={`${(player.save_pct || 0).toFixed(1)}%`} color="#00D2FF" />
                  <StatCard icon={Target} label="GAA" value={(player.goals_against_avg || 0).toFixed(2)} color="#FF3B30" />
                  <StatCard icon={Zap} label="Shutouts" value={player.shutouts || 0} color="#FF9F0A" />
                </>
              ) : (
                <>
                  <StatCard icon={Target} label="Goals" value={player.goals || 0} color="#FF3B30" />
                  <StatCard icon={Zap} label="Assists" value={player.assists || 0} color="#00D2FF" />
                  <StatCard icon={Trophy} label="Points" value={player.points || 0} color="#34C759" />
                  <StatCard icon={TrendingUp} label="+/-" value={player.plus_minus || 0} color={(player.plus_minus || 0) >= 0 ? "#34C759" : "#FF3B30"} />
                  <StatCard icon={Clock} label="GP" value={player.games_played || 0} color="#A1A1AA" />
                </>
              )}
            </div>

            {/* Recent Games */}
            <Card className="border-white/10" data-testid="player-recent-games">
              <CardHeader>
                <CardTitle className="text-white text-base">Recent Games</CardTitle>
              </CardHeader>
              <CardContent>
                {recentGames.length === 0 ? (
                  <p className="text-sm text-[#A1A1AA] py-3">No recent games on file.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-[#A1A1AA] text-xs uppercase tracking-wider">
                        <tr className="border-b border-white/5">
                          <th className="text-left py-2 pr-4">Date</th>
                          <th className="text-left py-2 pr-4">Team</th>
                          <th className="text-left py-2 pr-4">Opp</th>
                          {isGoalie ? (
                            <>
                              <th className="text-right py-2 pr-3">W</th>
                              <th className="text-right py-2 pr-3">SV</th>
                              <th className="text-right py-2 pr-3">GA</th>
                            </>
                          ) : (
                            <>
                              <th className="text-right py-2 pr-3">G</th>
                              <th className="text-right py-2 pr-3">A</th>
                              <th className="text-right py-2 pr-3">SOG</th>
                              <th className="text-right py-2 pr-3">+/-</th>
                              <th className="text-right py-2 pr-3">HIT</th>
                              <th className="text-right py-2 pr-3">BLK</th>
                            </>
                          )}
                          <th className="text-right py-2">FPTS</th>
                        </tr>
                      </thead>
                      <tbody className="text-white">
                        {recentGames.map((g) => (
                          <tr key={g.game_id} className="border-b border-white/5" data-testid={`recent-game-${g.game_id}`}>
                            <td className="py-2 pr-4 text-[#A1A1AA]">{g.date}</td>
                            <td className="py-2 pr-4">{g.team || "—"}</td>
                            <td className="py-2 pr-4 text-[#A1A1AA]">{g.home_away === "home" ? "vs" : "@"} {g.opponent || "?"}</td>
                            {isGoalie ? (
                              <>
                                <td className="py-2 pr-3 text-right tabular-nums">{g.wins}</td>
                                <td className="py-2 pr-3 text-right tabular-nums">{g.saves}</td>
                                <td className="py-2 pr-3 text-right tabular-nums">{g.goals_against}</td>
                              </>
                            ) : (
                              <>
                                <td className="py-2 pr-3 text-right tabular-nums">{g.goals}</td>
                                <td className="py-2 pr-3 text-right tabular-nums">{g.assists}</td>
                                <td className="py-2 pr-3 text-right tabular-nums">{g.shots}</td>
                                <td className={cn("py-2 pr-3 text-right tabular-nums", g.plus_minus > 0 ? "text-emerald-400" : g.plus_minus < 0 ? "text-rose-400" : "")}>{g.plus_minus > 0 ? `+${g.plus_minus}` : g.plus_minus}</td>
                                <td className="py-2 pr-3 text-right tabular-nums">{g.hits}</td>
                                <td className="py-2 pr-3 text-right tabular-nums">{g.blocks}</td>
                              </>
                            )}
                            <td className="py-2 text-right tabular-nums font-semibold text-[#00D2FF]">{g.fantasy_points?.toFixed(1) ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Detailed Stats */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card className="border-white/10">
                <CardHeader><CardTitle className="text-white">{isGoalie ? "Goaltending" : "Offense"}</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  {isGoalie ? (
                    <>
                      <StatBar label="Games Played" value={player.games_played || 0} max={82} />
                      <StatBar label="Wins" value={player.wins || 0} max={50} />
                      <StatBar label="Saves" value={player.saves || 0} max={2000} />
                      <StatBar label="Save %" value={player.save_pct || 0} max={100} suffix="%" />
                      <StatBar label="GAA" value={player.goals_against_avg || 0} max={5} />
                      <StatBar label="Shutouts" value={player.shutouts || 0} max={10} />
                    </>
                  ) : (
                    <>
                      <StatBar label="Games Played" value={player.games_played || 0} max={82} />
                      <StatBar label="Goals" value={player.goals || 0} max={60} />
                      <StatBar label="Assists" value={player.assists || 0} max={90} />
                      <StatBar label="Points" value={player.points || 0} max={140} />
                      <StatBar label="Points Per Game" value={player.points_per_game || 0} max={2} />
                      <StatBar label="Shooting %" value={player.shooting_pct || 0} max={25} suffix="%" />
                      <StatBar label="Shots" value={player.shots || 0} max={400} />
                    </>
                  )}
                </CardContent>
              </Card>

              <Card className="border-white/10">
                <CardHeader><CardTitle className="text-white">{isGoalie ? "Additional" : "Special Teams & Advanced"}</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  {isGoalie ? (
                    <>
                      <StatBar label="Penalty Minutes" value={player.penalty_minutes || 0} max={30} />
                      <StatBar label="Shots Against" value={player.shots_against || 0} max={2200} />
                      <StatBar label="Goals Against" value={player.goals_against || 0} max={200} />
                    </>
                  ) : (
                    <>
                      <StatBar label="Plus/Minus" value={player.plus_minus || 0} max={50} />
                      <StatBar label="Power Play Goals" value={player.power_play_goals || 0} max={25} />
                      <StatBar label="Power Play Points" value={player.power_play_points || 0} max={40} />
                      <StatBar label="Game Winning Goals" value={player.game_winning_goals || 0} max={15} />
                      <StatBar label="Penalty Minutes" value={player.penalty_minutes || 0} max={150} />
                      <StatBar label="Faceoff Win %" value={player.faceoff_win_pct || 0} max={65} suffix="%" />
                      <StatBar label="TOI/Game (min)" value={player.toi_per_game || 0} max={25} />
                    </>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Player Usage */}
            <Card className="border-white/10" data-testid="player-usage-section">
              <CardHeader>
                <CardTitle className="text-white text-base flex items-center gap-2">
                  <HomeIcon className="h-4 w-4 text-[#00D2FF]" />
                  Player Usage {leagueId ? "" : <span className="text-xs text-[#A1A1AA]">(switch to a league to see)</span>}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {!leagueId ? (
                  <p className="text-sm text-[#A1A1AA] py-3">Pick an active league from the sidebar to see how this player was used in your matchups.</p>
                ) : usage.length === 0 ? (
                  <p className="text-sm text-[#A1A1AA] py-3">No matchup history yet — this player hasn't appeared on a roster in this league.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-[#A1A1AA] text-xs uppercase tracking-wider">
                        <tr className="border-b border-white/5">
                          <th className="text-left py-2 pr-3">Wk</th>
                          <th className="text-left py-2 pr-3">Team</th>
                          <th className="text-left py-2 pr-3">Opp</th>
                          <th className="text-left py-2 pr-3">Status</th>
                          <th className="text-left py-2 pr-3">Slot</th>
                          <th className="text-right py-2">Result</th>
                        </tr>
                      </thead>
                      <tbody className="text-white">
                        {usage.map((w, i) => (
                          <tr key={`${w.week}-${i}`} className="border-b border-white/5" data-testid={`player-usage-week-${w.week}`}>
                            <td className="py-2 pr-3 text-[#A1A1AA]">W{w.week}</td>
                            <td className="py-2 pr-3 truncate max-w-[160px]">{w.team_name}</td>
                            <td className="py-2 pr-3 text-[#A1A1AA] truncate max-w-[160px]">vs {w.opponent_name}</td>
                            <td className="py-2 pr-3">
                              <Badge variant="outline" className={w.is_active ? "border-emerald-500/40 text-emerald-400" : "border-white/10 text-[#A1A1AA]"}>
                                {w.is_active ? "Active" : (w.section || "Bench")}
                              </Badge>
                            </td>
                            <td className="py-2 pr-3 text-[#A1A1AA] uppercase">{w.slot || (w.is_active ? player.position : "—")}</td>
                            <td className="py-2 text-right">
                              {w.result ? (
                                <Badge className={w.result === "W" ? "bg-emerald-600 text-emerald-50" : w.result === "L" ? "bg-rose-600 text-rose-50" : "bg-zinc-600 text-zinc-100"}>
                                  {w.result} {w.score_for}–{w.score_against}
                                </Badge>
                              ) : (
                                <span className="text-xs text-[#71717A] capitalize">{w.status}</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* STATS — career season-by-season */}
          <TabsContent value="stats">
            <Card className="border-white/10" data-testid="player-historical-stats">
              <CardHeader>
                <CardTitle className="text-white text-base">Career — by Season</CardTitle>
                {leagueId && <p className="text-xs text-[#A1A1AA]">Fantasy Points use the active league's scoring config — even for years before the league existed.</p>}
              </CardHeader>
              <CardContent>
                {history.seasons.length === 0 ? (
                  <p className="text-sm text-[#A1A1AA] py-3">{history.error || "Loading career stats from the NHL…"}</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-[#A1A1AA] text-xs uppercase tracking-wider">
                        <tr className="border-b border-white/5">
                          <th className="text-left py-2 pr-3">Season</th>
                          <th className="text-left py-2 pr-3">Team</th>
                          <th className="text-right py-2 pr-3">GP</th>
                          {history.is_goalie ? (
                            <>
                              <th className="text-right py-2 pr-3">W-L-OTL</th>
                              <th className="text-right py-2 pr-3">SV</th>
                              <th className="text-right py-2 pr-3">SO</th>
                              <th className="text-right py-2 pr-3">GAA</th>
                              <th className="text-right py-2 pr-3">SV%</th>
                            </>
                          ) : (
                            <>
                              <th className="text-right py-2 pr-3">G</th>
                              <th className="text-right py-2 pr-3">A</th>
                              <th className="text-right py-2 pr-3">PTS</th>
                              <th className="text-right py-2 pr-3">+/-</th>
                              <th className="text-right py-2 pr-3">PPG</th>
                              <th className="text-right py-2 pr-3">SOG</th>
                            </>
                          )}
                          <th className="text-right py-2">FPTS</th>
                        </tr>
                      </thead>
                      <tbody className="text-white">
                        {history.seasons.map((s, i) => (
                          <tr key={i} className="border-b border-white/5" data-testid={`historical-season-${s.season}`}>
                            <td className="py-2 pr-3 font-semibold">{s.season}</td>
                            <td className="py-2 pr-3 text-[#A1A1AA] truncate max-w-[200px]">{s.team}</td>
                            <td className="py-2 pr-3 text-right tabular-nums">{s.games_played}</td>
                            {history.is_goalie ? (
                              <>
                                <td className="py-2 pr-3 text-right tabular-nums">{s.wins}-{s.losses}-{s.ot_losses}</td>
                                <td className="py-2 pr-3 text-right tabular-nums">{s.saves}</td>
                                <td className="py-2 pr-3 text-right tabular-nums">{s.shutouts}</td>
                                <td className="py-2 pr-3 text-right tabular-nums">{(s.goals_against_avg || 0).toFixed(2)}</td>
                                <td className="py-2 pr-3 text-right tabular-nums">{((s.save_pct || 0) * 100).toFixed(1)}</td>
                              </>
                            ) : (
                              <>
                                <td className="py-2 pr-3 text-right tabular-nums">{s.goals}</td>
                                <td className="py-2 pr-3 text-right tabular-nums">{s.assists}</td>
                                <td className="py-2 pr-3 text-right tabular-nums font-semibold">{s.points}</td>
                                <td className={cn("py-2 pr-3 text-right tabular-nums", s.plus_minus > 0 ? "text-emerald-400" : s.plus_minus < 0 ? "text-rose-400" : "")}>{s.plus_minus > 0 ? `+${s.plus_minus}` : s.plus_minus}</td>
                                <td className="py-2 pr-3 text-right tabular-nums">{s.power_play_goals}</td>
                                <td className="py-2 pr-3 text-right tabular-nums">{s.shots}</td>
                              </>
                            )}
                            <td className="py-2 text-right tabular-nums font-semibold text-[#00D2FF]">{s.fantasy_points?.toFixed(1) ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* RECENT PERFORMANCE — windows */}
          <TabsContent value="performance">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="player-recent-performance">
              {(perf?.windows ? Object.entries(perf.windows) : []).map(([label, w]) => (
                <Card key={label} className="border-white/10" data-testid={`perf-window-${label}`}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-xs uppercase tracking-wider text-[#A1A1AA]">
                      {label === "last_7d" ? "Last 7 days" : label === "prev_7d" ? "Week before" : label === "last_14d" ? "Last 14 days" : "Last 30 days"}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1.5">
                    <p className="text-3xl font-bold text-[#00D2FF]">{w.fantasy_points?.toFixed(1) ?? "—"}</p>
                    <p className="text-xs text-[#A1A1AA]">FPTS · {w.games_played} GP</p>
                    {history.is_goalie || perf?.is_goalie ? (
                      <p className="text-xs text-white">{w.wins}W · {w.saves} SV · {w.goals_against} GA</p>
                    ) : (
                      <p className="text-xs text-white">{w.goals}G {w.assists}A · {w.shots} SOG · {w.plus_minus > 0 ? `+${w.plus_minus}` : w.plus_minus}</p>
                    )}
                  </CardContent>
                </Card>
              ))}
              {!perf && (
                <p className="text-sm text-[#A1A1AA] col-span-full py-6">Loading windows…</p>
              )}
            </div>
          </TabsContent>

          {/* PROJECTIONS — ROS + weekly */}
          <TabsContent value="projections">
            <Card className="border-white/10" data-testid="player-projections">
              <CardHeader>
                <CardTitle className="text-white text-base flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-[#00D2FF]" /> Player Projections
                </CardTitle>
                <p className="text-xs text-[#A1A1AA]">
                  Deterministic projection blending season FPG (60%) and last-14-day FPG (40%). Scored against {leagueId ? "this league's rules" : "platform default scoring"}.
                </p>
              </CardHeader>
              <CardContent>
                {!projections ? (
                  <p className="text-sm text-[#A1A1AA] py-6">Loading projections…</p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <Card className="border-[#00D2FF]/20" data-testid="projection-ros">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-xs uppercase tracking-wider text-[#A1A1AA]">Rest of Season</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        <p className="text-4xl font-bold text-[#00D2FF] tabular-nums">{projections.projected_ros_fpts.toFixed(1)}</p>
                        <p className="text-xs text-[#A1A1AA]">FPTS over {projections.games_remaining} games remaining</p>
                        <div className="grid grid-cols-2 gap-2 pt-3 border-t border-white/5 text-xs text-[#A1A1AA]">
                          <div><span className="text-white">{projections.blended_fpg.toFixed(2)}</span> Blended FPG</div>
                          <div className="capitalize">Source: <span className="text-white">{projections.source.replace("_", " ")}</span></div>
                        </div>
                      </CardContent>
                    </Card>
                    <Card className="border-[#FFB020]/20" data-testid="projection-week">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-xs uppercase tracking-wider text-[#A1A1AA]">Next Week</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        <p className="text-4xl font-bold text-[#FFB020] tabular-nums">{projections.projected_week_fpts.toFixed(1)}</p>
                        <p className="text-xs text-[#A1A1AA]">FPTS over ~{projections.games_per_week_assumed} games</p>
                        <div className="grid grid-cols-2 gap-2 pt-3 border-t border-white/5 text-xs text-[#A1A1AA]">
                          <div><span className="text-white">{projections.season_fpg.toFixed(2)}</span> Season FPG</div>
                          <div><span className="text-white">{projections.recent_fpg.toFixed(2)}</span> Last-14d FPG</div>
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* CROSS-LEAGUE OWNERSHIP */}
          <TabsContent value="cross-league">
            <Card className="border-white/10" data-testid="player-cross-league">
              <CardHeader>
                <CardTitle className="text-white text-base flex items-center gap-2">
                  <Globe className="h-4 w-4 text-[#00D2FF]" /> Cross-League Ownership
                </CardTitle>
                <p className="text-xs text-[#A1A1AA]">Where this player sits across each of your leagues.</p>
              </CardHeader>
              <CardContent>
                {crossLeague.length === 0 ? (
                  <p className="text-sm text-[#A1A1AA] py-3">You're not in any leagues yet.</p>
                ) : (
                  <div className="space-y-2">
                    {crossLeague.map((l) => (
                      <div
                        key={l.league_id}
                        className={cn(
                          "flex items-center justify-between p-3 rounded-lg border",
                          l.owned_by_me ? "bg-[#00D2FF]/10 border-[#00D2FF]/30" :
                          l.is_free_agent ? "bg-emerald-500/5 border-emerald-500/20" :
                          "bg-[#1A1A1A] border-white/10",
                        )}
                        data-testid={`cross-league-row-${l.league_id}`}
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-white truncate">{l.league_name}</p>
                          <p className="text-xs text-[#A1A1AA] capitalize">{l.scoring_format || "—"}</p>
                        </div>
                        <div className="text-right">
                          {l.owned_by_me ? (
                            <Badge className="bg-[#00D2FF] text-black">You own</Badge>
                          ) : l.is_free_agent ? (
                            <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">Free agent</Badge>
                          ) : (
                            <>
                              <p className="text-sm text-white">{l.owned_by_team_name}</p>
                              <p className="text-[10px] text-[#A1A1AA]">{l.owned_by_owner_name}</p>
                            </>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* FANTASY TRANSACTIONS */}
          <TabsContent value="transactions">
            <Card className="border-white/10" data-testid="player-transactions">
              <CardHeader>
                <CardTitle className="text-white text-base flex items-center gap-2">
                  <ArrowRightLeft className="h-4 w-4 text-[#00D2FF]" /> Fantasy Transactions
                </CardTitle>
                <p className="text-xs text-[#A1A1AA]">{leagueId ? "Filtered to this league." : "Across all of your leagues."}</p>
              </CardHeader>
              <CardContent>
                {transactions.length === 0 ? (
                  <p className="text-sm text-[#A1A1AA] py-3">No transactions on file for this player yet.</p>
                ) : (
                  <ul className="space-y-2">
                    {transactions.map((t) => (
                      <li
                        key={t._id}
                        className="flex items-start gap-3 p-3 rounded-lg bg-[#1A1A1A] border border-white/5"
                        data-testid={`player-transaction-${t._id}`}
                      >
                        <Badge
                          variant="outline"
                          className={cn(
                            "uppercase text-[10px] tracking-wider shrink-0",
                            t.event_type === "draft_pick" ? "border-amber-500/50 text-amber-400" :
                            t.event_type === "roster_add" ? "border-emerald-500/50 text-emerald-400" :
                            t.event_type === "roster_drop" ? "border-rose-500/50 text-rose-400" :
                            t.event_type === "waiver_won" ? "border-violet-500/50 text-violet-400" :
                            "border-cyan-500/50 text-cyan-400",
                          )}
                        >
                          {t.event_type.replace("_", " ")}
                        </Badge>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-white">{t.message || t.description}</p>
                          <p className="text-xs text-[#71717A]">{formatTimeAgo(t.created_at)}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* NEWS — full history */}
          <TabsContent value="news">
            <Card className="border-white/10" data-testid="player-news-history">
              <CardHeader>
                <CardTitle className="text-white text-base flex items-center gap-2">
                  <Newspaper className="h-4 w-4 text-[#FFB020]" /> News History
                </CardTitle>
              </CardHeader>
              <CardContent>
                {news.length === 0 ? (
                  <p className="text-sm text-[#A1A1AA] py-3">No news articles on file.</p>
                ) : (
                  <ul className="space-y-3">
                    {news.map((n) => (
                      <li key={n._id} className="p-3 rounded-lg bg-[#1A1A1A] border border-white/5" data-testid={`news-item-${n._id}`}>
                        <div className="flex items-start justify-between gap-3 mb-1">
                          <p className="text-sm text-white font-semibold">{n.headline}</p>
                          <span className="text-[10px] text-[#71717A] shrink-0">{formatTimeAgo(n.published_at)}</span>
                        </div>
                        {n.summary && <p className="text-xs text-[#A1A1AA] mb-2">{n.summary}</p>}
                        <div className="flex items-center gap-3">
                          <span className="text-[11px] text-[#71717A]">{n.source || "—"}</span>
                          {n.url && (
                            <a href={n.url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-[#00D2FF] inline-flex items-center gap-1 hover:underline">
                              Read <ExternalLink className="h-3 w-3" />
                            </a>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
}
