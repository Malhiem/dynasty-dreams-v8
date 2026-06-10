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
  CheckCircle2, ListOrdered, Star, Trophy, MapPin, Hash, X,
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
}) {
  if (!player) {
    return (
      <Card className="border-border border-dashed bg-secondary/20" data-testid="draft-room-selected-card-empty">
        <CardContent className="py-4 px-5 flex items-center gap-3 text-sm text-muted-foreground">
          <Trophy className="h-4 w-4 text-muted-foreground/40" />
          Tap any player in the eligible list to preview their card here.
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
      className="border-primary/30 bg-gradient-to-r from-primary/5 to-transparent"
      data-testid={`draft-room-selected-card-${player.id}`}
    >
      <CardContent className="p-3 flex items-center gap-3">
        {/* Headshot — placeholder avatar with initials */}
        <div
          className={cn(
            "h-14 w-14 rounded-full flex items-center justify-center shrink-0 text-base font-bold ring-2",
            positionColors[player.position],
          )}
          data-testid="draft-room-selected-card-headshot"
          style={{ ringColor: undefined }}
        >
          {player.headshot_url ? (
            <img
              src={player.headshot_url}
              alt={player.name}
              className="h-14 w-14 rounded-full object-cover"
            />
          ) : (
            initials(player.name)
          )}
        </div>

        {/* Player meta */}
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
            <span className="text-[11px] text-muted-foreground">
              {player.age != null && `${player.age}y · `}
              {player.league || player.nhl_team || ""}
            </span>
            {adp != null && (
              <Badge
                variant="outline"
                className="text-[10px] gap-0.5"
                data-testid="draft-room-selected-card-adp"
              >
                <Hash className="h-2.5 w-2.5" />
                ADP {adp}
              </Badge>
            )}
            {player.team && (
              <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                <MapPin className="h-2.5 w-2.5" />
                {player.team}
              </span>
            )}
          </div>
          {/* Minor-league / current-league stat line */}
          <div className="flex items-center gap-3 mt-1 text-[11px]" data-testid="draft-room-selected-card-statline">
            {stats.map((s) => (
              <span key={s.label} className="tabular-nums">
                <span className="text-muted-foreground">{s.label}</span>{" "}
                <span className="text-foreground font-medium">{s.v}</span>
              </span>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            size="sm"
            variant="outline"
            className="h-8 gap-1"
            onClick={() => onToggleShortlist?.(player.id)}
            data-testid="draft-room-selected-card-shortlist"
            aria-pressed={isShortlisted}
          >
            <Star className={cn("h-3.5 w-3.5", isShortlisted && "fill-current text-accent")} />
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-8 gap-1"
            onClick={() => onToggleQueue?.(player.id)}
            data-testid="draft-room-selected-card-queue"
            aria-pressed={isQueued}
          >
            <ListOrdered className={cn("h-3.5 w-3.5", isQueued && "text-primary")} />
          </Button>
          <Button
            size="sm"
            className="h-8 gap-1.5 bg-primary hover:bg-primary/90"
            disabled={!isOnTheClock}
            onClick={() => onDraftPlayer?.(player)}
            data-testid="draft-room-selected-card-draft-btn"
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            Draft Player
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
            onClick={onClose}
            data-testid="draft-room-selected-card-close"
            aria-label="Close card"
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
