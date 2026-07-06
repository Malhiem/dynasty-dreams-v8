// Extracted from pages/DraftRoomPage.jsx (Iter 232N.35 refactor).
// Renders the sticky-header draft grid: one row per round, one column per
// team. Team headers get an "online" dot + green ring when the socket
// reports the owner as present in the room. Cells show pick number, drafted
// player initials + position badge, and a per-pick "add to trade" icon when
// trade mode is on (Iter 146).
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Repeat } from "lucide-react";
import { cn } from "@/lib/utils";

const positionColors = {
  C: "bg-blue-600/80 text-blue-100 border-blue-500/50",
  LW: "bg-emerald-600/80 text-emerald-100 border-emerald-500/50",
  RW: "bg-teal-600/80 text-teal-100 border-teal-500/50",
  D: "bg-amber-600/80 text-amber-100 border-amber-500/50",
  G: "bg-purple-600/80 text-purple-100 border-purple-500/50",
};

const teamByAbbr = (teams, abbr) => {
  if (!abbr || !teams?.length) return null;
  return teams.find((t) => (t.logo_abbr || (t.name || "").slice(0, 3).toUpperCase()) === abbr) || null;
};

export default function DraftBoardGrid({
  teams,
  teamAbbrs,
  totalTeams,
  allPicks,
  currentPick,
  onTheClockTeam,
  isActive,
  onlineUserIds,
  tradeMode,
  onAddPickToTrade,
}) {
  return (
    <Card className="border-white/10">
      <CardHeader className="pb-2">
        <CardTitle className="text-base text-white">Draft Board</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="w-full">
          <div className="min-w-[700px] p-4 pt-0">
            <div
              className="grid gap-1 mb-1 sticky top-0 bg-[#141414] z-10 pt-2"
              style={{ gridTemplateColumns: `48px repeat(${totalTeams}, minmax(72px, 1fr))` }}
            >
              <div className="p-1.5 text-[10px] font-semibold text-[#A1A1AA] uppercase">Rd</div>
              {teamAbbrs.map((abbr) => {
                const t = teamByAbbr(teams, abbr);
                const ownerOnline = !!(t?.owner_id && onlineUserIds?.has(String(t.owner_id)));
                const isOnClock = abbr === onTheClockTeam && isActive;
                return (
                  <div
                    key={abbr}
                    data-testid={`draft-team-header-${abbr}`}
                    data-online={ownerOnline ? "true" : "false"}
                    className={cn(
                      "p-1.5 text-[10px] font-semibold text-center uppercase truncate rounded border-2",
                      isOnClock
                        ? "bg-[#FFD700]/15 text-[#FFD700]"
                        : "bg-[#1A1A1A] text-[#A1A1AA] border-transparent",
                      // Iter 140 — green outline when owner is online + in room
                      ownerOnline ? "border-[#34C759]/80 shadow-[0_0_0_1px_rgba(52,199,89,0.35)]" : "",
                    )}
                  >
                    {ownerOnline && (
                      <span
                        className="inline-block h-1.5 w-1.5 rounded-full bg-[#34C759] mr-1 align-middle"
                        data-testid={`draft-team-online-dot-${abbr}`}
                      />
                    )}
                    {abbr}
                  </div>
                );
              })}
            </div>
            {allPicks.map((roundPicks, rIdx) => (
              <div
                key={rIdx + 1}
                className="grid gap-1 mb-1"
                style={{ gridTemplateColumns: `48px repeat(${totalTeams}, minmax(72px, 1fr))` }}
              >
                <div className="p-1.5 flex items-center justify-center text-[10px] font-bold text-[#A1A1AA] bg-[#1A1A1A]/30 rounded">
                  {rIdx + 1}
                </div>
                {roundPicks.map((pick) => {
                  const isCurrent = pick.overall === currentPick && isActive;
                  return (
                    <div
                      key={`${rIdx}-${pick.team}`}
                      className={cn(
                        "p-1.5 rounded border text-center min-h-[52px] flex flex-col items-center justify-center gap-0.5 transition-all relative",
                        isCurrent
                          ? "bg-[#00D2FF]/10 border-[#00D2FF]/50 ring-1 ring-[#00D2FF]/30"
                          : pick.player
                            ? "bg-[#1A1A1A]/60 border-white/10"
                            : "bg-[#0A0A0A]/50 border-white/5",
                      )}
                    >
                      <span className="text-[9px] text-[#A1A1AA]">#{pick.overall}</span>
                      {pick.player ? (
                        <>
                          <span className="text-[10px] font-medium text-white truncate w-full leading-tight">
                            {pick.player.name?.split(" ").map((n, i) => (i === 0 ? n[0] + "." : n)).join(" ")}
                          </span>
                          <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[pick.player.position] || "bg-[#1A1A1A]")}>
                            {pick.player.position}
                          </Badge>
                        </>
                      ) : (
                        <span className="text-[10px] text-[#52525B]">—</span>
                      )}
                      {/* Iter 146 — Per-pick trade button (visible only in trade mode) */}
                      {tradeMode && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onAddPickToTrade(pick.team, rIdx + 1, pick.overall, pick.player);
                          }}
                          data-testid={`draft-room-pick-trade-${pick.team}-${pick.overall}`}
                          aria-label="Add pick to trade"
                          className="absolute top-0.5 right-0.5 h-4 w-4 inline-flex items-center justify-center rounded-sm bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/30"
                        >
                          <Repeat className="h-2.5 w-2.5" />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
