// @ts-nocheck
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

export interface DraftPick {
  round: number;
  pick: number;
  overall: number;
  team: string;
  player?: {
    name: string;
    position: string;
  };
}

interface DraftBoardProps {
  picks: DraftPick[];
  teams: string[];
  totalRounds: number;
}

const positionColors: Record<string, string> = {
  C: "bg-blue-600/80 text-blue-100 border-blue-500/50",
  LW: "bg-emerald-600/80 text-emerald-100 border-emerald-500/50",
  RW: "bg-teal-600/80 text-teal-100 border-teal-500/50",
  D: "bg-amber-600/80 text-amber-100 border-amber-500/50",
  G: "bg-purple-600/80 text-purple-100 border-purple-500/50",
};

export function DraftBoard({ picks, teams, totalRounds }: DraftBoardProps) {
  const getPickForSlot = (round: number, teamIndex: number) => {
    return picks.find(
      (p) => p.round === round && p.team === teams[teamIndex]
    );
  };

  return (
    <ScrollArea className="w-full">
      <div className="min-w-[800px]">
        {/* Header row with team names */}
        <div className="grid gap-1 mb-1" style={{ gridTemplateColumns: `60px repeat(${teams.length}, minmax(100px, 1fr))` }}>
          <div className="p-2 text-xs font-semibold text-muted-foreground uppercase">Round</div>
          {teams.map((team) => (
            <div key={team} className="p-2 text-xs font-semibold text-center text-muted-foreground uppercase truncate bg-secondary/50 rounded">
              {team}
            </div>
          ))}
        </div>

        {/* Draft grid */}
        {Array.from({ length: totalRounds }, (_, roundIdx) => {
          const round = roundIdx + 1;
          // Snake draft: odd rounds L-R, even rounds R-L
          const isSnake = round % 2 === 0;
          const orderedTeams = isSnake ? [...teams].reverse() : teams;

          return (
            <div
              key={round}
              className="grid gap-1 mb-1"
              style={{ gridTemplateColumns: `60px repeat(${teams.length}, minmax(100px, 1fr))` }}
            >
              <div className="p-2 flex items-center justify-center text-xs font-bold text-muted-foreground bg-secondary/30 rounded">
                {round}
              </div>
              {orderedTeams.map((team, idx) => {
                const displayIdx = isSnake ? teams.length - 1 - idx : idx;
                const pick = getPickForSlot(round, teams.indexOf(team));
                const overall = (round - 1) * teams.length + idx + 1;

                return (
                  <div
                    key={`${round}-${team}`}
                    className={cn(
                      "p-2 rounded border text-center min-h-[60px] flex flex-col items-center justify-center gap-1 transition-colors",
                      pick?.player
                        ? "bg-secondary/60 border-border"
                        : "bg-card/50 border-border/50 hover:border-primary/30"
                    )}
                    style={{ order: displayIdx }}
                  >
                    <span className="text-[10px] text-muted-foreground">#{overall}</span>
                    {pick?.player ? (
                      <>
                        <span className="text-xs font-medium text-foreground truncate w-full">
                          {pick.player.name}
                        </span>
                        <Badge
                          className={cn(
                            "text-[10px] px-1.5 py-0 h-4 border",
                            positionColors[pick.player.position] || "bg-muted text-muted-foreground"
                          )}
                        >
                          {pick.player.position}
                        </Badge>
                      </>
                    ) : (
                      <span className="text-[10px] text-muted-foreground/50">—</span>
                    )}
                  </div>
                );
              })}
            </div>
          );
        })}

        {/* Position legend */}
        <div className="flex items-center gap-3 mt-4 pt-3 border-t border-border">
          <span className="text-xs text-muted-foreground">Positions:</span>
          {Object.entries(positionColors).map(([pos, colorClass]) => (
            <Badge key={pos} className={cn("text-[10px] px-1.5 py-0 h-4 border", colorClass)}>
              {pos}
            </Badge>
          ))}
        </div>
      </div>
    </ScrollArea>
  );
}
