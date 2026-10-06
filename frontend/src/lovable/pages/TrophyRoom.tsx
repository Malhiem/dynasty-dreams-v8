// @ts-nocheck
import "./trophy-room/TrophyRoom.css";
import FranchiseRecords from "./trophy-room/FranchiseRecords";
import { seasonPlayerAwards } from "./history/awardRecords";
import { useHistoryRequest } from "./history/useHistoryRequest";
import { HistoryStatus, FilteredAwardsEmpty } from "./history/HistoryStatus";
import { useCallback, useMemo, useState } from "react";
import { recordedSeasonYears, selectSeasonYears } from "./trophy-room/seasonFilters";
import { useNavigate, useParams } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Crown, Trophy, Star, Shield, Award, Medal, Zap, TurtleIcon, RefreshCw, Handshake, ListChecks } from "lucide-react";


const BANNER_COLOR: Record<string, string> = {
  championship: "#8B0000",        // dark red
  presidents_trophy: "#7a4f0a",   // bronze
  conference: "#0a1a3a",          // dark navy
  division: "#1a4220",            // forest green
  consolation: "#3a2510",         // brown
};

const BANNER_TITLE: Record<string, string> = {
  championship: "Champions",
  presidents_trophy: "President's Trophy",
  conference: "Conference Champ",
  division: "Division Champ",
  consolation: "Consolation Cup",
};

const BANNER_ICON: Record<string, any> = {
  championship: Crown,
  presidents_trophy: Star,
  conference: Trophy,
  division: Shield,
  consolation: Medal,
};

const TROPHY_ICON: Record<string, any> = {
  "Season MVP": Star,
  "Best Goalie": Shield,
  "Best Defenseman": Award,
};

interface BannerData {
  type: string;
  year: number;
  division?: string;
  conference?: string;
}

interface TrophyData {
  league_id: string;
  seasons: any[];
  team_banners: { team_id: string; team_name: string; logo_url?: string; banners: BannerData[] }[];
  hall_of_fame: any[];
}

const Banner = ({ banner, onClick }: { banner: BannerData; onClick?: () => void }) => {
  const color = BANNER_COLOR[banner.type] || "#3a2510";
  const Icon = BANNER_ICON[banner.type] || Trophy;
  const title = BANNER_TITLE[banner.type] || banner.type;
  const detail = banner.division || banner.conference || "";
  return (
    <button
      type="button"
      onClick={onClick}
      className="trophy-banner group"
      style={{ "--banner-color": color } as any}
      data-testid={`trophy-banner-${banner.type}-${banner.year}`}
      aria-label={`${title} ${banner.year}`}
    >
      <div className="trophy-banner-rope" />
      <div className="trophy-banner-body">
        <Icon className="h-5 w-5 text-amber-200" strokeWidth={1.5} />
        <div className="trophy-banner-year">{banner.year}</div>
        <div className="trophy-banner-title">{title}</div>
        {detail && <div className="trophy-banner-detail">{detail}</div>}
      </div>
    </button>
  );
};

const TrophyDisplay = ({ trophy, year }: { trophy: any; year?: number | string }) => {
  if (!trophy) return null;
  const Icon = TROPHY_ICON[trophy.label] || Trophy;
  const navigate = useNavigate();
  const slug = (trophy.label || "").toLowerCase().replace(/\s+/g, "-");
  return (
    <button
      type="button"
      className="trophy-item group"
      onClick={() => trophy.player_id && navigate(`/players/${trophy.player_id}`)}
      data-testid={`trophy-item-${slug}${year ? `-${year}` : ""}`}
    >
      <div className="trophy-icon">
        <Icon className="h-7 w-7 text-amber-300" strokeWidth={1.5} />
        <div className="trophy-glow" />
      </div>
      <div className="trophy-plaque">
        <div className="trophy-plaque-name">{trophy.label}{year ? ` · ${year}` : ""}</div>
        <div className="trophy-plaque-stat">
          {trophy.player_name}{trophy.position ? ` · ${trophy.position}` : ""}
          {trophy.scoring_basis === "legacy_estimate" && <span> · Legacy score estimate</span>}
        </div>
        {trophy.owner_team_name && (
          <div className="trophy-plaque-owner">on {trophy.owner_team_name}</div>
        )}
      </div>
    </button>
  );
};

const HallPlaque = ({ legend }: { legend: any }) => {
  const initials = (legend.player_name || "?")
    .split(" ").slice(0, 2).map((p: string) => p[0]).join("").toUpperCase();
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => legend.player_id && navigate(`/players/${legend.player_id}`)}
      className="hall-plaque"
      data-testid={`hall-plaque-${legend.player_id}`}
    >
      <div className="plaque-avatar">{initials}</div>
      <div className="plaque-info">
        <div className="plaque-player">{legend.player_name}</div>
        <div className="plaque-seasons">
          {legend.position} · {legend.trophies?.length || 0} {legend.trophies?.length === 1 ? "trophy" : "trophies"}
        </div>
        <div className="plaque-trophies-list">
          {(legend.trophies || []).slice(0, 3).map((t: any, i: number) => (
            <span key={i} className="text-[9px] uppercase tracking-wider text-amber-300/80">
              {t.label} {t.year}
              {i < Math.min((legend.trophies || []).length, 3) - 1 ? " · " : ""}
            </span>
          ))}
        </div>
      </div>
      <div className="plaque-badge">Legend</div>
    </button>
  );
};

// Iter 232N.28 — Vintage-styled card summarising a single completed
// draft's leaderboard. Lives inside the Trophy Room's Draft Hall of
// Awards display case. Icons + captions mirror <DraftLeaderboard/>
// so the two surfaces feel like one product.
const DRAFT_AWARD_ROWS: Array<{ id: string; label: string; icon: any }> = [
  { id: "speed_demon", label: "Speed Demon", icon: Zap },
  { id: "slow_poke", label: "Slow-Poke", icon: TurtleIcon },
  { id: "autopilot", label: "Auto-Pilot", icon: RefreshCw },
  { id: "wheeler_dealer", label: "Wheeler-Dealer", icon: Handshake },
  { id: "iron_man", label: "Iron Man", icon: ListChecks },
  { id: "queue_master", label: "Queue Master", icon: Star },
];

const DraftAwardCard = ({ entry }: { entry: any }) => {
  const awards = entry?.awards || {};
  return (
    <div className="draft-award-card" data-testid={`draft-award-card-${entry.draft_id}`}>
      <div className="draft-award-header">
        <span className="draft-award-year">{entry.year ?? "—"}</span>
        <span className="draft-award-name">{entry.name}</span>
      </div>
      <div className="draft-award-meta">
        {entry.total_picks} picks · {entry.auto_picks_total} auto
      </div>
      <div className="draft-award-rows">
        {DRAFT_AWARD_ROWS.map(({ id, label, icon: Icon }) => {
          const winner = awards[id];
          return (
            <div
              key={id}
              className="draft-award-row"
              data-testid={`draft-award-row-${entry.draft_id}-${id}`}
            >
              <Icon size={12} className="draft-award-icon" />
              <span className="draft-award-label">{label}</span>
              <span className="draft-award-winner">
                {winner ? winner.team_name : "—"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};


export default function TrophyRoom() {
  const { teamId } = useParams<{ teamId?: string }>();
  const { league: activeLeague } = useActiveLeague();
  return (
    <AppLayout>
      <TrophyRoomView leagueId={activeLeague?.id} teamId={teamId} leagueName={activeLeague?.name} />
    </AppLayout>
  );
}

export function TrophyRoomView({
  leagueId,
  teamId,
  leagueName,
  embedded = false,
}: {
  leagueId?: string | null;
  teamId?: string | null;
  leagueName?: string | null;
  embedded?: boolean;
}) {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<"all" | "recent">("all");
  // Iter 232N.84 — Multi-season filter. `null` = every year, otherwise
  // clamp banners + trophies to just the picked season year.
  const [yearFilter, setYearFilter] = useState<number | null>(null);
  const loadLeague = useCallback((signal: AbortSignal) => api.get(`/leagues/${leagueId}/trophy-room`, {signal}).then(res => res.data), [leagueId]);
  const loadTeam = useCallback((signal: AbortSignal) => api.get(`/teams/${teamId}/trophy-room`, {signal}).then(res => res.data), [teamId]);
  const loadDrafts = useCallback((signal: AbortSignal) => api.get(`/leagues/${leagueId}/draft-hall-of-awards`, {signal}).then(res => res.data?.drafts || []), [leagueId]);
  const leagueRequest = useHistoryRequest<TrophyData>(leagueId || null, loadLeague);
  const teamRequest = useHistoryRequest<any>(leagueId && teamId ? `${leagueId}:${teamId}` : null, loadTeam);
  const draftRequest = useHistoryRequest<any[]>(leagueId && !teamId ? leagueId : null, loadDrafts);
  const data = leagueRequest.data;
  const teamData = teamRequest.data;
  const hallOfAwards = draftRequest.data || [];
  const loading = leagueRequest.loading || teamRequest.loading;
  const error = leagueRequest.error || teamRequest.error;
  const retry = () => {leagueRequest.retry(); teamRequest.retry();};
  const filtersActive = filter !== "all" || yearFilter !== null;
  const resetFilters = () => {setFilter("all"); setYearFilter(null);};

  const availableYears = useMemo(() => recordedSeasonYears(data), [data]);
  const visibleYears = useMemo(() => selectSeasonYears(availableYears, filter === "recent", yearFilter), [availableYears, filter, yearFilter]);
  const allBanners = useMemo(() => data?.team_banners
    .flatMap(tb => tb.banners.map(b => ({ ...b, team_name: tb.team_name, team_id: tb.team_id })))
    .filter(b => visibleYears.has(Number(b.year))) || [], [data, visibleYears]);
  const teamBanners = (teamData?.banners || []).filter((b: BannerData) => visibleYears.has(Number(b.year)));
  const teamHonors = (teamData?.individual_awards || []).filter((a: any) => visibleYears.has(Number(a.year)));

  const trophies = useMemo(() => {
    if (!data) return [];
    const out: any[] = [];
    for (const s of data.seasons) {
      if (!visibleYears.has(Number(s.season_year))) continue;
      for (const award of seasonPlayerAwards(s)) out.push({...award, _year: s.season_year});
    }
    return out;
  }, [data, visibleYears]);

  return (
    <>
    <div className="trophy-room" data-testid="trophy-room-page">
        {data?.seasons?.some((s: any) => s.champion_status === "ambiguous") && <p role="alert">Some older championship records have ambiguous franchise names. No champion has been assigned to those records.</p>}
        {/* HEADER */}
        <div className="trophy-room-header">
          <div className="franchise-name">
            {teamData ? `${teamData.team_name} — Trophy Room` : `${leagueName || "League"} — Trophy Room`}
          </div>
          <div className="season-selector" data-testid="trophy-room-filter">
            <button onClick={() => setFilter("all")} className={`s-btn ${filter === "all" ? "active" : ""}`} data-testid="filter-all">All Time</button>
            <button onClick={() => setFilter("recent")} className={`s-btn ${filter === "recent" ? "active" : ""}`} data-testid="filter-recent">Last 3 Seasons</button>
            {/* Iter 232N.84 — Season year picker (visible when we've
                actually got multi-year history to switch between). */}
            {availableYears.length > 1 && (
              <select
                value={yearFilter == null ? "all" : String(yearFilter)}
                onChange={(e) => setYearFilter(e.target.value === "all" ? null : Number(e.target.value))}
                className="s-btn"
                style={{ appearance: "auto" }}
                data-testid="trophy-room-year-filter"
                aria-label="Filter by season year"
              >
                <option value="all">All years</option>
                {availableYears.map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            )}
            {teamData && !embedded && (
              <button
                className="s-btn"
                onClick={() => navigate("/trophy-room")}
                data-testid="exit-team-room-btn"
              >← League Room</button>
            )}
          </div>
        </div>

        {!leagueId && <p role="status">Select a league to view its history.</p>}
        <HistoryStatus loading={loading} error={error} retry={retry} />

        {teamData?.historical_franchise && !loading && !error && <p className="text-center text-xs py-2">Archived franchise — showing saved season history.</p>}
        {/* TEAM TROPHY ROOM (if team-specific) */}
        {!loading && !error && teamData && (
          <>
            <div className="rafters" data-testid="team-banners-rafter">
              <div className="rafter-beam" />
              <div className="rafter-label">{teamData.team_name} Banners</div>
              <div className="banners-row">
                {teamBanners.length === 0 && (
                  <FilteredAwardsEmpty active={filtersActive} reset={resetFilters} fallback="No banners hung yet — the rafters await your first championship." />
                )}
                {teamBanners.map((b: BannerData, i: number) => (
                  <Banner key={i} banner={b} />
                ))}
              </div>
            </div>

            <div className="display-case">
              <div className="case-label">Individual Honors</div>
              <div className="shelf">
                {teamHonors.length === 0 && (
                  <FilteredAwardsEmpty active={filtersActive} reset={resetFilters} fallback="Drafting future MVPs..." />
                )}
                {teamHonors.map((a: any, i: number) => (
                  <TrophyDisplay
                    key={i}
                    trophy={{
                      label: a.label,
                      player_name: a.player_name,
                      position: a.position,
                      player_id: a.player_id,
                      scoring_basis: a.scoring_basis,
                    }}
                    year={a.year}
                  />
                ))}
                <div className="shelf-shadow" />
              </div>
            </div>
            <FranchiseRecords seasons={teamData.seasons_played || []} visibleYears={visibleYears} />
          </>
        )}

        {/* LEAGUE TROPHY ROOM */}
        {!loading && !error && !teamId && data && (
          <>
            <div className="rafters" data-testid="league-banners-rafter">
              <div className="rafter-beam" />
              <div className="rafter-label">Championship Banners</div>
              <div className="banners-row">
                {allBanners.length === 0 && (
                  <FilteredAwardsEmpty active={filtersActive} reset={resetFilters} fallback="Complete a season + crown a champion to start filling the rafters." />
                )}
                {allBanners.map((b: any, i: number) => (
                  <div key={`${b.team_id}-${b.year}-${b.type}-${i}`} className="banner-with-team">
                    <Banner banner={b} onClick={() => b.team_id && navigate(`/trophy-room/team/${b.team_id}`)} />
                    <span className="banner-team-name">{b.team_name}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="display-case">
              <div className="case-label">Individual Trophies</div>
              <div className="shelf shelf-grid">
                {trophies.length === 0 && (
                  <FilteredAwardsEmpty active={filtersActive} reset={resetFilters} fallback="Awaiting end-of-season MVP balloting." />
                )}
                {trophies.map((t, i) => (
                  <TrophyDisplay key={i} trophy={t} year={t._year} />
                ))}
                <div className="shelf-shadow" />
              </div>
            </div>

            <div className="display-case">
              <div className="case-label">Hall of Fame</div>
              <div className="plaques-row">
                {data.hall_of_fame.length === 0 && (
                  <p className="text-amber-200/40 italic text-xs">Hall of Fame opens after a few seasons of trophies.</p>
                )}
                {data.hall_of_fame.map((legend, i) => (
                  <HallPlaque key={i} legend={legend} />
                ))}
              </div>
            </div>

            {/* Iter 232N.28 — Draft Hall of Awards.
                Archives every completed draft's leaderboard so managers
                can revisit past seasons' trash talk. Rendered only in
                the LEAGUE view (not team-specific) and only when at
                least one completed draft exists. */}
            <div className="display-case" data-testid="draft-hall-of-awards">
              <div className="case-label">Draft Hall of Awards</div>
              {draftRequest.loading || draftRequest.error ? <HistoryStatus loading={draftRequest.loading} error={draftRequest.error} retry={draftRequest.retry} /> : hallOfAwards.length === 0 ? (
                <p className="text-amber-200/40 italic text-xs px-3 py-2">
                  Complete a draft to enshrine your first Speed Demon and Slow-Poke.
                </p>
              ) : (
                <div className="hall-of-awards-grid" data-testid="hall-of-awards-grid">
                  {hallOfAwards.map((entry) => (
                    <DraftAwardCard key={entry.draft_id} entry={entry} />
                  ))}
                </div>
              )}
            </div>

            {/* Per-team grid for "visit team trophy rooms" */}
            <div className="display-case">
              <div className="case-label">Team Trophy Rooms</div>
              <div className="team-rooms-grid" data-testid="team-rooms-grid">
                {data.team_banners.map((tb) => (
                  <button
                    key={tb.team_id}
                    onClick={() => navigate(`/trophy-room/team/${tb.team_id}`)}
                    className="team-room-card"
                    data-testid={`team-room-card-${tb.team_id}`}
                  >
                    <div className="team-room-name">{tb.team_name}</div>
                    <div className="team-room-banners">{tb.banners.length} banner{tb.banners.length === 1 ? "" : "s"}</div>
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      </div>


    </>
  );
}
