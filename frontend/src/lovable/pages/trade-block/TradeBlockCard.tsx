// @ts-nocheck
/**
 * Iter 230 — Extracted from TradeBlock.tsx.
 *
 * Renders one tile in the Trade Block grid: player headshot/initials,
 * stats (skater vs goalie), "Looking for" badges, owner chip (with
 * theme color via TeamLogo), and the Trade/Message action buttons.
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

  return (
    <Card className="bg-card border-border hover:border-primary/30 transition-colors relative">
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
      <CardContent className="p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="h-14 w-14 rounded-lg bg-gradient-to-br from-secondary to-muted flex items-center justify-center text-sm font-bold">
              {item.type === "pick" ? "📋" : item.team}
            </div>

            <div>
              <div className="flex items-center gap-2 mb-1">
                <h3 className="font-semibold text-lg">{item.name}</h3>
                {item.trend === "up" && <TrendingUp className="h-4 w-4 text-success" />}
                {item.trend === "down" && <TrendingDown className="h-4 w-4 text-destructive" />}
                {getTypeLabel() && (
                  <Badge variant="secondary" className="text-xs">
                    {getTypeLabel()}
                  </Badge>
                )}
              </div>

              <div className="flex items-center gap-3 text-sm text-muted-foreground mb-3">
                <span>{item.position}</span>
                {item.team !== "Own" && (
                  <>
                    <span>•</span>
                    <span>{item.team}</span>
                  </>
                )}
                {item.age && (
                  <>
                    <span>•</span>
                    <span>Age {item.age}</span>
                  </>
                )}
                {item.weeklyPoints !== undefined && item.weeklyPoints > 0 && (
                  <>
                    <span>•</span>
                    <span className="text-primary">{item.weeklyPoints} pts/wk</span>
                  </>
                )}
              </div>

              {item.type === "player" && item.gp !== undefined && (
                <div className="text-xs text-muted-foreground mb-3 flex flex-wrap gap-x-3 gap-y-1">
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
                      <span>{item.ppp}PPP</span>
                      <span>{item.shp}SHP</span>
                      <span>{item.gwg}GWG</span>
                      <span>{item.sog}SOG</span>
                      <span>{item.hit}HIT</span>
                      <span>{item.blk}BLK</span>
                      <span>{item.fow}FOW</span>
                      <span>{item.fol}FOL</span>
                    </>
                  )}
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                <span className="text-xs text-muted-foreground">Looking for:</span>
                {item.lookingFor.map((req, idx) => (
                  <Badge key={idx} variant="outline" className="bg-secondary/50">
                    {req}
                  </Badge>
                ))}
              </div>
            </div>
          </div>

          <div className="flex flex-col items-end gap-3">
            <div className="flex items-center gap-2">
              {/* Iter 229k — Owner chip uses the team's saved theme_color */}
              <div data-testid={`trade-block-owner-chip-${item.id}`}>
                <TeamLogo
                  name={item.owner}
                  abbr={item.ownerAvatar}
                  themeColor={item.ownerThemeColor}
                  size="sm"
                  className="rounded-full"
                />
              </div>
              <span className="text-sm text-muted-foreground"><TeamLink name={item.owner} /></span>
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
                  <Crown className="h-4 w-4" />
                </Link>
              )}
              {streakChipData && (
                <span
                  data-testid={`trade-block-streak-chip-${item.team_id}`}
                  title={`${streakChipData.count} consecutive ${streakChipData.label === "Hot" ? "winning" : "losing"} seasons`}
                  className={`inline-flex items-center justify-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border whitespace-nowrap leading-none ${
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

            <div className="flex gap-2">
              <Button variant="outline" size="sm">
                <MessageSquare className="h-4 w-4 mr-2" />
                Message
              </Button>
              <Button
                size="sm"
                className="bg-primary hover:bg-primary/90"
                onClick={onProposeTrade}
                data-testid={`trade-block-trade-btn-${item.id}`}
                title={`Trade for ${item.name} — opens proposal pre-filled with this player`}
              >
                <ArrowRightLeft className="h-4 w-4 mr-2" />
                Trade
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default TradeBlockCard;
