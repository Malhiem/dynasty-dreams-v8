// @ts-nocheck
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Star, X, Search, GripVertical } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ShortlistPlayer {
  id: string;
  name: string;
  position: string;
  team: string;
  age: number;
  points: number;
}

interface PlayerShortlistProps {
  availablePlayers: ShortlistPlayer[];
  shortlist: ShortlistPlayer[];
  onAddToShortlist: (player: ShortlistPlayer) => void;
  onRemoveFromShortlist: (playerId: string) => void;
}

const positionBadgeColors: Record<string, string> = {
  C: "bg-blue-600/80 text-blue-100",
  LW: "bg-emerald-600/80 text-emerald-100",
  RW: "bg-teal-600/80 text-teal-100",
  D: "bg-amber-600/80 text-amber-100",
  G: "bg-purple-600/80 text-purple-100",
};

export function PlayerShortlist({
  availablePlayers,
  shortlist,
  onAddToShortlist,
  onRemoveFromShortlist,
}: PlayerShortlistProps) {
  const [search, setSearch] = useState("");

  const filteredPlayers = availablePlayers.filter(
    (p) =>
      !shortlist.some((s) => s.id === p.id) &&
      (p.name.toLowerCase().includes(search.toLowerCase()) ||
        p.position.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="space-y-4">
      {/* Shortlist */}
      <Card className="border-primary/20">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <Star className="h-4 w-4 text-accent" />
            My Shortlist ({shortlist.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5 max-h-[200px] overflow-y-auto">
          {shortlist.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-4">
              Add players from below to build your shortlist
            </p>
          ) : (
            shortlist.map((player, idx) => (
              <div
                key={player.id}
                className="flex items-center gap-2 p-2 rounded bg-secondary/50 group"
              >
                <GripVertical className="h-3 w-3 text-muted-foreground/50" />
                <span className="text-xs font-medium text-muted-foreground w-4">
                  {idx + 1}.
                </span>
                <Badge className={cn("text-[10px] px-1.5 py-0 h-4", positionBadgeColors[player.position])}>
                  {player.position}
                </Badge>
                <span className="text-sm flex-1 truncate">{player.name}</span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => onRemoveFromShortlist(player.id)}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {/* Available players */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Available Players</CardTitle>
          <div className="relative mt-2">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Search players..."
              className="pl-8 h-8 text-sm"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </CardHeader>
        <CardContent className="space-y-1 max-h-[300px] overflow-y-auto">
          {filteredPlayers.slice(0, 30).map((player) => (
            <div
              key={player.id}
              className="flex items-center gap-2 p-2 rounded hover:bg-secondary/50 cursor-pointer transition-colors group"
              onClick={() => onAddToShortlist(player)}
            >
              <Badge className={cn("text-[10px] px-1.5 py-0 h-4", positionBadgeColors[player.position])}>
                {player.position}
              </Badge>
              <span className="text-sm flex-1 truncate">{player.name}</span>
              <span className="text-xs text-muted-foreground">{player.team}</span>
              <span className="text-xs text-muted-foreground">{player.points} pts</span>
              <Star className="h-3 w-3 text-muted-foreground/30 group-hover:text-accent transition-colors" />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
