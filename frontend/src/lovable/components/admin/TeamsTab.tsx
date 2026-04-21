// @ts-nocheck
import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Plus, X, Pencil, Check, Mail, Users } from "lucide-react";
import { toast } from "sonner";

interface TeamOwner {
  email: string;
  accepted: boolean;
}

interface TeamEntry {
  id: string;
  name: string;
  abbreviation: string;
  owners: TeamOwner[];
}

const initialTeams: TeamEntry[] = [
  { id: "t1", name: "Team Frostbite", abbreviation: "FRO", owners: [{ email: "john@example.com", accepted: true }] },
  { id: "t2", name: "Polar Bears", abbreviation: "PLR", owners: [{ email: "sarah@example.com", accepted: true }, { email: "mike@example.com", accepted: false }] },
  { id: "t3", name: "Ice Dragons", abbreviation: "ICE", owners: [{ email: "alex@example.com", accepted: false }] },
  { id: "t4", name: "Frost Giants", abbreviation: "FRG", owners: [{ email: "emma@example.com", accepted: true }] },
  { id: "t5", name: "Arctic Wolves", abbreviation: "ARC", owners: [{ email: "chris@example.com", accepted: true }] },
  { id: "t6", name: "Blizzard", abbreviation: "BLZ", owners: [{ email: "taylor@example.com", accepted: true }] },
  { id: "t7", name: "Snow Hawks", abbreviation: "SNH", owners: [] },
  { id: "t8", name: "Glaciers", abbreviation: "GLC", owners: [{ email: "jordan@example.com", accepted: true }] },
  { id: "t9", name: "Tundra Kings", abbreviation: "TDK", owners: [{ email: "casey@example.com", accepted: true }] },
  { id: "t10", name: "Avalanche", abbreviation: "AVL", owners: [{ email: "morgan@example.com", accepted: true }] },
  { id: "t11", name: "Icebreakers", abbreviation: "IBK", owners: [{ email: "riley@example.com", accepted: false }] },
  { id: "t12", name: "Northern Lights", abbreviation: "NTL", owners: [{ email: "quinn@example.com", accepted: true }] },
];

const TeamsTab = () => {
  const [teams, setTeams] = useState<TeamEntry[]>(initialTeams);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editAbbr, setEditAbbr] = useState("");
  const [addingOwnerFor, setAddingOwnerFor] = useState<string | null>(null);
  const [newOwnerEmail, setNewOwnerEmail] = useState("");

  const startEditing = (team: TeamEntry) => {
    setEditingId(team.id);
    setEditName(team.name);
    setEditAbbr(team.abbreviation);
  };

  const saveEditing = () => {
    if (!editingId) return;
    setTeams(prev => prev.map(t =>
      t.id === editingId ? { ...t, name: editName, abbreviation: editAbbr } : t
    ));
    setEditingId(null);
    toast.success("Team updated");
  };

  const addOwner = (teamId: string) => {
    if (!newOwnerEmail.trim() || !newOwnerEmail.includes("@")) {
      toast.error("Please enter a valid email");
      return;
    }
    setTeams(prev => prev.map(t =>
      t.id === teamId
        ? { ...t, owners: [...t.owners, { email: newOwnerEmail.trim(), accepted: false }] }
        : t
    ));
    setNewOwnerEmail("");
    setAddingOwnerFor(null);
    toast.success("Owner invited");
  };

  const removeOwner = (teamId: string, email: string) => {
    setTeams(prev => prev.map(t =>
      t.id === teamId
        ? { ...t, owners: t.owners.filter(o => o.email !== email) }
        : t
    ));
    toast.success("Owner removed");
  };

  const reinviteOwner = (email: string) => {
    toast.success(`Invite resent to ${email}`);
  };

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="h-5 w-5 text-primary" />
          Teams & Owners
        </CardTitle>
        <CardDescription>Manage team names, abbreviations, and owner assignments</CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow className="border-border">
              <TableHead className="text-muted-foreground w-[200px]">Team Name</TableHead>
              <TableHead className="text-muted-foreground w-[100px]">Abbreviation</TableHead>
              <TableHead className="text-muted-foreground">Manager Email(s)</TableHead>
              <TableHead className="text-muted-foreground text-center w-[100px]">Joined</TableHead>
              <TableHead className="text-muted-foreground text-center w-[80px]">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {teams.map((team) => (
              <TableRow key={team.id} className="border-border">
                <TableCell>
                  {editingId === team.id ? (
                    <Input
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      className="h-8 bg-secondary border-border"
                    />
                  ) : (
                    <span className="font-medium">{team.name}</span>
                  )}
                </TableCell>
                <TableCell>
                  {editingId === team.id ? (
                    <Input
                      value={editAbbr}
                      onChange={(e) => setEditAbbr(e.target.value.toUpperCase().slice(0, 4))}
                      className="h-8 bg-secondary border-border w-20"
                      maxLength={4}
                    />
                  ) : (
                    <Badge variant="outline" className="text-xs">{team.abbreviation}</Badge>
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex flex-col gap-1.5">
                    {team.owners.map((owner) => (
                      <div key={owner.email} className="flex items-center gap-2">
                        <span className="text-sm">{owner.email}</span>
                        {!owner.accepted && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-5 w-5 text-yellow-500 hover:text-yellow-400 hover:bg-yellow-500/10"
                                onClick={() => reinviteOwner(owner.email)}
                              >
                                <Mail className="h-3 w-3" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent><p className="text-xs">Reinvite owner</p></TooltipContent>
                          </Tooltip>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                          onClick={() => removeOwner(team.id, owner.email)}
                        >
                          <X className="h-3 w-3" />
                        </Button>
                      </div>
                    ))}
                    {team.owners.length === 0 && (
                      <span className="text-xs text-muted-foreground italic">No owners assigned</span>
                    )}
                    {addingOwnerFor === team.id ? (
                      <div className="flex items-center gap-1 mt-1">
                        <Input
                          placeholder="email@example.com"
                          value={newOwnerEmail}
                          onChange={(e) => setNewOwnerEmail(e.target.value)}
                          className="h-7 text-xs bg-secondary border-border"
                          onKeyDown={(e) => e.key === "Enter" && addOwner(team.id)}
                        />
                        <Button size="icon" variant="ghost" className="h-7 w-7 text-primary" onClick={() => addOwner(team.id)}>
                          <Check className="h-3 w-3" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setAddingOwnerFor(null); setNewOwnerEmail(""); }}>
                          <X className="h-3 w-3" />
                        </Button>
                      </div>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 text-xs text-primary hover:text-primary/80 w-fit gap-1 p-0"
                        onClick={() => setAddingOwnerFor(team.id)}
                      >
                        <Plus className="h-3 w-3" /> Add owner
                      </Button>
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-center">
                  {team.owners.length === 0 ? (
                    <Badge variant="outline" className="text-[10px] text-muted-foreground">N/A</Badge>
                  ) : team.owners.every(o => o.accepted) ? (
                    <Badge className="bg-green-500/20 text-green-400 border-green-500/30 text-[10px]">Yes</Badge>
                  ) : team.owners.some(o => o.accepted) ? (
                    <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/30 text-[10px]">Partial</Badge>
                  ) : (
                    <Badge variant="destructive" className="text-[10px]">No</Badge>
                  )}
                </TableCell>
                <TableCell className="text-center">
                  {editingId === team.id ? (
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-primary" onClick={saveEditing}>
                      <Check className="h-4 w-4" />
                    </Button>
                  ) : (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => startEditing(team)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent><p className="text-xs">Edit team</p></TooltipContent>
                    </Tooltip>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};

export default TeamsTab;
