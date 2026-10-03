// @ts-nocheck
import { useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from "@/components/ui/tooltip";
import { FileText, ExternalLink } from "lucide-react";

/**
 * NewsSignalIcon
 *
 * Document icon + 3-bar signal-strength indicator. Click opens a small
 * in-app modal with the headline and summary (so users stay inside the
 * app); the modal includes a "Read original" link to open the source URL
 * in a new tab if the user wants to.
 *
 * Color bands:
 *   fresh  (≤ 7d)  — emerald, 3 bars
 *   stale  (7-21d) — amber,   2 bars
 *   cold   (21-35d)— rose,    1 bar
 *
 * Used on Players page (inline beside the player name) and PlayerRoster.
 */
export function NewsSignalIcon({ player }) {
  const [open, setOpen] = useState(false);
  const signal = player?.news_signal;
  if (!signal) return null;

  const palette = signal === "fresh"
    ? { color: "text-emerald-400", bars: 3, label: "Recent" }
    : signal === "stale"
      ? { color: "text-amber-300", bars: 2, label: "Aging" }
      : { color: "text-rose-400", bars: 1, label: "Stale" };
  const heights = [3, 6, 9];
  const headline = player.news_headline || "Player news";
  const summary = (player.news_summary || "").replace(/<[^>]+>/g, "").trim();
  const source = player.news_source || player.news_provider;
  const ageDays = player.news_age_days;
  const url = player.news_url;

  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); e.preventDefault(); setOpen(true); }}
              className={`inline-flex items-center gap-1 ${palette.color}`}
              data-testid={`news-signal-${player._id || player.id}`}
              aria-label={`News: ${headline}`}
            >
              <FileText className="h-3.5 w-3.5" />
              <span className="inline-flex items-end gap-[1px] h-3">
                {heights.map((h, i) => (
                  <span
                    key={i}
                    className={`w-[3px] rounded-sm ${i < palette.bars ? "bg-current" : "bg-current/25"}`}
                    style={{ height: `${h}px` }}
                  />
                ))}
              </span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="text-[11px] max-w-[280px]">
            <div className="font-semibold">{headline}</div>
            <div className="text-muted-foreground mt-1">
              {ageDays != null ? `${ageDays}d old` : ""} · {palette.label}
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md" data-testid={`news-modal-${player._id || player.id}`}>
          <DialogHeader>
            <div className="flex items-center gap-2">
              <span className={`inline-flex items-end gap-[1px] h-3 ${palette.color}`}>
                {heights.map((h, i) => (
                  <span
                    key={i}
                    className={`w-[3px] rounded-sm ${i < palette.bars ? "bg-current" : "bg-current/25"}`}
                    style={{ height: `${h}px` }}
                  />
                ))}
              </span>
              <span className={`text-[10px] uppercase tracking-wider ${palette.color}`}>{palette.label}</span>
              {ageDays != null && (
                <span className="text-[10px] text-muted-foreground">· {ageDays}d ago</span>
              )}
              {source && (
                <span className="text-[10px] text-muted-foreground ml-auto">{source}</span>
              )}
            </div>
            <DialogTitle className="text-base mt-1">{headline}</DialogTitle>
            <DialogDescription className="sr-only">
              News article preview for {player.name || "this player"}
            </DialogDescription>
          </DialogHeader>
          {summary ? (
            <p className="text-sm text-foreground/85 leading-relaxed whitespace-pre-line max-h-[300px] overflow-y-auto">
              {summary}
            </p>
          ) : (
            <p className="text-sm text-muted-foreground italic">
              No summary available — click below to read the full article on the source site.
            </p>
          )}
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-cyan-300 hover:text-cyan-200 inline-flex items-center gap-1 mt-2"
              data-testid={`news-modal-source-${player._id || player.id}`}
            >
              Read original <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
