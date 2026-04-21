// @ts-nocheck
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowRightLeft } from "lucide-react";
import TeamLink from "@/lovable/components/TeamLink";

const tradeBlockPlayers = [
  {
    name: "Connor McDavid", team: "Arctic Wolves", position: "C", age: 28, fp: 186.4,
    gp: 48, g: 22, a: 38, plusMinus: 12, ppp: 14, shp: 1, gwg: 4, sog: 198, hit: 32, blk: 18, fow: 412, fol: 298,
  },
  {
    name: "Cale Makar", team: "Glacier Kings", position: "D", age: 26, fp: 152.8,
    gp: 50, g: 10, a: 34, plusMinus: 18, ppp: 12, shp: 0, gwg: 2, sog: 142, hit: 48, blk: 76, fow: 0, fol: 0,
  },
  {
    name: "Igor Shesterkin", team: "Frozen Thunder", position: "G", age: 29, fp: 134.2,
    gp: 42, w: 18, l: 8, sol: 3, sv: 1042, ga: 72, so: 3,
  },
  {
    name: "Tim Stützle", team: "Ice Crushers", position: "C", age: 23, fp: 142.6,
    gp: 46, g: 16, a: 29, plusMinus: 5, ppp: 8, shp: 2, gwg: 3, sog: 156, hit: 28, blk: 14, fow: 384, fol: 312,
  },
];

const TradeBlockWidget = () => {
  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <ArrowRightLeft className="h-5 w-5 text-primary" />
          Trading Block
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {tradeBlockPlayers.map((player) => {
          const isGoalie = player.position === "G";
          return (
            <div key={player.name} className="flex items-center justify-between p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors gap-3">
              <div className="min-w-0">
                <p className="font-semibold text-sm">{player.name}</p>
                <p className="text-xs text-muted-foreground">
                  <TeamLink name={player.team} /> · {player.position} · Age {player.age}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {isGoalie
                    ? `GP ${player.gp} · ${player.w}W · ${player.l}L · ${player.sol}SOL · ${player.sv}SV · ${player.ga}GA · ${player.so}SO`
                    : `GP ${player.gp} · ${player.g}G · ${player.a}A · ${player.plusMinus >= 0 ? '+' : ''}${player.plusMinus} · ${player.ppp}PPP · ${player.shp}SHP · ${player.gwg}GWG · ${player.sog}SOG · ${player.hit}HIT · ${player.blk}BLK · ${player.fow}FOW · ${player.fol}FOL`
                  }
                </p>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-sm font-semibold text-primary">{player.fp} FP</p>
                <p className="text-xs text-muted-foreground">{(player.fp / player.gp).toFixed(1)} FP/GP</p>
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
};

export default TradeBlockWidget;
