// @ts-nocheck
import { useState } from "react";
import { Trophy, ChevronDown, Check, User, Mail, Pencil } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "@/hooks/use-toast";

interface League {
  id: string;
  name: string;
  teamName: string;
  record: string;
  place: number;
  totalTeams: number;
  season: string;
}

const mockLeagues: League[] = [
  { id: "1", name: "Dynasty Pro League", teamName: "Team Frostbite", record: "8-3-1", place: 2, totalTeams: 20, season: "2025-26" },
  { id: "2", name: "Northern Lights League", teamName: "Arctic Thunder", record: "10-2-0", place: 1, totalTeams: 16, season: "2025-26" },
  { id: "3", name: "Frozen Four Fantasy", teamName: "Ice Phantoms", record: "5-6-1", place: 9, totalTeams: 12, season: "2025-26" },
];

const ordinalSuffix = (n: number) => {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

export function UserLeagueMenu() {
  const [activeLeagueId, setActiveLeagueId] = useState("1");
  const [editingProfile, setEditingProfile] = useState(false);
  const [username, setUsername] = useState("FrostKing99");
  const [email, setEmail] = useState("frost@dynastyice.com");
  const [tempUsername, setTempUsername] = useState(username);
  const [tempEmail, setTempEmail] = useState(email);

  const activeLeague = mockLeagues.find(l => l.id === activeLeagueId)!;

  const allTimeRecord = mockLeagues.reduce(
    (acc, league) => {
      const [w, l, t] = league.record.split("-").map(Number);
      return { wins: acc.wins + w, losses: acc.losses + l, ties: acc.ties + t };
    },
    { wins: 0, losses: 0, ties: 0 }
  );

  const handleSaveProfile = () => {
    setUsername(tempUsername);
    setEmail(tempEmail);
    setEditingProfile(false);
    toast({ title: "Profile updated", description: "Your profile settings have been saved." });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex items-center gap-2 rounded-full hover:ring-2 hover:ring-primary/40 transition-all focus:outline-none focus:ring-2 focus:ring-primary/40">
          <div className="h-8 w-8 rounded-full bg-gradient-to-br from-primary to-ice-subtle flex items-center justify-center text-xs font-bold text-primary-foreground">
            {activeLeague.teamName.split(" ").map(w => w[0]).join("").slice(0, 2)}
          </div>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-0 bg-popover border-border">
        {/* Leagues Section */}
        <DropdownMenuLabel className="px-4 pt-3 pb-1 text-xs uppercase tracking-wider text-muted-foreground font-medium">
          Your Leagues
        </DropdownMenuLabel>
        {mockLeagues.map((league) => (
          <DropdownMenuItem
            key={league.id}
            className="px-4 py-3 cursor-pointer focus:bg-secondary"
            onClick={() => setActiveLeagueId(league.id)}
          >
            <div className="flex items-start gap-3 w-full">
              <div className="h-9 w-9 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 mt-0.5">
                <Trophy className="h-4 w-4 text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-sm text-foreground truncate">{league.name}</span>
                  {league.id === activeLeagueId && (
                    <Check className="h-4 w-4 text-primary shrink-0" />
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">{league.teamName}</p>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-xs font-medium text-foreground">{league.record}</span>
                  <span className="text-xs text-muted-foreground">•</span>
                  <span className="text-xs text-accent font-medium">{ordinalSuffix(league.place)} of {league.totalTeams}</span>
                </div>
              </div>
            </div>
          </DropdownMenuItem>
        ))}

        <DropdownMenuSeparator className="bg-border" />

        {/* Profile Settings Section */}
        <DropdownMenuLabel className="px-4 pt-2 pb-1 text-xs uppercase tracking-wider text-muted-foreground font-medium">
          Profile Settings
        </DropdownMenuLabel>
        <div className="px-4 pb-4 pt-1" onClick={(e) => e.stopPropagation()}>
          {editingProfile ? (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <User className="h-3 w-3" /> Username
                </label>
                <Input
                  value={tempUsername}
                  onChange={(e) => setTempUsername(e.target.value)}
                  className="h-8 text-sm bg-secondary border-border"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <Mail className="h-3 w-3" /> Email
                </label>
                <Input
                  value={tempEmail}
                  onChange={(e) => setTempEmail(e.target.value)}
                  className="h-8 text-sm bg-secondary border-border"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <Button size="sm" className="flex-1 h-8 text-xs" onClick={handleSaveProfile}>
                  Save
                </Button>
                <Button size="sm" variant="outline" className="flex-1 h-8 text-xs" onClick={() => {
                  setEditingProfile(false);
                  setTempUsername(username);
                  setTempEmail(email);
                }}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-sm">
                    <User className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-foreground font-medium">{username}</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <Mail className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-muted-foreground">{email}</span>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0"
                  onClick={() => {
                    setTempUsername(username);
                    setTempEmail(email);
                    setEditingProfile(true);
                  }}
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              </div>
              <div className="rounded-lg bg-secondary/60 border border-border px-3 py-2">
                <p className="text-xs text-muted-foreground mb-1">All-Time Record</p>
                <p className="text-sm font-semibold text-foreground">
                  {allTimeRecord.wins}W - {allTimeRecord.losses}L - {allTimeRecord.ties}T
                  <span className="text-xs font-normal text-muted-foreground ml-2">
                    ({mockLeagues.length} league{mockLeagues.length !== 1 ? "s" : ""})
                  </span>
                </p>
              </div>
            </div>
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
