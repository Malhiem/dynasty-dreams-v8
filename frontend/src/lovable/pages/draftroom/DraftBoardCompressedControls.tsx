// @ts-nocheck
/**
 * Iter 230x — DraftBoardCompressedControls
 *
 * Renders the "Compress / All rounds" toggle + the round-window
 * navigator (prev / next round, "Jump to live") for the Draft Board's
 * compressed view. Pure presentational; all state lives in
 * `DraftBoard.tsx` and is forwarded via props.
 */
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Minimize2,
} from "lucide-react";

interface Props {
  totalRounds: number;
  compressedWindow: number;
  compressed: boolean;
  setCompressed: (updater: (c: boolean) => boolean) => void;
  windowStart: number;
  windowEnd: number;
  canStepBack: boolean;
  canStepFwd: boolean;
  isFollowingLive: boolean;
  draftStarted: boolean;
  currentRound: number;
  setCenterRound: (updater: number | ((r: number) => number)) => void;
}

export default function DraftBoardCompressedControls({
  totalRounds,
  compressedWindow,
  compressed,
  setCompressed,
  windowStart,
  windowEnd,
  canStepBack,
  canStepFwd,
  isFollowingLive,
  draftStarted,
  currentRound,
  setCenterRound,
}: Props) {
  if (totalRounds <= compressedWindow) return null;
  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-6 px-2 text-[10px] uppercase tracking-wider"
            onClick={() => setCompressed((c) => !c)}
            data-testid="draft-board-compress-toggle"
            aria-pressed={compressed}
          >
            {compressed ? (
              <>
                <Maximize2 className="h-3 w-3 mr-1" /> All rounds
              </>
            ) : (
              <>
                <Minimize2 className="h-3 w-3 mr-1" /> Compress
              </>
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          {compressed
            ? `Show all ${totalRounds} rounds`
            : `Hide all but ${compressedWindow} rounds around the current pick`}
        </TooltipContent>
      </Tooltip>
      {compressed && (
        <div className="flex items-center gap-1" data-testid="draft-board-round-nav">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-6 w-6 p-0"
            disabled={!canStepBack}
            onClick={() => setCenterRound((r) => Math.max(1, r - compressedWindow))}
            data-testid="draft-board-round-prev"
            aria-label="Earlier rounds"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground tabular-nums">
            Rd {windowStart}-{windowEnd}{" "}
            <span className="opacity-60">/ {totalRounds}</span>
          </span>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-6 w-6 p-0"
            disabled={!canStepFwd}
            onClick={() => setCenterRound((r) => Math.min(totalRounds, r + compressedWindow))}
            data-testid="draft-board-round-next"
            aria-label="Later rounds"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
          {!isFollowingLive && draftStarted && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-[10px] uppercase text-primary hover:text-primary"
              onClick={() => setCenterRound(currentRound)}
              data-testid="draft-board-jump-live"
            >
              Jump to live
            </Button>
          )}
        </div>
      )}
    </>
  );
}
