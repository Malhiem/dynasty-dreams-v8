// @ts-nocheck
/**
 * Iter 171 — DraftLiveTile
 *
 * Extracted from DraftRoom.tsx (right column of the header strip).
 * Three states:
 *   • Pre-start: countdown clock + two start CTAs.
 *   • Live (clock active): on-the-clock team + criteria + next team +
 *     picks-until-my-turn + pick timer + pause/simulate/undo controls.
 *   • Live (no clock / early-start): same panel minus the timer block.
 *
 * Pure presentational. Parent owns every piece of state and passes it
 * down as props; this component renders the markup + emits events.
 */
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Clock, Play, Pause, Timer, AlertCircle, RotateCcw, Volume2, VolumeX } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatCountdown, formatPickTimer } from "@/lovable/pages/draftroom/draftConstants";

export default function DraftLiveTile({
  draftConfig,
  countdown,
  onEarlyStart,
  onStartWithTimer,
  onTheClockTeamFull,
  currentRound,
  currentPickInRound,
  currentDraft,
  totalTeams,
  getTeamForPick,
  boardTeams,
  picksUntilMyTurn,
  myTeam,
  isClockActive,
  timerPaused,
  setTimerPaused,
  pickTimeLeft,
  isLeagueManager,
  handleSimulatePick,
  picks,
  undoCount,
  setUndoCount,
  handleUndoPicks,
  // Iter 172 — audio alerts (opt-in toggle + preview)
  soundsEnabled,
  onToggleSounds,
  onPreviewOnTheClock,
}) {
  return (
    <Card className="border-border bg-card/80 min-w-[320px]">
      <CardContent className="p-4 space-y-3">
        {!draftConfig.draftStarted ? (
          <>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="h-4 w-4" />
              <span>Draft starts in</span>
            </div>
            <div className="text-3xl font-mono font-bold text-primary tracking-widest text-center">
              {formatCountdown(countdown)}
            </div>
            <p className="text-[11px] text-muted-foreground text-center">
              Scheduled: {draftConfig.scheduledTime?.toLocaleString()}
            </p>
            <Button variant="ice" size="sm" className="w-full" onClick={onEarlyStart}>
              <Play className="h-3.5 w-3.5 mr-1" />
              Start Draft Early (No Clock)
            </Button>
            <Button variant="gold" size="sm" className="w-full" onClick={onStartWithTimer}>
              <Timer className="h-3.5 w-3.5 mr-1" />
              Start Draft (With Timer)
            </Button>
          </>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-sm font-semibold text-foreground">Draft Live</span>
              </div>
              <div className="flex items-center gap-1">
                {draftConfig.earlyStart && countdown > 0 && (
                  <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-400/30">
                    <AlertCircle className="h-3 w-3 mr-1" />
                    No Clock
                  </Badge>
                )}
                {typeof onToggleSounds === "function" && (
                  <>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className={cn(
                            "h-6 w-6 shrink-0",
                            soundsEnabled
                              ? "text-emerald-300 hover:text-emerald-200"
                              : "text-muted-foreground hover:text-foreground",
                          )}
                          onClick={onToggleSounds}
                          data-testid="draft-room-sounds-toggle"
                          aria-pressed={!!soundsEnabled}
                          aria-label={soundsEnabled ? "Mute draft alerts" : "Enable draft alerts"}
                        >
                          {soundsEnabled
                            ? <Volume2 className="h-3.5 w-3.5" />
                            : <VolumeX className="h-3.5 w-3.5" />}
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        {soundsEnabled
                          ? "Draft alerts ON — chime when you're next up, alarm when you're on the clock"
                          : "Draft alerts muted — click to enable"}
                      </TooltipContent>
                    </Tooltip>
                    {soundsEnabled && typeof onPreviewOnTheClock === "function" && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 shrink-0 text-muted-foreground hover:text-foreground"
                            onClick={onPreviewOnTheClock}
                            data-testid="draft-room-sounds-preview"
                            aria-label="Preview on-the-clock alert"
                          >
                            <Play className="h-3 w-3" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Preview the on-the-clock alert</TooltipContent>
                      </Tooltip>
                    )}
                  </>
                )}
              </div>
            </div>
            <div className="bg-secondary/50 rounded-lg p-3 text-center space-y-1">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">On the Clock</p>
              <p
                className="text-lg font-bold text-foreground"
                data-testid="draft-room-on-the-clock-team"
              >
                {onTheClockTeamFull?.name}
              </p>
              <p className="text-xs text-muted-foreground">
                Round {currentRound}, Pick {currentPickInRound} (#{draftConfig.currentPick} overall)
              </p>
              {currentDraft?.player_criteria && (
                <p
                  className="text-[10px] uppercase tracking-wider text-muted-foreground/70"
                  data-testid="draft-room-criteria-badge"
                >
                  Format: {currentDraft.player_criteria === "entry" ? "Entry / Rookies" : "Open · all eligible NHL players"}
                </p>
              )}
              {(() => {
                const nextOverall = draftConfig.currentPick + 1;
                const nextAbbr = nextOverall <= totalTeams * draftConfig.totalRounds
                  ? getTeamForPick(nextOverall)
                  : null;
                const nextTeam = nextAbbr ? boardTeams.find((t) => t.abbr === nextAbbr) : null;
                if (!nextTeam) return null;
                return (
                  <p
                    className="text-[11px] text-muted-foreground/90 mt-1 pt-1 border-t border-border/40"
                    data-testid="draft-room-next-on-clock"
                  >
                    <span className="uppercase tracking-wider text-muted-foreground/60 mr-1">Next:</span>
                    <span className="font-medium text-foreground/85">{nextTeam.name}</span>
                    <span className="text-muted-foreground/60"> (#{nextOverall})</span>
                  </p>
                );
              })()}
              <p
                className={cn(
                  "text-[11px] font-medium mt-1.5 pt-1.5 border-t border-border/40",
                  picksUntilMyTurn === 0 ? "text-emerald-400" : "text-primary",
                )}
                data-testid="draft-picks-until-my-turn"
              >
                {picksUntilMyTurn === null
                  ? "Picks until your turn: —"
                  : picksUntilMyTurn === 0
                  ? "You're on the clock!"
                  : `${picksUntilMyTurn} ${picksUntilMyTurn === 1 ? "pick" : "picks"} until ${myTeam?.name || "your team"}`}
              </p>
            </div>
            {isClockActive && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <Timer className="h-3 w-3" />
                    Pick Timer
                    {timerPaused && (
                      <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-400/30 ml-1">
                        Paused
                      </Badge>
                    )}
                  </span>
                  <span className={cn(
                    "font-mono font-bold text-lg",
                    timerPaused ? "text-muted-foreground" : pickTimeLeft <= 15 ? "text-destructive" : "text-primary",
                  )}>
                    {formatPickTimer(pickTimeLeft)}
                  </span>
                </div>
                <Progress value={(pickTimeLeft / draftConfig.pickTimerSeconds) * 100} className="h-1.5" />
                {isLeagueManager && (
                  <Button
                    variant={timerPaused ? "gold" : "outline"}
                    size="sm"
                    className="w-full mt-1"
                    onClick={() => setTimerPaused((prev) => !prev)}
                  >
                    {timerPaused ? (
                      <><Play className="h-3.5 w-3.5 mr-1" />Resume Timer</>
                    ) : (
                      <><Pause className="h-3.5 w-3.5 mr-1" />Pause Timer</>
                    )}
                  </Button>
                )}
                {isLeagueManager && (
                  <Button
                    variant="secondary"
                    size="sm"
                    className="w-full mt-1"
                    onClick={handleSimulatePick}
                    data-testid="draft-room-simulate-pick"
                  >
                    <Play className="h-3.5 w-3.5 mr-1" />
                    Simulate Pick
                  </Button>
                )}
                {isLeagueManager && picks.length > 0 && (
                  <div className="flex items-stretch gap-1 mt-1" data-testid="draft-room-undo-bar">
                    <Input
                      type="number"
                      min={1}
                      max={picks.length}
                      value={undoCount}
                      onChange={(e) => setUndoCount(
                        Math.max(1, Math.min(picks.length, parseInt(e.target.value || "1", 10))),
                      )}
                      data-testid="draft-room-undo-count"
                      className="h-9 w-14 text-center text-sm"
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1 gap-1.5 text-amber-400 border-amber-400/30 hover:bg-amber-400/10"
                      onClick={() => handleUndoPicks(undoCount)}
                      data-testid="draft-room-undo-pick"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      {undoCount === 1 ? "Undo Last Pick" : `Undo ${undoCount} Picks`}
                    </Button>
                  </div>
                )}
              </div>
            )}
            {draftConfig.earlyStart && countdown > 0 && (
              <p className="text-[10px] text-muted-foreground text-center">
                Clock activates in {formatCountdown(countdown)}
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
