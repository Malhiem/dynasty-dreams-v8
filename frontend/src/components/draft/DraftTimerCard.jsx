// Extracted from pages/DraftRoomPage.jsx (Iter 232N.35 refactor).
// Renders the "Draft Live" timer card — the on-clock badge, main pick timer,
// personal timer tile (Iter 232N.26), and per-user auto-pick preference
// selector. Also handles the pre-draft "Start Draft" buttons and the
// post-draft "Complete!" message.
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Clock, Play, Pause, Timer, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import TeamLogo from "@/lovable/components/TeamLogo";

function formatPickTimer(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function DraftTimerCard({
  draft,
  teams,
  onTheClockTeam,
  onTheClockTeamObj,
  currentRound,
  currentPickInRound,
  currentPick,
  pickTimeLeft,
  personalTimeLeft,
  timerPaused,
  picks,
  myTeam,
  autoPickPref,
  savingAutoPickPref,
  onStartDraft,
  onPauseTimer,
  onSaveAutoPickPref,
}) {
  const isStarted = draft?.draft_started;
  const isEarlyStart = draft?.early_start;
  return (
    <Card className="border-white/10 bg-[#141414] min-w-[320px]">
      <CardContent className="p-4 space-y-3">
        {!isStarted ? (
          <>
            <p className="text-sm text-[#A1A1AA] flex items-center gap-2"><Clock className="h-4 w-4" /> Draft not started</p>
            <Button size="sm" className="w-full bg-[#00D2FF] text-black hover:bg-[#33DBFF]" onClick={() => onStartDraft(true)} data-testid="start-draft-early">
              <Play className="h-3.5 w-3.5 mr-1" /> Start Draft (No Clock)
            </Button>
            <Button size="sm" variant="outline" className="w-full border-white/10 text-white" onClick={() => onStartDraft(false)} data-testid="start-draft-timer">
              <Timer className="h-3.5 w-3.5 mr-1" /> Start Draft (With Timer)
            </Button>
          </>
        ) : draft.status === "completed" ? (
          <div className="text-center py-4">
            <p className="text-lg font-bold text-[#34C759]">Draft Complete!</p>
            <p className="text-sm text-[#A1A1AA]">All {picks.length} picks have been made</p>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-[#34C759] animate-pulse" />
              <span className="text-sm font-semibold text-white">Draft Live</span>
              {isEarlyStart && (
                <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-400/30">
                  <AlertCircle className="h-3 w-3 mr-1" />No Clock
                </Badge>
              )}
            </div>
            <div className="bg-[#1A1A1A] rounded-lg p-3 text-center space-y-1">
              <p className="text-[10px] uppercase tracking-wider text-[#A1A1AA]">On the Clock</p>
              <div className="flex items-center justify-center gap-2">
                <TeamLogo
                  logo={onTheClockTeamObj?.logo_url}
                  name={onTheClockTeamObj?.name || onTheClockTeam}
                  abbr={onTheClockTeam}
                  size="sm"
                />
                <p className="text-lg font-bold text-white" data-testid="on-the-clock">
                  {onTheClockTeamObj?.name || onTheClockTeam}
                </p>
              </div>
              <p className="text-xs text-[#A1A1AA]">
                Round {currentRound}, Pick {currentPickInRound} (#{currentPick} overall)
              </p>
            </div>
            {!isEarlyStart && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[#A1A1AA] flex items-center gap-1"><Timer className="h-3 w-3" />Pick Timer</span>
                  <span className={cn(
                    "font-mono font-bold text-lg",
                    timerPaused ? "text-[#A1A1AA]" : pickTimeLeft <= 15 ? "text-[#FF3B30]" : "text-[#00D2FF]",
                  )}>
                    {formatPickTimer(pickTimeLeft)}
                  </span>
                </div>
                <Progress value={(pickTimeLeft / (draft.time_per_pick || 120)) * 100} className="h-1.5" />
                {/* Iter 232N.26 — Personal timer tile. Rendered only when
                    the league has a personal cap AND that cap is TIGHTER
                    than the main clock (otherwise it never fires first). */}
                {draft.personal_pick_timer_seconds
                  && draft.personal_pick_timer_seconds < (draft.time_per_pick || 120) && (
                  <div className="mt-2 rounded-md border border-white/10 bg-black/30 p-2" data-testid="personal-timer-tile">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-[#A1A1AA] flex items-center gap-1">
                        <AlertCircle className="h-3 w-3 text-amber-400" />
                        Personal Timer
                      </span>
                      <span
                        className={cn(
                          "font-mono font-bold text-sm",
                          timerPaused
                            ? "text-[#A1A1AA]"
                            : personalTimeLeft <= 15
                              ? "text-[#FF3B30]"
                              : "text-amber-300",
                        )}
                        data-testid="personal-timer-value"
                      >
                        {formatPickTimer(personalTimeLeft)}
                      </span>
                    </div>
                    <Progress
                      value={(personalTimeLeft / draft.personal_pick_timer_seconds) * 100}
                      className="h-1 mt-1.5"
                    />
                    <p className="text-[10px] text-[#A1A1AA] mt-1.5 italic">
                      Auto-pick fires when this runs out — even if the main clock still has time.
                    </p>
                  </div>
                )}
                {/* Iter 232N.26 — My auto-pick fallback selector. Only
                    visible when the user actually owns a team in this
                    league. Persists to the team model. */}
                {myTeam?.id && (
                  <div className="mt-2 rounded-md border border-white/10 bg-black/20 p-2" data-testid="auto-pick-pref-block">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] uppercase tracking-wider text-[#A1A1AA]">
                        My auto-pick fallback
                      </span>
                      {savingAutoPickPref && (
                        <span className="text-[10px] text-[#00D2FF]">saving…</span>
                      )}
                    </div>
                    <Select value={autoPickPref} onValueChange={onSaveAutoPickPref}>
                      <SelectTrigger
                        className="mt-1 h-8 bg-[#1A1A1A] border-white/10 text-xs"
                        data-testid="auto-pick-pref-select"
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="queue_then_best" data-testid="auto-pick-pref-queue">
                          From my draft queue (fall back to best)
                        </SelectItem>
                        <SelectItem value="best_available" data-testid="auto-pick-pref-best">
                          Best available (skip my queue)
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
                <Button
                  variant={timerPaused ? "default" : "outline"}
                  size="sm"
                  className="w-full mt-1"
                  onClick={onPauseTimer}
                  data-testid="pause-timer"
                >
                  {timerPaused
                    ? <><Play className="h-3.5 w-3.5 mr-1" />Resume</>
                    : <><Pause className="h-3.5 w-3.5 mr-1" />Pause</>}
                </Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
