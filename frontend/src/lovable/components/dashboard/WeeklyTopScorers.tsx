// @ts-nocheck
import { useState } from "react";
import { Flame } from "lucide-react";
import PlayerCardModal from "@/lovable/components/dashboard/PlayerCardModal";
import TeamLink from "@/lovable/components/TeamLink";

interface Scorer {
  rank: number;
  name: string;
  team: string;
  points: number;
  isUser?: boolean;
}

const weeklyScorers: Scorer[] = [
  { rank: 1, name: "Connor McDavid", team: "Team Frostbite", points: 18.4, isUser: true },
  { rank: 2, name: "Nikita Kucherov", team: "Ice Breakers", points: 16.8 },
  { rank: 3, name: "Auston Matthews", team: "Puck Dynasty", points: 15.2 },
  { rank: 4, name: "Nathan MacKinnon", team: "Frozen Assets", points: 14.6 },
  { rank: 5, name: "Cale Makar", team: "Team Frostbite", points: 13.1, isUser: true },
  { rank: 6, name: "Brady Tkachuk", team: "Hat Trick Heroes", points: 12.4 },
  { rank: 7, name: "Mitch Marner", team: "Slapshot Kings", points: 11.8 },
  { rank: 8, name: "David Pastrnak", team: "Net Ninjas", points: 11.2 },
  { rank: 9, name: "Leon Draisaitl", team: "Blue Line Bandits", points: 10.5 },
  { rank: 10, name: "Igor Shesterkin", team: "Power Play Pros", points: 9.8 },
];

const dailyScorers: Scorer[] = [
  { rank: 1, name: "Auston Matthews", team: "Puck Dynasty", points: 6.2 },
  { rank: 2, name: "Connor McDavid", team: "Team Frostbite", points: 5.8, isUser: true },
  { rank: 3, name: "Brady Tkachuk", team: "Hat Trick Heroes", points: 5.1 },
  { rank: 4, name: "Nikita Kucherov", team: "Ice Breakers", points: 4.6 },
  { rank: 5, name: "Cale Makar", team: "Team Frostbite", points: 4.2, isUser: true },
];

// Map scorer names to NHL teams & positions for the player card
const playerDetails: Record<string, { nhlTeam: string; position: string }> = {
  "Connor McDavid": { nhlTeam: "EDM", position: "C" },
  "Nikita Kucherov": { nhlTeam: "TBL", position: "RW" },
  "Auston Matthews": { nhlTeam: "TOR", position: "C" },
  "Nathan MacKinnon": { nhlTeam: "COL", position: "C" },
  "Cale Makar": { nhlTeam: "COL", position: "D" },
  "Brady Tkachuk": { nhlTeam: "OTT", position: "LW" },
  "Mitch Marner": { nhlTeam: "TOR", position: "RW" },
  "David Pastrnak": { nhlTeam: "BOS", position: "RW" },
  "Leon Draisaitl": { nhlTeam: "EDM", position: "C" },
  "Igor Shesterkin": { nhlTeam: "NYR", position: "G" },
};

function scorerToPlayer(scorer: Scorer) {
  const details = playerDetails[scorer.name] || { nhlTeam: "NHL", position: "F" };
  return {
    id: scorer.rank + 1000,
    name: scorer.name,
    position: details.position,
    team: details.nhlTeam,
    points: scorer.points,
    dynastyValue: 85,
    trend: "up" as const,
    age: 27,
    contract: { salary: 10000000, yearsRemaining: 4, type: "Signed" as const },
    rosterSection: "starting",
    statsByPeriod: { "Week 1": 12, "Week 2": 14, "Week 3": 11, "Week 4": 15, "Week 5": 13, "Week 6": 16, "Week 7": scorer.points },
    categoryBreakdown: { G: 4, A: 6, PPP: 3, SOG: 20, HIT: 5, BLK: 2, PIM: 4, "+/-": 3 },
    matchupGames: 3,
    schedule: [
      { date: "Mon", opponent: "BOS", played: true, goals: 1, assists: 1, pts: 2 },
      { date: "Wed", opponent: "NYR", played: true, goals: 0, assists: 2, pts: 2 },
      { date: "Fri", opponent: "TBL", played: false },
    ],
  };
}

const WeeklyTopScorers = () => {
  const [cardOpen, setCardOpen] = useState(false);
  const [cardPlayer, setCardPlayer] = useState<ReturnType<typeof scorerToPlayer> | null>(null);

  const handleOpenCard = (scorer: Scorer) => {
    setCardPlayer(scorerToPlayer(scorer));
    setCardOpen(true);
  };

  const renderScorer = (scorer: Scorer, i: number) => (
    <div
      key={scorer.name}
      className={`flex items-center justify-between py-1.5 px-2 rounded-md transition-colors ${
        scorer.isUser ? "bg-primary/5" : "hover:bg-secondary/30"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={`w-5 text-center text-xs font-bold ${
          i === 0 ? "text-accent" : "text-muted-foreground"
        }`}>
          {scorer.rank}
        </span>
        <div>
          <button
            onClick={() => handleOpenCard(scorer)}
            className={`text-sm font-medium hover:underline cursor-pointer text-left ${scorer.isUser ? "text-primary" : "text-foreground"}`}
          >
            {scorer.name}
          </button>
          <p className="text-xs text-muted-foreground"><TeamLink name={scorer.team} /></p>
        </div>
      </div>
      <span className="text-sm font-semibold">{scorer.points}</span>
    </div>
  );

  return (
    <div className="stat-card p-0 overflow-hidden">
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Flame className="h-4 w-4 text-accent" />
            <h3 className="text-lg font-semibold">Top Scorers</h3>
          </div>
          <span className="text-xs text-muted-foreground">Week 7</span>
        </div>
      </div>

      {/* Weekly */}
      <div className="p-3 border-b border-border/50">
        <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">Weekly</p>
        <div className="space-y-1">
          {weeklyScorers.slice(0, 5).map((scorer, i) => renderScorer(scorer, i))}
        </div>
      </div>

      {/* Daily */}
      <div className="p-3">
        <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">Today</p>
        <div className="space-y-1">
          {dailyScorers.map((scorer, i) => renderScorer(scorer, i))}
        </div>
      </div>

      {cardPlayer && (
        <PlayerCardModal
          open={cardOpen}
          onOpenChange={setCardOpen}
          player={cardPlayer}
        />
      )}
    </div>
  );
};

export default WeeklyTopScorers;
