// @ts-nocheck
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Crown, Trophy, Star, Shield, Award, Medal } from "lucide-react";

const FONT_DISPLAY = `'Cinzel', 'Playfair Display', Georgia, serif`;

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

export default function TrophyRoom() {
  const { teamId } = useParams<{ teamId?: string }>();
  const navigate = useNavigate();
  const { league: activeLeague } = useActiveLeague();
  const [data, setData] = useState<TrophyData | null>(null);
  const [teamData, setTeamData] = useState<any>(null);
  const [filter, setFilter] = useState<"all" | "recent">("all");
  const [loading, setLoading] = useState(true);

  // Pull league trophy room
  useEffect(() => {
    if (!activeLeague?.id) return;
    setLoading(true);
    api.get(`/leagues/${activeLeague.id}/trophy-room`)
      .then((res) => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [activeLeague?.id]);

  // If a teamId is in the URL, pull team trophy room
  useEffect(() => {
    if (!teamId) { setTeamData(null); return; }
    api.get(`/teams/${teamId}/trophy-room`)
      .then((res) => setTeamData(res.data))
      .catch(() => setTeamData(null));
  }, [teamId]);

  const allBanners = useMemo(() => {
    if (!data) return [];
    return data.team_banners
      .flatMap(tb => tb.banners.map(b => ({ ...b, team_name: tb.team_name, team_id: tb.team_id })))
      .filter(b => filter === "all" ? true : (b.year >= (new Date().getFullYear() - 3)));
  }, [data, filter]);

  const trophies = useMemo(() => {
    if (!data) return [];
    const out: any[] = [];
    for (const s of data.seasons) {
      if (s.season_mvp) out.push({ ...s.season_mvp, _year: s.season_year });
      if (s.best_goalie) out.push({ ...s.best_goalie, _year: s.season_year });
      if (s.best_defenseman) out.push({ ...s.best_defenseman, _year: s.season_year });
    }
    return filter === "all" ? out : out.slice(0, 9);
  }, [data, filter]);

  return (
    <AppLayout>
      <div className="trophy-room" data-testid="trophy-room-page">
        {/* HEADER */}
        <div className="trophy-room-header">
          <div className="franchise-name">
            {teamData ? `${teamData.team_name} — Trophy Room` : `${activeLeague?.name || "League"} — Trophy Room`}
          </div>
          <div className="season-selector" data-testid="trophy-room-filter">
            <button onClick={() => setFilter("all")} className={`s-btn ${filter === "all" ? "active" : ""}`} data-testid="filter-all">All Time</button>
            <button onClick={() => setFilter("recent")} className={`s-btn ${filter === "recent" ? "active" : ""}`} data-testid="filter-recent">Last 3 Seasons</button>
            {teamData && (
              <button
                className="s-btn"
                onClick={() => navigate("/trophy-room")}
                data-testid="exit-team-room-btn"
              >← League Room</button>
            )}
          </div>
        </div>

        {loading && <p className="text-amber-200/50 text-center py-8">Polishing the silverware...</p>}

        {/* TEAM TROPHY ROOM (if team-specific) */}
        {!loading && teamData && (
          <>
            <div className="rafters" data-testid="team-banners-rafter">
              <div className="rafter-beam" />
              <div className="rafter-label">{teamData.team_name} Banners</div>
              <div className="banners-row">
                {teamData.banners.length === 0 && (
                  <p className="text-amber-200/40 italic text-xs">No banners hung yet — the rafters await your first championship.</p>
                )}
                {teamData.banners.map((b: BannerData, i: number) => (
                  <Banner key={i} banner={b} />
                ))}
              </div>
            </div>

            <div className="display-case">
              <div className="case-label">Individual Honors</div>
              <div className="shelf">
                {teamData.individual_awards.length === 0 && (
                  <p className="text-amber-200/40 italic text-xs px-3 py-2">Drafting future MVPs...</p>
                )}
                {teamData.individual_awards.map((a: any, i: number) => (
                  <TrophyDisplay
                    key={i}
                    trophy={{
                      label: a.label,
                      player_name: a.player_name,
                      position: a.position,
                      player_id: a.player_id,
                    }}
                    year={a.year}
                  />
                ))}
                <div className="shelf-shadow" />
              </div>
            </div>
          </>
        )}

        {/* LEAGUE TROPHY ROOM */}
        {!loading && !teamData && data && (
          <>
            <div className="rafters" data-testid="league-banners-rafter">
              <div className="rafter-beam" />
              <div className="rafter-label">Championship Banners</div>
              <div className="banners-row">
                {allBanners.length === 0 && (
                  <p className="text-amber-200/40 italic text-xs">Complete a season + crown a champion to start filling the rafters.</p>
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
                  <p className="text-amber-200/40 italic text-xs px-3 py-2">Awaiting end-of-season MVP balloting.</p>
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

      {/* Inline scoped CSS — vintage trophy room aesthetic */}
      <style>{`
        .trophy-room {
          background: radial-gradient(ellipse at top, #1a1008 0%, #0d0805 70%, #050300 100%);
          min-height: 100%;
          padding: 24px 32px 60px;
          color: #c8a060;
          font-family: ${FONT_DISPLAY};
        }
        .trophy-room-header {
          display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap;
          gap: 16px; padding-bottom: 18px;
          border-bottom: 1px solid rgba(200,160,96,0.2);
          margin-bottom: 28px;
        }
        .franchise-name {
          font-size: 28px; font-weight: 700; letter-spacing: 0.18em;
          text-transform: uppercase; color: #f0d080;
          text-shadow: 0 0 18px rgba(200,160,96,0.35), 0 1px 0 rgba(0,0,0,0.6);
        }
        .season-selector { display: inline-flex; gap: 6px; }
        .s-btn {
          background: rgba(74,56,32,0.4); border: 1px solid rgba(200,160,96,0.3);
          color: #c8a060; font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase;
          padding: 6px 14px; border-radius: 4px; cursor: pointer; transition: all 0.2s;
        }
        .s-btn:hover { background: rgba(74,56,32,0.7); }
        .s-btn.active {
          background: linear-gradient(180deg,#c8a060,#7a6040); color: #1a1008;
          font-weight: 600; box-shadow: 0 0 12px rgba(200,160,96,0.4);
        }
        .rafters {
          position: relative; margin: 30px 0 36px;
          padding: 24px 16px 32px;
        }
        .rafter-beam {
          position: absolute; top: 0; left: 0; right: 0; height: 14px;
          background: linear-gradient(180deg,#3a2510,#1a0a05,#3a2510);
          border-bottom: 2px solid #6a4020;
          box-shadow: 0 4px 12px rgba(0,0,0,0.6);
        }
        .rafter-label {
          font-size: 10px; letter-spacing: 0.3em; text-transform: uppercase;
          color: #7a6040; text-align: center; margin-top: 18px; margin-bottom: 18px;
        }
        .banners-row {
          display: flex; flex-wrap: wrap; gap: 18px; justify-content: center;
        }
        .trophy-banner {
          background: transparent; border: none; padding: 0;
          display: flex; flex-direction: column; align-items: center;
          cursor: pointer; transition: transform 0.25s ease;
          animation: bannerDrop 0.6s ease-out backwards;
        }
        .trophy-banner:hover { transform: translateY(-4px); }
        .trophy-banner:nth-child(1) { animation-delay: 0.05s; }
        .trophy-banner:nth-child(2) { animation-delay: 0.12s; }
        .trophy-banner:nth-child(3) { animation-delay: 0.18s; }
        .trophy-banner:nth-child(4) { animation-delay: 0.24s; }
        .trophy-banner:nth-child(5) { animation-delay: 0.30s; }
        .trophy-banner-rope { width: 2px; height: 14px; background: #4a3820; }
        .trophy-banner-body {
          background: var(--banner-color, #3a2510);
          color: #f0d080; padding: 14px 16px 26px; min-width: 110px; text-align: center;
          clip-path: polygon(0 0, 100% 0, 100% 86%, 50% 100%, 0 86%);
          box-shadow: 0 6px 18px rgba(0,0,0,0.55), inset 0 0 30px rgba(0,0,0,0.25);
          border: 1px solid rgba(240,208,128,0.25);
          display: flex; flex-direction: column; align-items: center; gap: 4px;
        }
        .trophy-banner-year {
          font-size: 18px; font-weight: 700; letter-spacing: 0.04em;
          color: #f0d080; text-shadow: 0 1px 0 rgba(0,0,0,0.5);
        }
        .trophy-banner-title {
          font-size: 9px; letter-spacing: 0.2em; text-transform: uppercase;
          color: #f0d080; opacity: 0.85;
        }
        .trophy-banner-detail {
          font-size: 8px; letter-spacing: 0.15em; text-transform: uppercase;
          color: #c8a060; opacity: 0.7;
        }
        .banner-with-team { display: flex; flex-direction: column; align-items: center; gap: 6px; }
        .banner-team-name {
          font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase;
          color: #c8a060; opacity: 0.7;
        }
        .display-case { margin-bottom: 36px; }
        .case-label {
          font-size: 11px; letter-spacing: 0.3em; text-transform: uppercase;
          color: #c8a060; text-align: center; padding: 8px 0;
          border-top: 1px solid rgba(200,160,96,0.18);
          border-bottom: 1px solid rgba(200,160,96,0.18);
          margin-bottom: 20px;
        }
        .shelf {
          background: linear-gradient(180deg,#2a1a0e,#1a1008);
          border-top: 2px solid #6a4020; border-bottom: 1px solid #1a1008;
          padding: 22px 18px 16px; position: relative;
          display: flex; flex-wrap: wrap; gap: 22px; justify-content: center;
        }
        .shelf-grid { gap: 26px; }
        .shelf-shadow {
          position: absolute; left: 0; right: 0; bottom: -10px; height: 10px;
          background: linear-gradient(180deg,rgba(0,0,0,0.5),transparent);
        }
        .trophy-item {
          background: transparent; border: none; cursor: pointer;
          display: flex; flex-direction: column; align-items: center; gap: 6px;
          min-width: 130px; max-width: 160px; transition: transform 0.2s;
          padding: 6px 8px;
        }
        .trophy-item:hover { transform: translateY(-3px); }
        .trophy-icon {
          position: relative;
          width: 64px; height: 64px;
          background: radial-gradient(circle at 35% 30%, #f0d080, #c8a060 50%, #7a6040 100%);
          border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          box-shadow: 0 4px 14px rgba(200,160,96,0.4), inset 0 -4px 10px rgba(0,0,0,0.3);
          border: 2px solid #6a4020;
        }
        .trophy-glow {
          position: absolute; inset: -8px;
          background: radial-gradient(circle, rgba(255,200,50,0.18), transparent 60%);
          border-radius: 50%; pointer-events: none;
        }
        .trophy-plaque {
          background: linear-gradient(180deg,#3a2510,#1a1008);
          border: 1px solid rgba(200,160,96,0.3);
          padding: 6px 10px; min-width: 110px; text-align: center;
          border-radius: 3px;
        }
        .trophy-plaque-name {
          font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase;
          color: #f0d080; font-weight: 600;
        }
        .trophy-plaque-stat {
          font-size: 11px; color: #c8a060; margin-top: 2px;
        }
        .trophy-plaque-owner {
          font-size: 8px; color: #7a6040; letter-spacing: 0.1em;
          text-transform: uppercase; margin-top: 2px;
        }
        .plaques-row {
          display: flex; flex-wrap: wrap; gap: 14px; justify-content: center;
        }
        .hall-plaque {
          background: linear-gradient(180deg,#3a2510,#1a0a05);
          border: 1px solid rgba(200,160,96,0.3);
          color: #c8a060; padding: 10px 14px; cursor: pointer;
          display: flex; gap: 12px; align-items: center; min-width: 240px;
          border-radius: 3px; box-shadow: 0 3px 10px rgba(0,0,0,0.5);
          transition: transform 0.2s, border-color 0.2s;
        }
        .hall-plaque:hover { transform: translateY(-2px); border-color: rgba(240,208,128,0.6); }
        .plaque-avatar {
          width: 38px; height: 38px; border-radius: 50%;
          background: radial-gradient(circle at 35% 30%, #f0d080, #7a6040);
          display: flex; align-items: center; justify-content: center;
          font-weight: 700; color: #1a1008; font-size: 13px; letter-spacing: 0.05em;
          box-shadow: inset 0 -3px 8px rgba(0,0,0,0.3);
        }
        .plaque-info { flex: 1; text-align: left; }
        .plaque-player {
          font-size: 13px; color: #f0d080; font-weight: 600;
          letter-spacing: 0.05em;
        }
        .plaque-seasons {
          font-size: 9px; color: #7a6040; letter-spacing: 0.12em;
          text-transform: uppercase; margin-top: 1px;
        }
        .plaque-trophies-list { margin-top: 4px; }
        .plaque-badge {
          font-size: 8px; letter-spacing: 0.18em; text-transform: uppercase;
          background: rgba(200,160,96,0.15); border: 1px solid rgba(200,160,96,0.4);
          padding: 3px 7px; color: #f0d080; border-radius: 3px;
        }
        .team-rooms-grid {
          display: grid; gap: 10px;
          grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
        }
        .team-room-card {
          background: linear-gradient(180deg,#2a1a0e,#1a1008);
          border: 1px solid rgba(200,160,96,0.25);
          padding: 14px; cursor: pointer; text-align: left;
          border-radius: 3px; color: #c8a060;
          transition: transform 0.15s, border-color 0.15s;
        }
        .team-room-card:hover {
          transform: translateY(-2px); border-color: rgba(240,208,128,0.6);
        }
        .team-room-name { font-size: 13px; color: #f0d080; font-weight: 600; }
        .team-room-banners { font-size: 10px; color: #7a6040; margin-top: 4px;
          letter-spacing: 0.1em; text-transform: uppercase; }
        @keyframes bannerDrop {
          from { transform: translateY(-30px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
      `}</style>
    </AppLayout>
  );
}
