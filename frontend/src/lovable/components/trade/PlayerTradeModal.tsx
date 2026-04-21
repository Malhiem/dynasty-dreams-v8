// @ts-nocheck
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowUpDown, Send, Plus, X } from "lucide-react";

interface Contract {
  salary: number;
  yearsRemaining: number;
  type: "RFA" | "UFA" | "ELC" | "Signed";
}

interface Player {
  id: number;
  name: string;
  position: string;
  team: string;
  points: number;
  dynastyValue: number;
  trend: "up" | "down" | "stable";
  age: number;
  contract: Contract;
}

interface DraftPick {
  id: number;
  round: string;
  year: number;
  original: string;
  value: number;
}

interface TradeAsset {
  player: Player;
  retainedPercentage: number;
}

interface PlayerTradeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialPlayer: Player;
  allPlayers: Player[];
}

const otherTeams = [
  "Arctic Wolves",
  "Blizzard Kings",
  "Frost Giants",
  "Ice Dragons",
  "Northern Lights",
  "Polar Bears",
  "Snow Hawks",
  "Tundra Titans",
  "Winter Storm",
  "Glacier Force",
  "Avalanche",
];

const myDraftPicks: DraftPick[] = [
  { id: 201, round: "1st", year: 2025, original: "Own", value: 3500 },
  { id: 202, round: "2nd", year: 2025, original: "Own", value: 2000 },
  { id: 203, round: "3rd", year: 2025, original: "Own", value: 1200 },
  { id: 204, round: "1st", year: 2026, original: "Own", value: 3200 },
  { id: 205, round: "2nd", year: 2026, original: "Own", value: 1800 },
  { id: 206, round: "1st", year: 2027, original: "Own", value: 3000 },
];

const formatSalary = (salary: number) => {
  return `$${(salary / 1000000).toFixed(1)}M`;
};

export const PlayerTradeModal = ({
  open,
  onOpenChange,
  initialPlayer,
  allPlayers,
}: PlayerTradeModalProps) => {
  const [selectedTeam, setSelectedTeam] = useState<string>("");
  const [tradeAssets, setTradeAssets] = useState<TradeAsset[]>([
    { player: initialPlayer, retainedPercentage: 0 },
  ]);
  const [selectedPicks, setSelectedPicks] = useState<number[]>([]);
  const [pickToAdd, setPickToAdd] = useState<string>("");

  const handleClose = () => {
    setSelectedTeam("");
    setTradeAssets([{ player: initialPlayer, retainedPercentage: 0 }]);
    setSelectedPicks([]);
    setPickToAdd("");
    onOpenChange(false);
  };

  const addPlayerToTrade = (playerId: number) => {
    const player = allPlayers.find((p) => p.id === playerId);
    if (player && !tradeAssets.some((a) => a.player.id === playerId)) {
      setTradeAssets([...tradeAssets, { player, retainedPercentage: 0 }]);
    }
  };

  const removePlayerFromTrade = (playerId: number) => {
    if (tradeAssets.length > 1) {
      setTradeAssets(tradeAssets.filter((a) => a.player.id !== playerId));
    }
  };

  const updateRetention = (playerId: number, percentage: number) => {
    setTradeAssets(
      tradeAssets.map((a) =>
        a.player.id === playerId ? { ...a, retainedPercentage: percentage } : a
      )
    );
  };

  const addDraftPick = () => {
    if (pickToAdd) {
      const pickId = parseInt(pickToAdd);
      if (!selectedPicks.includes(pickId)) {
        setSelectedPicks([...selectedPicks, pickId]);
      }
      setPickToAdd("");
    }
  };

  const removeDraftPick = (pickId: number) => {
    setSelectedPicks(selectedPicks.filter((id) => id !== pickId));
  };

  const availablePlayers = allPlayers.filter(
    (p) => !tradeAssets.some((a) => a.player.id === p.id)
  );

  const availablePicks = myDraftPicks.filter(
    (p) => !selectedPicks.includes(p.id)
  );

  const totalRetainedSalary = tradeAssets.reduce(
    (sum, a) => sum + (a.player.contract.salary * a.retainedPercentage) / 100,
    0
  );

  const totalOutgoingValue =
    tradeAssets.reduce((sum, a) => sum + a.player.dynastyValue, 0) +
    selectedPicks.reduce((sum, id) => {
      const pick = myDraftPicks.find((p) => p.id === id);
      return sum + (pick?.value || 0);
    }, 0);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl bg-card border-border max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArrowUpDown className="h-5 w-5 text-primary" />
            Propose Trade
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-6">
          {/* Select Trade Partner */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-muted-foreground">
              Trade Partner
            </label>
            <Select value={selectedTeam} onValueChange={setSelectedTeam}>
              <SelectTrigger className="bg-secondary/50">
                <SelectValue placeholder="Select a team..." />
              </SelectTrigger>
              <SelectContent>
                {otherTeams.map((team) => (
                  <SelectItem key={team} value={team}>
                    {team}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Players Being Traded */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-muted-foreground">
                Players to Trade
              </label>
              {availablePlayers.length > 0 && (
                <Select
                  value=""
                  onValueChange={(val) => addPlayerToTrade(parseInt(val))}
                >
                  <SelectTrigger className="w-[180px] bg-secondary/50">
                    <SelectValue placeholder="Add player..." />
                  </SelectTrigger>
                  <SelectContent>
                    {availablePlayers.map((player) => (
                      <SelectItem key={player.id} value={player.id.toString()}>
                        {player.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            <div className="space-y-3">
              {tradeAssets.map((asset) => (
                <div
                  key={asset.player.id}
                  className="p-4 rounded-lg border border-border bg-secondary/20"
                >
                  <div className="flex items-center gap-3 mb-3">
                    <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-secondary to-muted flex items-center justify-center text-xs font-bold">
                      {asset.player.team}
                    </div>
                    <div className="flex-1">
                      <p className="font-medium">{asset.player.name}</p>
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <span>{asset.player.position}</span>
                        <span>•</span>
                        <span className="text-accent">
                          {formatSalary(asset.player.contract.salary)}
                        </span>
                        <span>•</span>
                        <span>{asset.player.contract.yearsRemaining}yr</span>
                      </div>
                    </div>
                    {tradeAssets.length > 1 && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        onClick={() => removePlayerFromTrade(asset.player.id)}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    )}
                  </div>

                  {/* Salary Retention Slider */}
                  <div className="space-y-2 pt-2 border-t border-border/50">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">
                        Salary Retention
                      </span>
                      <span className="font-medium text-accent">
                        {asset.retainedPercentage}% (
                        {formatSalary(
                          (asset.player.contract.salary *
                            asset.retainedPercentage) /
                            100
                        )}
                        )
                      </span>
                    </div>
                    <Slider
                      value={[asset.retainedPercentage]}
                      onValueChange={(val) =>
                        updateRetention(asset.player.id, val[0])
                      }
                      max={50}
                      step={5}
                      className="w-full"
                    />
                    <p className="text-xs text-muted-foreground">
                      Max 50% retention. You keep cap hit for duration of
                      contract.
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Draft Picks */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-muted-foreground">
                Draft Picks to Include
              </label>
              <div className="flex gap-2">
                <Select value={pickToAdd} onValueChange={setPickToAdd}>
                  <SelectTrigger className="w-[160px] bg-secondary/50">
                    <SelectValue placeholder="Select pick..." />
                  </SelectTrigger>
                  <SelectContent>
                    {availablePicks.map((pick) => (
                      <SelectItem key={pick.id} value={pick.id.toString()}>
                        {pick.year} {pick.round} Round
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  variant="outline"
                  size="icon"
                  onClick={addDraftPick}
                  disabled={!pickToAdd}
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {selectedPicks.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {selectedPicks.map((pickId) => {
                  const pick = myDraftPicks.find((p) => p.id === pickId);
                  if (!pick) return null;
                  return (
                    <Badge
                      key={pickId}
                      variant="secondary"
                      className="flex items-center gap-1 pr-1"
                    >
                      {pick.year} {pick.round} Round
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-4 w-4 ml-1 hover:bg-destructive/20"
                        onClick={() => removeDraftPick(pickId)}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </Badge>
                  );
                })}
              </div>
            )}
          </div>

          {/* Trade Summary */}
          <div className="p-4 rounded-lg bg-muted/50 border border-border space-y-3">
            <h4 className="font-semibold text-sm">Trade Summary</h4>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Players:</span>
                <span className="ml-2 font-medium">{tradeAssets.length}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Draft Picks:</span>
                <span className="ml-2 font-medium">{selectedPicks.length}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Total Value:</span>
                <span className="ml-2 font-medium text-primary">
                  {totalOutgoingValue.toLocaleString()}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Retained Salary:</span>
                <span className="ml-2 font-medium text-accent">
                  {formatSalary(totalRetainedSalary)}
                </span>
              </div>
            </div>
            {totalRetainedSalary > 0 && (
              <p className="text-xs text-muted-foreground border-t border-border/50 pt-2">
                Note: Retained salary will count against your cap for the
                remainder of the contract period.
              </p>
            )}
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={handleClose}>
              Cancel
            </Button>
            <Button
              disabled={!selectedTeam}
              className="bg-primary hover:bg-primary/90"
            >
              <Send className="h-4 w-4 mr-2" />
              Send Trade Proposal
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
