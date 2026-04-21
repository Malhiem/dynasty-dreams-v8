// @ts-nocheck
import { useState } from "react";
import { X, ArrowUpDown, ChevronDown, ChevronUp, Send, Settings } from "lucide-react";
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

// ── Types ──────────────────────────────────────────────

interface Contract {
  salary: number;
  yearsRemaining: number;
  type: "RFA" | "UFA" | "ELC" | "Signed";
}

interface PlayerCategoryBreakdown {
  G: number;
  A: number;
  PPP: number;
  SHP: number;
  SOG: number;
  HIT: number;
  BLK: number;
  PIM: number;
  "+/-": number;
  FOW: number;
  FOL: number;
  [key: string]: number;
}

export interface TradePlayer {
  id: number;
  name: string;
  position: string;
  eligiblePositions: string[];
  team: string;
  points: number;
  dynastyValue: number;
  trend: "up" | "down" | "stable";
  age: number;
  contract: Contract;
  categoryBreakdown: PlayerCategoryBreakdown;
  statsByPeriod: Record<string, number>;
  fromTeam: string;
}

export interface TradeDraftPick {
  id: string;
  year: number;
  round: number;
  originalTeam: string | null;
  originalTeamFull: string | null;
  fromTeam: string;
  value: number;
}

interface TradeAsset {
  player: TradePlayer;
  retainSalary: boolean;
  retainedPercentage: number;
}

interface TeamInfo {
  id: string;
  name: string;
  abbr: string;
  owner: string;
}

export interface TradeBuilderDisplaySettings {
  showStats: boolean;
  showContract: boolean;
}

interface TradeBuilderProps {
  open: boolean;
  onClose: () => void;
  assets: TradeAsset[];
  picks: TradeDraftPick[];
  selectedTeam: string;
  onSelectTeam: (team: string) => void;
  onRemovePlayer: (playerId: number) => void;
  onRemovePick: (pickId: string) => void;
  onToggleRetain: (playerId: number) => void;
  onUpdateRetention: (playerId: number, pct: number) => void;
  onSendProposal: () => void;
  teams?: TeamInfo[];
  myTeamId?: string;
  onNavigateToTeam?: (teamId: string) => void;
  onNext?: () => void;
}

const defaultTeams: TeamInfo[] = [
  { id: "ice-dragons", name: "Ice Dragons", abbr: "ICE", owner: "Alex M." },
  { id: "blazers", name: "Blazers", abbr: "BLZ", owner: "Jordan K." },
  { id: "thunder", name: "Thunder", abbr: "THU", owner: "Chris P." },
  { id: "wolverines", name: "Wolverines", abbr: "WLV", owner: "Sam L." },
  { id: "phoenix", name: "Phoenix", abbr: "PHX", owner: "Taylor R." },
  { id: "storm-chasers", name: "Storm Chasers", abbr: "STM", owner: "Morgan W." },
  { id: "vipers", name: "Vipers", abbr: "VPR", owner: "Casey D." },
  { id: "avalanche", name: "Avalanche", abbr: "AVL", owner: "Riley N." },
  { id: "knights", name: "Knights", abbr: "KNT", owner: "Jamie B." },
  { id: "titans", name: "Titans", abbr: "TTN", owner: "Drew H." },
  { id: "hawks", name: "Hawks", abbr: "HWK", owner: "Pat F." },
];

const formatSalary = (salary: number) => `$${(salary / 1000000).toFixed(1)}M`;

const CURRENT_YEAR = 2026;

const getContractDisplayLabel = (contract: Contract) => {
  if (contract.type === "ELC") return "ELC";
  if (contract.type === "UFA") {
    return contract.yearsRemaining <= 1 ? "Upcoming UFA" : "UFA";
  }
  if (contract.type === "RFA") {
    return contract.yearsRemaining <= 1 ? "Upcoming RFA" : "RFA";
  }
  // Signed
  const expiryYear = CURRENT_YEAR + contract.yearsRemaining;
  return `Signed until ${expiryYear}`;
};

const getContractTooltip = (contract: Contract) => {
  const expiryYear = CURRENT_YEAR + contract.yearsRemaining;
  if (contract.type === "ELC") return `Entry-level contract, expires ${expiryYear}`;
  if (contract.type === "UFA") {
    return contract.yearsRemaining <= 1
      ? `Becomes an unrestricted free agent after this season (${expiryYear})`
      : `Unrestricted free agent after ${expiryYear}`;
  }
  if (contract.type === "RFA") {
    return contract.yearsRemaining <= 1
      ? `Becomes a restricted free agent after this season (${expiryYear})`
      : `Restricted free agent after ${expiryYear}`;
  }
  // Signed
  // Determine what they become after contract ends
  const postStatus = contract.yearsRemaining <= 2 ? "UFA" : "RFA";
  return `Signed until ${expiryYear}. Becomes ${postStatus} upon expiry.`;
};

const getContractTypeColor = (type: Contract["type"]) => {
  switch (type) {
    case "ELC": return "bg-success/20 text-success";
    case "RFA": return "bg-accent/20 text-accent";
    case "UFA": return "bg-destructive/20 text-destructive";
    case "Signed": return "bg-primary/20 text-primary";
    default: return "bg-secondary text-secondary-foreground";
  }
};

const getPositionColor = (position: string) => {
  switch (position) {
    case "C": return "bg-primary/20 text-primary";
    case "LW":
    case "RW": return "bg-success/20 text-success";
    case "D": return "bg-accent/20 text-accent";
    case "G": return "bg-purple-500/20 text-purple-400";
    default: return "bg-secondary text-secondary-foreground";
  }
};

const statKeys = ["G", "A", "PPP", "SOG", "HIT", "BLK"] as const;

// ── Player Card in Trade ──────────────────────────────

const TradePlayerCard = ({
  asset,
  onRemove,
  onToggleRetain,
  onUpdateRetention,
  canRemove,
  displaySettings,
  retentionDisabled,
}: {
  asset: TradeAsset;
  onRemove: () => void;
  onToggleRetain: () => void;
  onUpdateRetention: (pct: number) => void;
  canRemove: boolean;
  displaySettings: TradeBuilderDisplaySettings;
  retentionDisabled?: boolean;
}) => {
  const { player, retainSalary, retainedPercentage } = asset;
  const retainedAmount = (player.contract.salary * retainedPercentage) / 100;
  const effectiveSalary = player.contract.salary - retainedAmount;

  return (
    <div className="rounded-lg border border-border bg-card/80 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 p-3 bg-secondary/30">
        <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-secondary to-muted flex items-center justify-center text-xs font-bold shrink-0">
          {player.team}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm truncate">{player.name}</p>
          <div className="flex items-center gap-1.5 mt-0.5">
            {player.eligiblePositions.map(pos => (
              <span key={pos} className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${getPositionColor(pos)}`}>
                {pos}
              </span>
            ))}
            <span className="text-[10px] text-muted-foreground">Age {player.age}</span>
          </div>
        </div>
        {canRemove && (
          <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive shrink-0" onClick={onRemove}>
            <X className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      {/* Stats row */}
      {displaySettings.showStats && (
        <div className="px-3 py-2 border-t border-border/50">
          <div className="grid grid-cols-6 gap-1 text-center">
            {statKeys.map(key => (
              <div key={key} className="flex flex-col">
                <span className="text-[9px] text-muted-foreground font-medium">{key}</span>
                <span className="text-xs font-bold">{player.categoryBreakdown[key] ?? 0}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Contract info */}
      {displaySettings.showContract && (
        <div className="px-3 py-2 border-t border-border/50 flex items-center gap-2 text-xs">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge variant="outline" className={`text-[10px] cursor-help ${getContractTypeColor(player.contract.type)}`}>
                  {getContractDisplayLabel(player.contract)}
                </Badge>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-[200px]">
                <p className="text-xs">{getContractTooltip(player.contract)}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <span className="font-semibold text-accent">
            {retainSalary ? formatSalary(effectiveSalary) : formatSalary(player.contract.salary)}
          </span>
          <span className="text-muted-foreground">·</span>
          <span className="text-muted-foreground">{player.contract.yearsRemaining}yr</span>
          <span className="text-muted-foreground">·</span>
          <span className="text-muted-foreground">{player.points} FPTS</span>
        </div>
      )}

      {/* Salary retention */}
      <div className="px-3 py-2 border-t border-border/50">
        <div className="flex items-center gap-2">
          <Checkbox
            id={`retain-${player.id}`}
            checked={retainSalary}
            onCheckedChange={onToggleRetain}
            className="h-3.5 w-3.5"
            disabled={!retainSalary && retentionDisabled}
          />
          <label
            htmlFor={`retain-${player.id}`}
            className={`text-xs cursor-pointer ${!retainSalary && retentionDisabled ? "text-muted-foreground/50" : "text-muted-foreground"}`}
          >
            Salary Retention
          </label>
          {!retainSalary && retentionDisabled && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="text-[10px] text-destructive font-medium">No slots</span>
                </TooltipTrigger>
                <TooltipContent side="top">
                  <p className="text-xs">All retention slots are in use. Release a retention to enable.</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
        {retainSalary && (
          <div className="mt-2 space-y-1.5 pl-5 animate-in slide-in-from-top-1 duration-200">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Retain {retainedPercentage}%</span>
              <span className="font-semibold text-destructive">
                −{formatSalary(retainedAmount)}
              </span>
            </div>
            <Slider
              value={[retainedPercentage]}
              onValueChange={(val) => onUpdateRetention(val[0])}
              max={50}
              step={5}
              className="w-full"
            />
            <p className="text-[10px] text-muted-foreground">
              Max 50% · Cap hit retained for {player.contract.yearsRemaining}yr
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

// ── Draft Pick Card ───────────────────────────────────

const TradeDraftPickCard = ({
  pick,
  onRemove,
}: {
  pick: TradeDraftPick;
  onRemove: () => void;
}) => (
  <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-card/80">
    <div className="flex-1">
      <span className="text-xs font-semibold">
        {pick.year} Rd {pick.round}
      </span>
      {pick.originalTeam && (
        <span className="ml-1 text-[10px] text-primary">({pick.originalTeam})</span>
      )}
    </div>
    <Badge variant="outline" className="bg-accent/10 text-accent text-[10px]">
      ~{pick.value.toLocaleString()}
    </Badge>
    <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-destructive" onClick={onRemove}>
      <X className="h-3 w-3" />
    </Button>
  </div>
);

// ── Main TradeBuilder Panel ───────────────────────────

export const TradeBuilder = ({
  open,
  onClose,
  assets,
  picks,
  selectedTeam,
  onSelectTeam,
  onRemovePlayer,
  onRemovePick,
  onToggleRetain,
  onUpdateRetention,
  onSendProposal,
  teams,
  myTeamId = "frostbite",
  onNavigateToTeam,
  onNext,
}: TradeBuilderProps) => {
  const [collapsed, setCollapsed] = useState(false);
  const [displaySettings, setDisplaySettings] = useState<TradeBuilderDisplaySettings>({
    showStats: true,
    showContract: true,
  });

  if (!open) return null;

  const availableTeams = (teams ?? defaultTeams).filter(t => t.id !== myTeamId);

  const handleSelectTeam = (teamName: string) => {
    onSelectTeam(teamName);
    const team = availableTeams.find(t => t.name === teamName);
    if (team && onNavigateToTeam) {
      onNavigateToTeam(team.id);
    }
  };

  const myAssets = assets.filter(a => a.player.fromTeam === "mine");
  const theirAssets = assets.filter(a => a.player.fromTeam !== "mine");
  const myPicks = picks.filter(p => p.fromTeam === "mine");
  const theirPicks = picks.filter(p => p.fromTeam !== "mine");

  const totalMyValue =
    myAssets.reduce((s, a) => s + a.player.dynastyValue, 0) +
    myPicks.reduce((s, p) => s + p.value, 0);
  const totalTheirValue =
    theirAssets.reduce((s, a) => s + a.player.dynastyValue, 0) +
    theirPicks.reduce((s, p) => s + p.value, 0);
  const totalRetained = assets.reduce(
    (s, a) => s + (a.retainSalary ? (a.player.contract.salary * a.retainedPercentage) / 100 : 0),
    0
  );

  // Retention slot tracking: 3 total, 1 already used league-wide
  const retentionSlotsTotal = 3;
  const retentionSlotsUsedExisting = 1;
  const retentionSlotsUsedInTrade = assets.filter(a => a.retainSalary).length;
  const retentionSlotsRemaining = retentionSlotsTotal - retentionSlotsUsedExisting - retentionSlotsUsedInTrade;
  const noRetentionSlotsLeft = retentionSlotsRemaining <= 0;

  const valueDiff = totalTheirValue - totalMyValue;
  const hasAssets = assets.length > 0 || picks.length > 0;

  return (
    <div className="fixed bottom-4 right-4 z-50 w-[420px] max-h-[85vh] flex flex-col rounded-xl border border-border bg-card shadow-2xl shadow-primary/5 animate-in slide-in-from-bottom-4 duration-300">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-secondary/30 rounded-t-xl">
        <ArrowUpDown className="h-4 w-4 text-primary" />
        <h3 className="font-bold text-sm flex-1">Trade Builder</h3>
        {hasAssets && (
          <Badge variant="outline" className="text-[10px] bg-primary/10 text-primary">
            {assets.length + picks.length} assets
          </Badge>
        )}
        {/* Settings cog */}
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-foreground">
              <Settings className="h-3.5 w-3.5" />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-52 p-3 space-y-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Display Options</p>
            <div className="flex items-center justify-between">
              <Label htmlFor="show-stats" className="text-xs cursor-pointer">Stats Line</Label>
              <Switch
                id="show-stats"
                checked={displaySettings.showStats}
                onCheckedChange={(v) => setDisplaySettings(prev => ({ ...prev, showStats: !!v }))}
                className="scale-75"
              />
            </div>
            <div className="flex items-center justify-between">
              <Label htmlFor="show-contract" className="text-xs cursor-pointer">Contract Line</Label>
              <Switch
                id="show-contract"
                checked={displaySettings.showContract}
                onCheckedChange={(v) => setDisplaySettings(prev => ({ ...prev, showContract: !!v }))}
                className="scale-75"
              />
            </div>
          </PopoverContent>
        </Popover>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setCollapsed(!collapsed)}>
          {collapsed ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </Button>
        <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {!collapsed && (
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Team selector */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Trade Partner</label>
            <Select value={selectedTeam} onValueChange={handleSelectTeam}>
              <SelectTrigger className="bg-secondary/50 h-9 text-xs">
                <SelectValue placeholder="Select team..." />
              </SelectTrigger>
              <SelectContent>
                {availableTeams.map((team) => (
                  <SelectItem key={team.id} value={team.name}>
                    <span className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground w-8">{team.abbr}</span>
                      <span>{team.name}</span>
                      <span className="text-[10px] text-muted-foreground">({team.owner})</span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Your Assets */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">You Send</h4>
              {totalMyValue > 0 && (
                <span className="text-[10px] font-semibold text-accent">{totalMyValue.toLocaleString()} value</span>
              )}
            </div>
            {myAssets.length === 0 && myPicks.length === 0 ? (
              <p className="text-xs text-muted-foreground italic py-2">Click trade icons on your roster to add players/picks</p>
            ) : (
              <div className="space-y-2">
                {myAssets.map(asset => (
                  <TradePlayerCard
                    key={asset.player.id}
                    asset={asset}
                    onRemove={() => onRemovePlayer(asset.player.id)}
                    onToggleRetain={() => onToggleRetain(asset.player.id)}
                    onUpdateRetention={(pct) => onUpdateRetention(asset.player.id, pct)}
                    canRemove={true}
                    displaySettings={displaySettings}
                    retentionDisabled={!asset.retainSalary && noRetentionSlotsLeft}
                  />
                ))}
                {myPicks.map(pick => (
                  <TradeDraftPickCard key={pick.id} pick={pick} onRemove={() => onRemovePick(pick.id)} />
                ))}
              </div>
            )}
          </div>

          {/* Their Assets */}
          {(theirAssets.length > 0 || theirPicks.length > 0) && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">You Receive</h4>
                {totalTheirValue > 0 && (
                  <span className="text-[10px] font-semibold text-primary">{totalTheirValue.toLocaleString()} value</span>
                )}
              </div>
              <div className="space-y-2">
                {theirAssets.map(asset => (
                  <TradePlayerCard
                    key={asset.player.id}
                    asset={asset}
                    onRemove={() => onRemovePlayer(asset.player.id)}
                    onToggleRetain={() => onToggleRetain(asset.player.id)}
                    onUpdateRetention={(pct) => onUpdateRetention(asset.player.id, pct)}
                    canRemove={true}
                    displaySettings={displaySettings}
                    retentionDisabled={!asset.retainSalary && noRetentionSlotsLeft}
                  />
                ))}
                {theirPicks.map(pick => (
                  <TradeDraftPickCard key={pick.id} pick={pick} onRemove={() => onRemovePick(pick.id)} />
                ))}
              </div>
            </div>
          )}

          {/* Trade Summary */}
          {hasAssets && (
            <div className="p-3 rounded-lg bg-muted/50 border border-border space-y-2">
              <h4 className="text-xs font-bold">Trade Summary</h4>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">You send:</span>
                  <span className="font-semibold text-accent">{totalMyValue.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">You receive:</span>
                  <span className="font-semibold text-primary">{totalTheirValue.toLocaleString()}</span>
                </div>
              </div>
              <div className="flex items-center justify-between text-xs pt-1 border-t border-border/50">
                <span className="text-muted-foreground">Value difference:</span>
                <span className={`font-bold ${valueDiff > 0 ? "text-success" : valueDiff < 0 ? "text-destructive" : "text-foreground"}`}>
                  {valueDiff > 0 ? "+" : ""}{valueDiff.toLocaleString()}
                </span>
              </div>
              {totalRetained > 0 && (
                <div className="flex items-center justify-between text-xs pt-1 border-t border-border/50">
                  <span className="text-muted-foreground">Retained salary:</span>
                  <span className="font-semibold text-destructive">{formatSalary(totalRetained)}</span>
                </div>
              )}
              {retentionSlotsUsedInTrade > 0 && (
                <div className="flex items-center justify-between text-xs pt-1 border-t border-border/50">
                  <span className="text-muted-foreground">Retention slots:</span>
                  <span className={`font-semibold ${noRetentionSlotsLeft ? "text-destructive" : "text-muted-foreground"}`}>
                    {retentionSlotsUsedExisting + retentionSlotsUsedInTrade} / {retentionSlotsTotal} used
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Footer actions */}
      {!collapsed && (
        <div className="flex items-center justify-between gap-2 px-4 py-3 border-t border-border bg-secondary/20 rounded-b-xl">
          <Button variant="outline" size="sm" className="text-xs" onClick={onClose}>
            Cancel
          </Button>
          <div className="flex items-center gap-2">
            {onNext && (
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={onNext}
              >
                Next
              </Button>
            )}
            <Button
              size="sm"
              className="text-xs bg-primary hover:bg-primary/90"
              disabled={!selectedTeam || !hasAssets}
              onClick={onSendProposal}
            >
              <Send className="h-3.5 w-3.5 mr-1.5" />
              Send Proposal
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default TradeBuilder;
