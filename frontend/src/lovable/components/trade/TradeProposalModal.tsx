// @ts-nocheck
import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { ArrowRightLeft, ChevronLeft, ChevronRight, Send } from "lucide-react";

interface Player {
  id: number;
  name: string;
  position: string;
  team: string;
  dynastyValue: number;
}

interface Pick {
  id: number;
  round: string;
  year: number;
  original: string;
}

interface TradeProposalModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  targetTeam: string;
  targetPlayers: Player[];
  // iter-82: pre-select these players from `targetPlayers` when the modal
  // opens. Used when the user clicked a "Trade" button on a specific player
  // card — that player should already be on the "want" side so the user
  // only has to pick what to offer.
  prefilledTheirPlayerIds?: number[];
}

const myRoster: Player[] = [
  { id: 101, name: "Nathan MacKinnon", position: "C", team: "COL", dynastyValue: 9200 },
  { id: 102, name: "Cale Makar", position: "D", team: "COL", dynastyValue: 9500 },
  { id: 103, name: "Igor Shesterkin", position: "G", team: "NYR", dynastyValue: 7200 },
  { id: 104, name: "Artemi Panarin", position: "LW", team: "NYR", dynastyValue: 6800 },
  { id: 105, name: "Mikko Rantanen", position: "RW", team: "COL", dynastyValue: 7500 },
];

const myPicks: Pick[] = [
  { id: 201, round: "1st", year: 2025, original: "Own" },
  { id: 202, round: "2nd", year: 2025, original: "Own" },
  { id: 203, round: "1st", year: 2026, original: "Own" },
];

export const TradeProposalModal = ({
  open,
  onOpenChange,
  targetTeam,
  targetPlayers,
  prefilledTheirPlayerIds,
}: TradeProposalModalProps) => {
  const [step, setStep] = useState<"their-roster" | "my-roster" | "review">("their-roster");
  const [selectedTheirPlayers, setSelectedTheirPlayers] = useState<number[]>([]);
  const [selectedMyPlayers, setSelectedMyPlayers] = useState<number[]>([]);
  const [selectedMyPicks, setSelectedMyPicks] = useState<number[]>([]);

  // Seed the requested side whenever the modal opens with a prefilled id.
  // The user landed here from a per-player Trade button; pre-checking saves
  // them a click and signals "yes, we found the player you came for".
  useEffect(() => {
    if (!open) return;
    if (prefilledTheirPlayerIds && prefilledTheirPlayerIds.length > 0) {
      setSelectedTheirPlayers(prefilledTheirPlayerIds);
      setStep("my-roster"); // skip "their roster" step — already chosen
    }
  }, [open, prefilledTheirPlayerIds]);

  const handleClose = () => {
    setStep("their-roster");
    setSelectedTheirPlayers([]);
    setSelectedMyPlayers([]);
    setSelectedMyPicks([]);
    onOpenChange(false);
  };

  const toggleTheirPlayer = (id: number) => {
    setSelectedTheirPlayers((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]
    );
  };

  const toggleMyPlayer = (id: number) => {
    setSelectedMyPlayers((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]
    );
  };

  const toggleMyPick = (id: number) => {
    setSelectedMyPicks((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]
    );
  };

  const theirValue = targetPlayers
    .filter((p) => selectedTheirPlayers.includes(p.id))
    .reduce((sum, p) => sum + p.dynastyValue, 0);

  const myValue = myRoster
    .filter((p) => selectedMyPlayers.includes(p.id))
    .reduce((sum, p) => sum + p.dynastyValue, 0) +
    selectedMyPicks.length * 2000;

  const getStepTitle = () => {
    switch (step) {
      case "their-roster":
        return `${targetTeam}'s Roster`;
      case "my-roster":
        return "Your Roster";
      case "review":
        return "Review Trade Proposal";
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl bg-card border-border">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArrowRightLeft className="h-5 w-5 text-primary" />
            {getStepTitle()}
          </DialogTitle>
        </DialogHeader>

        <div className="flex gap-2 mb-4">
          {["their-roster", "my-roster", "review"].map((s, idx) => (
            <div
              key={s}
              className={`flex-1 h-1 rounded-full ${
                idx <= ["their-roster", "my-roster", "review"].indexOf(step)
                  ? "bg-primary"
                  : "bg-secondary"
              }`}
            />
          ))}
        </div>

        {step === "their-roster" && (
          <div className="space-y-3 max-h-80 overflow-y-auto">
            <p className="text-sm text-muted-foreground mb-4">
              Select players you want from {targetTeam}
            </p>
            {targetPlayers.map((player) => (
              <div
                key={player.id}
                className={`flex items-center gap-3 p-3 rounded-lg border transition-colors cursor-pointer ${
                  selectedTheirPlayers.includes(player.id)
                    ? "border-primary bg-primary/10"
                    : "border-border hover:border-primary/50"
                }`}
                onClick={() => toggleTheirPlayer(player.id)}
              >
                <Checkbox checked={selectedTheirPlayers.includes(player.id)} />
                <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold">
                  {player.team}
                </div>
                <div className="flex-1">
                  <p className="font-medium">{player.name}</p>
                  <p className="text-sm text-muted-foreground">{player.position}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {step === "my-roster" && (
          <div className="space-y-4 max-h-80 overflow-y-auto">
            <p className="text-sm text-muted-foreground mb-2">
              Select players and picks to offer
            </p>
            
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-muted-foreground uppercase">Players</h4>
              {myRoster.map((player) => (
                <div
                  key={player.id}
                  className={`flex items-center gap-3 p-3 rounded-lg border transition-colors cursor-pointer ${
                    selectedMyPlayers.includes(player.id)
                      ? "border-primary bg-primary/10"
                      : "border-border hover:border-primary/50"
                  }`}
                  onClick={() => toggleMyPlayer(player.id)}
                >
                  <Checkbox checked={selectedMyPlayers.includes(player.id)} />
                  <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold">
                    {player.team}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium">{player.name}</p>
                    <p className="text-sm text-muted-foreground">{player.position}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-muted-foreground uppercase">Draft Picks</h4>
              {myPicks.map((pick) => (
                <div
                  key={pick.id}
                  className={`flex items-center gap-3 p-3 rounded-lg border transition-colors cursor-pointer ${
                    selectedMyPicks.includes(pick.id)
                      ? "border-primary bg-primary/10"
                      : "border-border hover:border-primary/50"
                  }`}
                  onClick={() => toggleMyPick(pick.id)}
                >
                  <Checkbox checked={selectedMyPicks.includes(pick.id)} />
                  <div className="flex-1">
                    <p className="font-medium">
                      {pick.year} {pick.round} Round
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {pick.original === "Own" ? "Your pick" : `Via ${pick.original}`}
                    </p>
                  </div>
                  <Badge variant="outline" className="bg-accent/20 text-accent">
                    ~2,000
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        )}

        {step === "review" && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 rounded-lg bg-secondary/30 border border-border">
                <h4 className="text-sm font-semibold text-muted-foreground mb-3">
                  You Receive
                </h4>
                <div className="space-y-2">
                  {targetPlayers
                    .filter((p) => selectedTheirPlayers.includes(p.id))
                    .map((player) => (
                      <div key={player.id} className="text-sm">
                        <span>{player.name}</span>
                      </div>
                    ))}
                </div>
              </div>

              <div className="p-4 rounded-lg bg-secondary/30 border border-border">
                <h4 className="text-sm font-semibold text-muted-foreground mb-3">
                  You Send
                </h4>
                <div className="space-y-2">
                  {myRoster
                    .filter((p) => selectedMyPlayers.includes(p.id))
                    .map((player) => (
                      <div key={player.id} className="text-sm">
                        <span>{player.name}</span>
                      </div>
                    ))}
                  {myPicks
                    .filter((p) => selectedMyPicks.includes(p.id))
                    .map((pick) => (
                      <div key={pick.id} className="text-sm">
                        <span>{pick.year} {pick.round}</span>
                      </div>
                    ))}
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="flex justify-between mt-4">
          <Button
            variant="outline"
            onClick={() => {
              if (step === "my-roster") setStep("their-roster");
              else if (step === "review") setStep("my-roster");
              else handleClose();
            }}
          >
            <ChevronLeft className="h-4 w-4 mr-1" />
            {step === "their-roster" ? "Cancel" : "Back"}
          </Button>

          {step !== "review" ? (
            <Button
              onClick={() => {
                if (step === "their-roster") setStep("my-roster");
                else setStep("review");
              }}
              disabled={step === "their-roster" && selectedTheirPlayers.length === 0}
            >
              Next
              <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          ) : (
            <Button
              className="bg-primary hover:bg-primary/90"
              disabled={selectedTheirPlayers.length === 0 || (selectedMyPlayers.length === 0 && selectedMyPicks.length === 0)}
            >
              <Send className="h-4 w-4 mr-2" />
              Send Proposal
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
