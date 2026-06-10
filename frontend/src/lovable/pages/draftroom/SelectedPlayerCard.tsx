// @ts-nocheck
/**
 * Iter 152 — SelectedPlayerCard
 *
 * Inline player card shown above the Draft Board when the user clicks a
 * row in the Eligible Players list (or the Queue / Shortlist tabs).
 * Contents:
 *   • Headshot (placeholder avatar when image URL not available)
 *   • Name + position chip + age + NHL/minor-league team
 *   • Average predicted draft position (player.ranking / consensus_adp)
 *   • Stat line for their respective minor league (GP · G · A · P · +/- · PIM · SOG)
 *   • "Draft Player" button (calls onDraftPlayer prop)
 *   • "Add to Queue" / "Shortlist" mirrors
 * Component is purely presentational; parent owns selected-player state.
 */
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  CheckCircle2, ListOrdered, Star, Trophy, MapPin, Hash, X, Maximize2,
} from "lucide-react";

const positionColors = {
  C:  "bg-blue-500/20 text-blue-300 border-blue-500/30",
  LW: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  RW: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  W:  "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  D:  "bg-violet-500/20 text-violet-300 border-violet-500/30",
  G:  "bg-rose-500/20 text-rose-300 border-rose-500/30",
};

function initials(name = "") {
  return name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase() || "?";
}

export default function SelectedPlayerCard({
  player,
  isOnTheClock = false,
  isQueued = false,
  isShortlisted = false,
  onDraftPlayer,
  onToggleQueue,
  onToggleShortlist,
  onClose,
  onExpand,
}) {
  if (!player) {
    return (
      <Card className="border-border border-dashed bg-secondary/20 h-full min-h-[200px]" data-testid="draft-room-selected-card-empty">
        <CardContent className="h-full py-4 px-5 flex flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
          <Trophy className="h-6 w-6 text-muted-foreground/40" />
          <p className="text-center">Tap any player in the eligible list to preview their card here.</p>
        </CardContent>
      </Card>
    );
  }

  // Friendly stat-line — falls back gracefully when fields are absent
  const stats = [
    { label: "GP", v: player.gp },
    { label: "G", v: player.g },
    { label: "A", v: player.a },
    { label: "P", v: player.pts },
    { label: "+/-", v: player.plus_minus },
    { label: "PIM", v: player.pim },
    { label: "SOG", v: player.shots },
  ].filter((s) => s.v !== undefined && s.v !== null);

  const adp = player.adp ?? player.ranking;
  return (
    <Card
      className="border-primary/30 bg-gradient-to-r from-primary/5 to-transparent h-full min-h-[200px]"
      data-testid={`draft-room-selected-card-${player.id}`}
    >
      <CardContent className="p-4 h-full flex flex-col gap-3">
        {/* Header: headshot · name+meta · close */}
        <div className="flex items-start gap-3">
          <div
            className={cn(
              "h-16 w-16 rounded-full flex items-center justify-center shrink-0 text-lg font-bold ring-2",
              positionColors[player.position],
            )}
            data-testid="draft-room-selected-card-headshot"
          >
            {player.headshot_url ? (
              <img src={player.headshot_url} alt={player.name} className="h-16 w-16 rounded-full object-cover" />
            ) : (
              initials(player.name)
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge className={cn("text-[10px] px-1.5 py-0 h-4 border", positionColors[player.position])}>
                {player.position}
              </Badge>
              <h3
                className="text-base font-bold text-foreground truncate"
                data-testid="draft-room-selected-card-name"
              >
                {player.name}
              </h3>
              {/* Iter 153 — Inline "View full card" link opens the existing PlayerCardModal */}
              <button
                type="button"
                onClick={() => onExpand?.(player)}
                className="inline-flex items-center gap-0.5 text-[10px] text-primary hover:text-primary/80 hover:underline ml-auto"
                data-testid="draft-room-selected-card-expand"
                title="Open full player card"
              >
                <Maximize2 className="h-3 w-3" />
                View full card
              </button>
            </div>
            <div className="flex items-center gap-2 mt-1 flex-wrap text-[11px] text-muted-foreground">
              {player.age != null && <span>{player.age}y</span>}
              {player.league && <span>· {player.league}</span>}
              {player.team && (
                <span className="flex items-center gap-0.5">
                  <MapPin className="h-2.5 w-2.5" />
                  {player.team}
                </span>
              )}
              {adp != null && (
                <Badge variant="outline" className="text-[10px] gap-0.5 ml-1" data-testid="draft-room-selected-card-adp">
                  <Hash className="h-2.5 w-2.5" />
                  ADP {adp}
                </Badge>
              )}
            </div>
          </div>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground shrink-0"
            onClick={onClose}
            data-testid="draft-room-selected-card-close"
            aria-label="Close card"
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>

        {/* Stat-line — grid for vertical balance */}
        <div
          className="grid grid-cols-7 gap-1 bg-secondary/30 rounded-md p-2"
          data-testid="draft-room-selected-card-statline"
        >
          {stats.map((s) => (
            <div key={s.label} className="flex flex-col items-center">
              <span className="text-[9px] uppercase tracking-wider text-muted-foreground">{s.label}</span>
              <span className="text-sm text-foreground font-semibold tabular-nums">{s.v ?? "—"}</span>
            </div>
          ))}
        </div>

        {/* Action row — pinned to the bottom of the card */}
        <div className="flex items-center gap-1.5 mt-auto">
          <Button
            size="sm"
            variant="outline"
            className="h-8 gap-1 flex-1"
            onClick={() => onToggleShortlist?.(player.id)}
            data-testid="draft-room-selected-card-shortlist"
            aria-pressed={isShortlisted}
          >
            <Star className={cn("h-3.5 w-3.5", isShortlisted && "fill-current text-accent")} />
            <span className="text-[11px]">{isShortlisted ? "Shortlisted" : "Shortlist"}</span>
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-8 gap-1 flex-1"
            onClick={() => onToggleQueue?.(player.id)}
            data-testid="draft-room-selected-card-queue"
            aria-pressed={isQueued}
          >
            <ListOrdered className={cn("h-3.5 w-3.5", isQueued && "text-primary")} />
            <span className="text-[11px]">{isQueued ? "Queued" : "Queue"}</span>
          </Button>
          <Button
            size="sm"
            className="h-8 gap-1.5 bg-primary hover:bg-primary/90 flex-1"
            disabled={!isOnTheClock}
            onClick={() => onDraftPlayer?.(player)}
            data-testid="draft-room-selected-card-draft-btn"
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            Draft Player
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
