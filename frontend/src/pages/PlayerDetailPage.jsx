import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ArrowLeft, User, Trophy, Target, TrendingUp, Shield, Zap, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import api from "@/lib/api";

const positionLabels = { C: "Center", LW: "Left Wing", RW: "Right Wing", D: "Defenseman", G: "Goalie" };
const positionColors = {
  C: "bg-blue-600 text-blue-100",
  LW: "bg-emerald-600 text-emerald-100",
  RW: "bg-teal-600 text-teal-100",
  D: "bg-amber-600 text-amber-100",
  G: "bg-purple-600 text-purple-100",
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

export default function PlayerDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [player, setPlayer] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetch = async () => {
      try {
        const { data } = await api.get(`/players/${id}`);
        setPlayer(data);
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    fetch();
  }, [id]);

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
        <button onClick={() => navigate(-1)} className="flex items-center gap-2 text-[#A1A1AA] hover:text-white">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>

        {/* Player Header */}
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
              <div className="text-right">
                <p className="text-sm text-[#A1A1AA]">Fantasy Points</p>
                <p className="text-4xl font-bold text-[#00D2FF]" data-testid="fantasy-points">
                  {((player.goals || 0) * 3 + (player.assists || 0) * 2 + (player.plus_minus || 0)).toFixed(1)}
                </p>
              </div>
            </div>
          </div>
        </Card>

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
              <StatCard icon={TrendingUp} label="+/-" value={player.plus_minus || 0} color={player.plus_minus >= 0 ? "#34C759" : "#FF3B30"} />
              <StatCard icon={Clock} label="GP" value={player.games_played || 0} color="#A1A1AA" />
            </>
          )}
        </div>

        {/* Detailed Stats */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Offensive / Primary Stats */}
          <Card className="border-white/10">
            <CardHeader><CardTitle className="text-white">{isGoalie ? "Goaltending" : "Offense"}</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              {isGoalie ? (
                <>
                  <StatBar label="Games Played" value={player.games_played || 0} max={82} />
                  <StatBar label="Games Started" value={player.games_started || 0} max={82} />
                  <StatBar label="Wins" value={player.wins || 0} max={50} />
                  <StatBar label="Losses" value={player.losses || 0} max={30} />
                  <StatBar label="OT Losses" value={player.ot_losses || 0} max={15} />
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

          {/* Special Teams / Advanced */}
          <Card className="border-white/10">
            <CardHeader><CardTitle className="text-white">{isGoalie ? "Additional" : "Special Teams & Advanced"}</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              {isGoalie ? (
                <>
                  <StatBar label="Goals" value={player.goals || 0} max={3} />
                  <StatBar label="Assists" value={player.assists || 0} max={5} />
                  <StatBar label="Penalty Minutes" value={player.penalty_minutes || 0} max={30} />
                  <StatBar label="Shots Against" value={player.shots_against || 0} max={2200} />
                  <StatBar label="Goals Against" value={player.goals_against || 0} max={200} />
                  <StatBar label="TOI (minutes)" value={player.toi_total || 0} max={4000} />
                </>
              ) : (
                <>
                  <StatBar label="Plus/Minus" value={player.plus_minus || 0} max={50} />
                  <StatBar label="Power Play Goals" value={player.power_play_goals || 0} max={25} />
                  <StatBar label="Power Play Points" value={player.power_play_points || 0} max={40} />
                  <StatBar label="Short Handed Goals" value={player.short_handed_goals || 0} max={5} />
                  <StatBar label="Short Handed Points" value={player.short_handed_points || 0} max={8} />
                  <StatBar label="Even Strength Goals" value={player.even_strength_goals || 0} max={40} />
                  <StatBar label="Game Winning Goals" value={player.game_winning_goals || 0} max={15} />
                  <StatBar label="Overtime Goals" value={player.overtime_goals || 0} max={5} />
                  <StatBar label="Penalty Minutes" value={player.penalty_minutes || 0} max={150} />
                  <StatBar label="Faceoff Win %" value={player.faceoff_win_pct || 0} max={65} suffix="%" />
                  <StatBar label="TOI/Game (min)" value={player.toi_per_game || 0} max={25} />
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppLayout>
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
