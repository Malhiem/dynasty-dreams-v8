// @ts-nocheck
/**
 * Iter 230 — Extracted from TradeBlock.tsx.
 * Iter 230ao — Rebuilt layout to stop content overflowing the tile.
 *
 * Previous layout was a 2-column flex with the player block on the
 * left and the owner chip + actions on the right. On narrower viewports
 * (sm:grid-cols-2 → ~440px tiles) the long player names + multi-word
 * owner names ("Zarek's Frozen") pushed the right column off the tile
 * AND wrapped the "Looking for" badges below their stat row.
 *
 * Now: vertical stack — header row (name + type badge + close X),
 * owner row, stats row, looking-for chips, then action buttons. Every
 * text node uses `truncate` / `min-w-0` so long names ellipsize
 * cleanly rather than busting layout.
 */
import { Link } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ArrowRightLeft, MessageSquare, TrendingUp, TrendingDown, Crown, X,
} from "lucide-react";
import TeamLink from "@/lovable/components/TeamLink";
import TeamLogo from "@/lovable/components/TeamLogo";
import ReportUserButton from "@/components/ReportUserButton";

const TradeBlockCard = ({ item, onProposeTrade, onHide, streakChipData }) => {
  const getTypeLabel = () => {
    if (item.type === "prospect") return "Prospect";
    if (item.type === "pick") return "Draft Pick";
    return null;
  };

  // Iter 231 — Player thumbnail fallback. Previously the 12x12 box just
  // rendered `item.team` (NHL team abbr), which left an empty square
  // when a roster's `nhl_team` was unset. Now we derive initials from
  // the player name if no team abbr is available so the tile always
  // has a legible glyph.
  const playerInitials = (item.name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  const thumbContent =
    item.type === "pick"
      ? "📋"
      : (item.team && item.team !== "Own" ? item.team : playerInitials || "—");

  return (
    <Card className="bg-card border-border hover:border-primary/30 transition-colors relative overflow-hidden">
      {onHide && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onHide(); }}
          className="absolute top-2 right-2 z-10 h-6 w-6 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-secondary flex items-center justify-center transition-colors"
          title="Hide this player from the Trade Block"
          aria-label="Hide from Trade Block"
          data-testid={`trade-block-hide-${item.id}`}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
      <CardContent className="p-5 space-y-4">
        {/* Player header */}
        <div className="flex items-start gap-3 min-w-0 pr-7">
          <div
            className="h-12 w-12 shrink-0 rounded-lg bg-gradient-to-br from-secondary to-muted flex items-center justify-center text-xs font-bold"
            data-testid={`trade-block-thumb-${item.id}`}
            title={item.name}
          >
            {thumbContent}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 mb-1 min-w-0">
              <h3 className="font-semibold text-base truncate" title={item.name}>{item.name}</h3>
              {item.trend === "up" && <TrendingUp className="h-3.5 w-3.5 text-success shrink-0" />}
              {item.trend === "down" && <TrendingDown className="h-3.5 w-3.5 text-destructive shrink-0" />}
              {getTypeLabel() && (
                <Badge variant="secondary" className="text-[10px] shrink-0">
                  {getTypeLabel()}
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground truncate">
              <span>{item.position}</span>
              {item.team && item.team !== "Own" && (
                <>
                  <span>·</span>
                  <span className="truncate">{item.team}</span>
                </>
              )}
              {item.age && (
                <>
                  <span>·</span>
                  <span className="shrink-0">Age {item.age}</span>
                </>
              )}
              {item.weeklyPoints !== undefined && item.weeklyPoints > 0 && (
                <>
                  <span>·</span>
                  <span className="text-primary shrink-0">{item.weeklyPoints} pts/wk</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Owner chip row */}
        <div className="flex items-center gap-2 min-w-0">
          {/* Iter 229k — Owner chip uses the team's saved theme_color */}
          <div data-testid={`trade-block-owner-chip-${item.id}`} className="shrink-0">
            <TeamLogo
              name={item.owner}
              abbr={item.ownerAvatar}
              themeColor={item.ownerThemeColor}
              size="sm"
              className="rounded-full"
            />
          </div>
          <span className="text-xs text-muted-foreground truncate min-w-0 flex-1">
            <TeamLink name={item.owner} />
          </span>
          <div className="flex items-center gap-1 shrink-0">
            {item.owner_id && (
              <ReportUserButton
                targetUserId={item.owner_id}
                targetUserEmail={item.owner}
                targetTeamId={item.team_id}
                contextUrl={`/trade-block#item-${item.id}`}
              />
            )}
            {item.team_id && (
              <Link
                to={`/trophy-room/team/${item.team_id}`}
                title={`${item.owner} trophy room`}
                data-testid={`trade-block-trophy-link-${item.team_id}`}
                className="text-amber-400/70 hover:text-amber-300 inline-flex"
              >
                <Crown className="h-3.5 w-3.5" />
              </Link>
            )}
            {streakChipData && (
              <span
                data-testid={`trade-block-streak-chip-${item.team_id}`}
                title={`${streakChipData.count} consecutive ${streakChipData.label === "Hot" ? "winning" : "losing"} seasons`}
                className={`inline-flex items-center justify-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full border whitespace-nowrap leading-none ${
                  streakChipData.tone === "hot"
                    ? "bg-orange-500/20 text-orange-300 border-orange-400/40"
                    : "bg-sky-500/20 text-sky-200 border-sky-400/40"
                }`}
              >
                <span aria-hidden="true">{streakChipData.emoji}</span>
                <span>{streakChipData.label}</span>
                <span className="tabular-nums">{streakChipData.count}</span>
              </span>
            )}
          </div>
        </div>

        {/* Stats row (skater vs goalie) */}
        {item.type === "player" && item.gp !== undefined && (
          <div className="text-[11px] text-muted-foreground flex flex-wrap gap-x-2.5 gap-y-1">
            {item.position === "G" ? (
              <>
                <span>GP {item.gp}</span>
                <span>{item.w}W</span>
                <span>{item.l}L</span>
                <span>{item.sol}SOL</span>
                <span>{item.sv}SV</span>
                <span>{item.ga}GA</span>
                <span>{item.so}SO</span>
              </>
            ) : (
              <>
                <span>GP {item.gp}</span>
                <span>{item.g}G</span>
                <span>{item.a}A</span>
                <span>{(item.plusMinus ?? 0) >= 0 ? '+' : ''}{item.plusMinus}</span>
                <span>{item.sog}SOG</span>
              </>
            )}
          </div>
        )}

        {/* Looking for chips */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-muted-foreground shrink-0">Looking for:</span>
          {(item.lookingFor || []).map((req, idx) => (
            <Badge key={idx} variant="outline" className="bg-secondary/50 text-[10px] py-0">
              {req}
            </Badge>
          ))}
        </div>

        {/* Action buttons */}
        <div className="flex gap-2 pt-1">
          <Button variant="outline" size="sm" className="flex-1">
            <MessageSquare className="h-3.5 w-3.5 mr-1.5" />
            Message
          </Button>
          <Button
            size="sm"
            className="bg-primary hover:bg-primary/90 flex-1"
            onClick={onProposeTrade}
            data-testid={`trade-block-trade-btn-${item.id}`}
            title={`Trade for ${item.name} — opens proposal pre-filled with this player`}
          >
            <ArrowRightLeft className="h-3.5 w-3.5 mr-1.5" />
            Trade
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

export default TradeBlockCard;
