// Iter 230i — "My Players" tab content extracted from TradeBlock.tsx.
// Pure presentational: receives the owner's currently-listed players
// (already filtered + decorated upstream) and renders an empty-state
// CTA or a list of cards linking back to the Roster page.
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MinorEligibleBadge } from "@/lovable/components/MinorEligibleBadge";
import type { MyOnBlockPlayer } from "./types";

type Props = {
  players: MyOnBlockPlayer[];
  myTeam: { id?: string } | null;
};

export default function MyPlayersTab({ players, myTeam }: Props) {
  return (
    <Card className="bg-card border-border">
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>My Trade-Block Players</CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            Players you&apos;ve shopped from your roster. To add or remove
            listings, use the trade-block toggle on the{" "}
            {myTeam ? (
              <Link
                to={`/teams/${myTeam.id}`}
                className="text-primary hover:underline"
                data-testid="my-players-roster-link"
              >
                Roster page
              </Link>
            ) : (
              "Roster page"
            )}
            .
          </p>
        </div>
        <Badge variant="outline" data-testid="my-players-count">
          {players.length} on block
        </Badge>
      </CardHeader>
      <CardContent>
        {players.length === 0 ? (
          <div
            className="text-center py-10 text-sm text-muted-foreground"
            data-testid="my-players-empty"
          >
            None of your players are on the trade block yet.
            <div className="mt-2">
              {myTeam && (
                <Button asChild variant="outline" size="sm">
                  <Link to={`/teams/${myTeam.id}`} data-testid="my-players-go-to-roster">
                    Go to Roster →
                  </Link>
                </Button>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {players.map((player) => (
              <div
                key={player.id}
                data-testid={`my-players-row-${player.id}`}
                className="flex items-center justify-between p-4 rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold shrink-0">
                    {player.team || player.nhl_team || "?"}
                  </div>
                  <div className="min-w-0">
                    <p className="font-medium truncate flex items-center gap-1.5">
                      {player.name}
                      <MinorEligibleBadge
                        eligible={
                          (player as any).minor_eligible ||
                          (player as any).player_type === "prospect"
                        }
                      />
                    </p>
                    <p className="text-sm text-muted-foreground flex flex-wrap items-center gap-1">
                      <span>{player.position}</span>
                      {(player.lookingFor || []).length > 0 && (
                        <>
                          <span className="text-muted-foreground/60">·</span>
                          <span className="text-xs">Looking for:</span>
                          {(player.lookingFor || []).slice(0, 3).map((r: string, i: number) => (
                            <Badge key={i} variant="secondary" className="text-[10px] py-0 px-1.5">
                              {r}
                            </Badge>
                          ))}
                        </>
                      )}
                    </p>
                  </div>
                </div>
                <Button
                  asChild
                  variant="outline"
                  size="sm"
                  data-testid={`my-players-manage-${player.id}`}
                >
                  <Link to={`/teams/${myTeam?.id}`}>Manage on Roster →</Link>
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
